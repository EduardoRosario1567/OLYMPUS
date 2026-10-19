"""Narrow, fail-closed Rosales Café pilot: external LLM returns static text, never code execution.

The generic autonomous mission endpoint stays disabled. Model content is an untrusted
document: no scripts, forms, remote assets, event attributes, or external links.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from contextlib import contextmanager
import fcntl
import stat
import tempfile
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from hashlib import sha256
import json
import os
import re
import time

MAX_HTML = 80 * 1024
MAX_CSS = 80 * 1024
API_URL = "https://api.groq.com/openai/v1/chat/completions"
_ALLOWED = frozenset({"html","head","meta","title","link","body","header","nav","main",
    "section","article","div","span","p","h1","h2","h3","h4","strong","em","a","ul","li",
    "ol","footer","small","blockquote","br","hr"})
_VOID = frozenset({"meta","link","br","hr"})
_ATTRS = frozenset({"class","id","role","aria-label","aria-hidden","aria-labelledby","href",
    "lang","charset","name","content","rel"})
_IDS = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_CLASS = re.compile(r"^[a-zA-Z0-9_\- ]{0,240}$")
_STYLE = re.compile(r"^(?:style\.css)$")


class RosalesAIError(RuntimeError):
    """Public errors must never include model prompts, secrets, or response bodies."""


class _SafeMarkup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.targets = []
        self.tags = {}
        self.stack = []
        self.css_link = 0
        self.viewport = False

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED:
            raise RosalesAIError("Unsafe markup tag")
        values = {}
        for name, value in attrs:
            if name not in _ATTRS or name in values or value is None:
                raise RosalesAIError("Unsafe or duplicate markup attribute")
            values[name] = value
            if len(value) > 300:
                raise RosalesAIError("Markup attribute too long")
        if tag == "html" and values.get("lang") != "pt-BR":
            raise RosalesAIError("Brazilian Portuguese lang required")
        if "id" in values:
            if not _IDS.fullmatch(values["id"]) or values["id"] in self.ids:
                raise RosalesAIError("Duplicate or unsafe markup id")
            self.ids.add(values["id"])
        if "class" in values and not _CLASS.fullmatch(values["class"]):
            raise RosalesAIError("Unsafe class attribute")
        if "href" in values:
            href=values["href"]
            if tag=="link":
                if values.get("rel") != "stylesheet" or not _STYLE.fullmatch(href):
                    raise RosalesAIError("External stylesheet not allowed")
                self.css_link += 1
            elif tag=="a":
                if not re.fullmatch(r"#[a-z][a-z0-9_-]{0,63}",href):
                    raise RosalesAIError("Only local anchor links are allowed")
                self.targets.append(href[1:])
            else:
                raise RosalesAIError("Unexpected href")
        if tag=="meta":
            if "charset" in values:
                if values["charset"].lower() != "utf-8" or len(values)!=1:
                    raise RosalesAIError("Unsafe charset")
            elif values.get("name")=="viewport" and values.get("content")=="width=device-width, initial-scale=1":
                self.viewport=True
            elif values.get("name") in {"description","color-scheme"} and set(values)=={"name","content"} and (values["name"]!="color-scheme" or values["content"]=="light"):
                pass
            else:
                raise RosalesAIError("Unsafe metadata")
        if tag=="link" and "href" not in values:
            raise RosalesAIError("CSS link missing")
        if tag=="a" and "href" not in values:
            raise RosalesAIError("Anchor missing")
        if tag not in _VOID:
            self.stack.append(tag)
        self.tags[tag]=self.tags.get(tag,0)+1

    def handle_startendtag(self, tag, attrs):
        if tag not in _VOID:
            raise RosalesAIError("Unexpected self-closing tag")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _VOID or not self.stack or self.stack[-1]!=tag:
            raise RosalesAIError("Unbalanced HTML tags")
        self.stack.pop()

    def finalize(self):
        if self.stack or self.tags.get("html")!=1 or self.tags.get("body")!=1:
            raise RosalesAIError("HTML structure is incomplete")
        if self.tags.get("h1")!=1 or self.tags.get("main")!=1 or self.tags.get("nav",0)<1:
            raise RosalesAIError("Accessible page structure is incomplete")
        if self.css_link!=1 or not self.viewport:
            raise RosalesAIError("Stylesheet or responsive viewport missing")
        if len(self.ids)<3 or len(self.targets)<2 or not set(self.targets).issubset(self.ids):
            raise RosalesAIError("Missing page anchors")


def validate_static_files(html: str, css: str) -> dict[str,str]:
    if not isinstance(html,str) or not isinstance(css,str):
        raise RosalesAIError("Non-text output")
    hb, cb=html.encode("utf-8"),css.encode("utf-8")
    if not 700<=len(hb)<=MAX_HTML or not 350<=len(cb)<=MAX_CSS:
        raise RosalesAIError("Static output size outside allowed range")
    if "\x00" in html or "\x00" in css or "<!ENTITY" in html.upper() or "<!DOCTYPE " in html.upper() and not html.lstrip().lower().startswith("<!doctype html>"):
        raise RosalesAIError("Unexpected document content")
    for pattern in (r"@import\b",r"url\s*\(",r"expression\s*\(",r"-moz-binding\b",
                    r"javascript\s*:",r"data\s*:",r"@font-face\b",r"(?<!-)behavior\s*:"):
        if re.search(pattern,css,re.I):
            raise RosalesAIError("CSS requires external or unsafe resources")
    # CSS escape sequences can conceal resource-fetching functions or at-rules.
    # This deliberately narrow pilot accepts only regular @media at-rules.
    if "\\" in css or any(name.lower() != "media" for name in re.findall(r"@([A-Za-z-]+)", css)):
        raise RosalesAIError("CSS uses unsupported escape or at-rule")
    parser=_SafeMarkup()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError) as exc:
        raise RosalesAIError("Invalid HTML") from None
    parser.finalize()
    if not re.search(r"Rosales\s+Caf[eé]",html,re.I) or "Col[oô]mb" not in html and "colomb" not in html.lower():
        raise RosalesAIError("Wrong brand context")
    return {"index.html":sha256(hb).hexdigest(),"style.css":sha256(cb).hexdigest()}


_SYSTEM = """Você é a IA de criação de uma prova controlada do OLYMPUS.
Crie uma landing page VISUALMENTE REFINADA para Rosales Café, em pt-BR:
café brasileiro com inspiração no estilo colombiano. Não invente história,
preço, endereço, telefone, pessoas, prêmios, certificações nem fornecedores.
RETORNE APENAS objeto JSON com duas chaves: html e css. HTML estático completo
<!doctype html><html lang="pt-BR">..., CSS separado como style.css.
Só tags HTML sem scripts, formulários, imagens externas, SVG, canvas, estilos inline,
eventos, fontes externas, recursos remotos e sem JavaScript. Identidade editorial,
tons de café, visual responsivo para 390px e desktop. HTML usa link
rel="stylesheet" href="style.css", meta charset="utf-8", meta viewport exata
content="width=device-width, initial-scale=1"; uma h1, main, nav e seções
id=inicio, id=conceito, id=experiencia. Links apenas ancoras #id existentes.
CSS sem url(), @import, @font-face. Ilustração de xícara apenas CSS.
Mantenha resposta enxuta, mas completa; não inclua blocos markdown."""


def generate_rosales_static(api_key: str, model: str, *, opener=None) -> tuple[str,str]:
    if not api_key or len(api_key)<16:
        raise RosalesAIError("Provider not configured")
    if not isinstance(model,str) or not re.fullmatch(r"[a-zA-Z0-9._/-]{3,120}",model):
        raise RosalesAIError("Model not explicitly configured")
    payload={"model":model,"temperature":0.3,"max_tokens":6200,
        "response_format":{"type":"json_object"},
        "messages":[{"role":"system","content":_SYSTEM},
                    {"role":"user","content":"Crie a landing page Rosales Café com 3 seções e os estilos."}]}
    data=json.dumps(payload,ensure_ascii=False).encode("utf-8")
    request=Request(API_URL,data=data,headers={"Content-Type":"application/json",
         "Authorization":"Bearer "+api_key,"Accept":"application/json"},method="POST")
    try:
        with (opener or urlopen)(request,timeout=65) as resp:
            raw=resp.read(200*1024+1)
        if len(raw)>200*1024:
            raise RosalesAIError("Provider reply too large")
        parsed=json.loads(raw)
        choices=parsed.get("choices")
        content=choices[0]["message"]["content"] if isinstance(choices,list) and len(choices)==1 else None
        if not isinstance(content,str):
            raise RosalesAIError("Provider did not return text")
        value=json.loads(content)
        if not isinstance(value,dict) or set(value)!={"html","css"}:
            raise RosalesAIError("Provider returned unexpected files")
        html,css=value["html"],value["css"]
        validate_static_files(html,css)
        return html,css
    except RosalesAIError:
        raise
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,TypeError,KeyError,IndexError):
        raise RosalesAIError("Provider response unavailable or invalid") from None


@contextmanager
def pilot_generation_guard(data_dir: Path, tenant_id: str, project_id: str):
    """One writer per persistent project, bounded provider attempts across restarts."""
    base=(Path(data_dir)/"rosales-ai-attempts").resolve()
    base.mkdir(mode=0o700,parents=True,exist_ok=True)
    if base.stat().st_uid!=os.getuid() or stat.S_IMODE(base.stat().st_mode)&0o077:
        raise RosalesAIError("Attempt log is not private")
    key=sha256((tenant_id+"\0"+project_id).encode()).hexdigest()
    lockfile=base/(key+".lock")
    fd=os.open(lockfile,os.O_CREAT|os.O_RDWR|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        fs=os.fstat(fd)
        if fs.st_uid!=os.getuid() or stat.S_IMODE(fs.st_mode)&0o077:
            raise RosalesAIError("Attempt lock is not private")
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RosalesAIError("An AI generation is already underway") from None
        try:
            log=base/(key+".json")
            now=time.time()
            events=[]
            if log.is_file():
                try:
                    events=json.loads(log.read_text(encoding="utf-8"))
                    if not isinstance(events,list) or any(not isinstance(x,(int,float)) for x in events):
                        raise ValueError("not a list")
                except (ValueError,OSError):
                    raise RosalesAIError("Attempt record damaged: fail closed") from None
            events=[float(x) for x in events if now-86400<float(x)<=now]
            if len(events)>=3 or (events and now-events[-1]<120):
                raise RosalesAIError("Pilot generation rate limited")
            # Record BEFORE contacting provider so errors/restarts still consume an attempt.
            events.append(now)
            tmpfd,tmpname=tempfile.mkstemp(dir=str(base),prefix=".rosales-attempt-",text=True)
            try:
                with os.fdopen(tmpfd,"w",encoding="utf-8") as out:
                    json.dump(events,out)
                    out.flush();os.fsync(out.fileno())
                os.chmod(tmpname,0o600)
                os.replace(tmpname,log)
            finally:
                if os.path.exists(tmpname): os.unlink(tmpname)
            yield
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN)
    finally:
        os.close(fd)


def save_generated_files(root: Path, html: str, css: str) -> dict[str,str]:
    hashes=validate_static_files(html,css)
    root=root.resolve(strict=True)
    if not root.is_dir():
        raise RosalesAIError("Project root missing")
    # Only our dedicated template files, never an arbitrary source tree.
    current={p.name for p in root.iterdir()}
    if current!={"index.html","style.css"} or any(p.is_symlink() for p in root.iterdir()):
        raise RosalesAIError("Project has unexpected files: aborting")
    from olympus.cloud.project_templates import INDEX_HTML, STYLE_CSS
    old={name:(root/name).read_bytes() for name in hashes}
    if old["index.html"]!=INDEX_HTML.encode("utf-8") or old["style.css"]!=STYLE_CSS.encode("utf-8"):
        raise RosalesAIError("Project template was previously changed: refusing overwrite")
    changes={"index.html":html.encode("utf-8"),"style.css":css.encode("utf-8")}
    try:
        for name,content in changes.items():
            temporary=root/(name+".rosales-writing")
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary,root/name)
    except OSError:
        for name,content in old.items():
            (root/name).write_bytes(content)
        raise RosalesAIError("Failed to save generated page") from None
    finally:
        for name in changes:
            (root/(name+".rosales-writing")).unlink(missing_ok=True)
    return hashes
