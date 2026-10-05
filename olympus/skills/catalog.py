"""Safe catalog and staged GitHub import for Olympus-owned agent skills."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
from typing import Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from olympus.skills.registry import SkillRegistry


MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 24 * 1024 * 1024
MAX_FILES = 500
_CRITICAL_PATTERNS = (
    (r"\brm\s+-rf\b", "destructive shell command"),
    (r"\b(?:curl|wget)\b[^\n|]*(?:\||>)", "download-and-execute instruction"),
    (r"(?:api[_-]?key|token|password)\s*[:=]", "credential-like assignment"),
    (r"ignore\s+(?:all\s+)?(?:previous|prior|olympus)", "prompt-injection instruction"),
)


@dataclass(frozen=True)
class SkillImportResult:
    imported: Tuple[str, ...]
    status: str
    findings: Tuple[str, ...]


class SkillCatalog:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def registry(self) -> SkillRegistry:
        return SkillRegistry((str(self.root),))

    def list(self) -> list[dict]:
        rows=[]
        for skill in self.registry().all():
            row=asdict(skill)
            row["triggers"]=list(skill.triggers)
            row["allowed_actions"]=list(skill.allowed_actions)
            row["constraints"]=list(skill.constraints)
            row["depends_on"]=list(skill.depends_on)
            row["guidance"]=list(skill.guidance)
            row["completion_checks"]=list(skill.completion_checks)
            rows.append(row)
        return rows

    @staticmethod
    def _github_archive_url(source_url: str) -> tuple[str, str]:
        parsed=urlparse(source_url)
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
            raise ValueError("Use uma URL HTTPS de um repositório público do GitHub.")
        parts=[part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts[:2]):
            raise ValueError("URL de repositório do GitHub inválida.")
        owner,repo=parts[0],parts[1].removesuffix(".git")
        ref="main"
        if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
            ref=parts[3]
        if not re.fullmatch(r"[A-Za-z0-9_.\/-]+",ref) or ".." in ref:
            raise ValueError("Referência do GitHub inválida.")
        return f"https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip", f"https://github.com/{owner}/{repo}"

    def import_github(self, source_url: str) -> SkillImportResult:
        archive_url,canonical=self._github_archive_url(source_url)
        request=Request(archive_url,headers={"Accept":"application/zip","User-Agent":"OLYMPUS/2.6.2"})
        with urlopen(request,timeout=20) as response:
            content=response.read(MAX_ARCHIVE_BYTES+1)
        if len(content) > MAX_ARCHIVE_BYTES:
            raise ValueError("O repositório excede o limite seguro de 8 MB.")
        return self.import_archive(content,canonical)

    def import_archive(self, content: bytes, source_url: str) -> SkillImportResult:
        if len(content) > MAX_ARCHIVE_BYTES:
            raise ValueError("O arquivo excede o limite seguro de 8 MB.")
        findings=[]
        imported=[]
        try:
            archive_file=ZipFile(BytesIO(content))
        except BadZipFile as exc:
            raise ValueError("O conteúdo baixado não é um arquivo ZIP válido.") from exc
        with archive_file as archive:
            entries=archive.infolist()
            if len(entries) > MAX_FILES or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
                raise ValueError("O conteúdo expandido excede os limites seguros.")
            for item in entries:
                path=PurePosixPath(item.filename)
                if path.is_absolute() or ".." in path.parts or (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("O arquivo contém caminho ou link simbólico inseguro.")
            skill_entries=[item for item in entries if PurePosixPath(item.filename).name == "SKILL.md" and not item.is_dir()]
            if not skill_entries:
                raise ValueError("Nenhum SKILL.md foi encontrado no repositório.")
            if any(item.file_size > 512 * 1024 for item in skill_entries):
                raise ValueError("Um SKILL.md excede o limite seguro de 512 KB.")
            core_ids=set(SkillRegistry().ids())
            prepared=[]
            for entry in skill_entries[:25]:
                try:
                    text=archive.read(entry).decode("utf-8",errors="strict")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"A skill {entry.filename} não está em UTF-8.") from exc
                local_findings=self._scan(text)
                findings.extend(f"{entry.filename}: {item}" for item in local_findings)
                skill_id=self._skill_id(text,PurePosixPath(entry.filename).parent.name)
                if skill_id in core_ids:
                    raise ValueError(f"A skill '{skill_id}' é proprietária do Olympus e não pode ser substituída.")
                if skill_id in {item[0] for item in prepared}:
                    raise ValueError(f"O repositório contém IDs duplicados para a skill '{skill_id}'.")
                destination=self.root / skill_id
                if destination.exists():
                    raise ValueError(f"A skill '{skill_id}' já existe; remova ou versione antes de substituir.")
                prepared.append((skill_id,text,local_findings))
            for skill_id,text,local_findings in prepared:
                destination=self.root / skill_id
                destination.mkdir(parents=True,exist_ok=False)
                (destination / "SKILL.md").write_text(text,encoding="utf-8")
                metadata={
                    "id":skill_id,
                    "source_url":source_url,
                    "status":"blocked" if local_findings else "review_required",
                    "category":"external",
                    "allowed_actions":["read_file","search_code","inspect_result"],
                    "findings":local_findings,
                }
                (destination / ".olympus-skill.json").write_text(
                    json.dumps(metadata,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"
                )
                imported.append(skill_id)
        return SkillImportResult(tuple(imported),"blocked" if findings else "review_required",tuple(findings))

    def approve(self, skill_id: str) -> dict:
        safe=re.sub(r"[^a-z0-9_-]","",skill_id.lower())
        directory=(self.root/safe).resolve()
        if directory.parent != self.root or not (directory/"SKILL.md").is_file():
            raise KeyError(skill_id)
        sidecar=directory/".olympus-skill.json"
        data=json.loads(sidecar.read_text(encoding="utf-8"))
        findings=list(data.get("findings") or ())
        if findings:
            raise ValueError("A skill possui achados críticos e não pode ser ativada.")
        data["status"]="active"
        sidecar.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        return next(item for item in self.list() if item["id"] == safe)

    def disable(self, skill_id: str) -> dict:
        safe=re.sub(r"[^a-z0-9_-]","",skill_id.lower())
        directory=(self.root/safe).resolve()
        sidecar=directory/".olympus-skill.json"
        if directory.parent != self.root or not sidecar.is_file():
            raise KeyError(skill_id)
        data=json.loads(sidecar.read_text(encoding="utf-8"))
        data["status"]="disabled"
        sidecar.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        return next(item for item in self.list() if item["id"] == safe)

    @staticmethod
    def _scan(text: str) -> list[str]:
        lowered=text.lower()
        return [label for pattern,label in _CRITICAL_PATTERNS if re.search(pattern,lowered,re.IGNORECASE)]

    @staticmethod
    def _skill_id(text: str, fallback: str) -> str:
        match=re.search(r"(?mi)^name\s*:\s*['\"]?([^'\"\n]+)",text[:4000])
        raw=(match.group(1) if match else fallback).strip().lower()
        skill_id=re.sub(r"[^a-z0-9_-]+","-",raw).strip("-")
        if not skill_id:
            raise ValueError("A skill não possui um identificador válido.")
        return skill_id[:80]
