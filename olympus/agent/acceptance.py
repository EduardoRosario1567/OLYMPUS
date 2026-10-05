"""Independent, deterministic acceptance for autonomous missions.

The model's ``finish`` is a claim, not evidence. This module measures the
workspace itself (file snapshots, a real test run, an HTML structure check) so
that a mission is accepted only when the evidence supports it. It has no
dependency on the mission engine: it only needs a workspace directory.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

IGNORED_DIRS = frozenset({
    ".git", ".olympus", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".venv", "venv", "dist", "build",
})
MAX_HASH_BYTES = 5 * 1024 * 1024
TEST_TIMEOUT_SECONDS = 120


# --------------------------------------------------------------------------- #
# Workspace snapshots
# --------------------------------------------------------------------------- #
def snapshot(root) -> Dict[str, str]:
    base = Path(root).resolve()
    out: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                size = path.stat().st_size
                rel = path.relative_to(base).as_posix()
                out[rel] = (
                    "size:%d" % size if size > MAX_HASH_BYTES
                    else hashlib.sha256(path.read_bytes()).hexdigest()
                )
            except OSError:
                continue
    return out


def diff_snapshots(before: Dict[str, str], after: Dict[str, str]) -> Tuple[List[str], List[str], List[str]]:
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    modified = sorted(p for p in set(before) & set(after) if before[p] != after[p])
    return created, modified, deleted


def _inside(root: Path, relative: str) -> Optional[Path]:
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


# --------------------------------------------------------------------------- #
# Result / context / check base
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def line(self) -> str:
        return "%s %s: %s" % ("PASS" if self.passed else "FAIL", self.name, self.detail)


@dataclass
class AcceptanceContext:
    root: Path
    before: Dict[str, str]
    after: Dict[str, str]
    claimed_modified: Tuple[str, ...] = ()
    baseline: Dict[str, dict] = field(default_factory=dict)

    @property
    def changes(self) -> Tuple[List[str], List[str], List[str]]:
        return diff_snapshots(self.before, self.after)

    @property
    def changed_files(self) -> List[str]:
        created, modified, _ = self.changes
        return created + modified


class Check:
    name = "check"

    def prepare(self, root: Path) -> dict:
        """Optional measurement taken BEFORE the mission runs."""
        return {}

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
class ExactTextFile(Check):
    def __init__(self, relative_path: str, expected: str) -> None:
        self.relative_path = relative_path
        self.expected = expected
        self.name = "exact_text:%s" % relative_path

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        path = _inside(ctx.root, self.relative_path)
        actual = None
        if path is not None and path.is_file():
            try:
                actual = path.read_text(encoding="utf-8")
            except OSError:
                actual = None
        if actual == self.expected or actual == self.expected + "\n":
            return CheckResult(self.name, True, "content is exact (single trailing newline tolerated)")
        preview = "<missing>" if actual is None else actual[:120]
        return CheckResult(
            self.name, False,
            "%s content mismatch; expected=%r; actual=%r" % (self.relative_path, self.expected[:120], preview),
        )


class FileExists(Check):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.name = "file_exists:%s" % relative_path

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        path = _inside(ctx.root, self.relative_path)
        ok = bool(path is not None and path.is_file())
        return CheckResult(self.name, ok, "file exists" if ok else "file is missing")


class CommandSucceeds(Check):
    def __init__(self, command: Sequence[str], timeout: int = TEST_TIMEOUT_SECONDS, name: str = "command_succeeds") -> None:
        self.command = list(command)
        self.timeout = timeout
        self.name = name

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        result = run_tests(ctx.root, self.command, self.timeout)
        ok = result.get("returncode") == 0
        return CheckResult(self.name, ok, "command exited 0" if ok else result.get("tail", "command failed"))


class MinFilesChanged(Check):
    def __init__(self, minimum: int) -> None:
        self.minimum = minimum
        self.name = "min_files_changed>=%d" % minimum

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        changed = ctx.changed_files
        ok = len(changed) >= self.minimum
        return CheckResult(
            self.name, ok,
            "%d file(s) created/modified on disk (required at least %d): %s"
            % (len(changed), self.minimum, ", ".join(changed[:8]) or "none"),
        )


def _has_python_tests(root: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        if any(f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")) for f in filenames):
            return True
    return False


def detect_test_command(root) -> Optional[List[str]]:
    root = Path(root)
    if not _has_python_tests(root):
        return None
    if importlib.util.find_spec("pytest") is not None:
        return [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    return [sys.executable, "-m", "unittest", "discover", "-q"]


def _scrubbed_env(root: Path) -> Dict[str, str]:
    # Tests run agent-written code. Never hand it the backend's provider keys.
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(root)
    return env


def run_tests(root, command: Optional[Sequence[str]], timeout: int = TEST_TIMEOUT_SECONDS) -> dict:
    if not command:
        return {"ran": False, "returncode": None, "tail": "no runnable python tests found in the workspace"}
    try:
        proc = subprocess.run(
            list(command), cwd=str(root), env=_scrubbed_env(Path(root)),
            capture_output=True, text=True, timeout=timeout, shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ran": True, "returncode": None, "tail": "test run exceeded %ds" % timeout}
    except OSError as exc:
        return {"ran": False, "returncode": None, "tail": "could not start tests: %s" % exc}
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return {"ran": True, "returncode": proc.returncode, "tail": output[-1500:]}


class TestsPass(Check):
    __test__ = False  # not a pytest test class

    def __init__(self, command: Optional[Sequence[str]], measure_baseline: bool = False,
                 timeout: int = TEST_TIMEOUT_SECONDS) -> None:
        self.command = list(command) if command else None
        self.measure_baseline = measure_baseline
        self.timeout = timeout
        self.name = "tests_pass"

    def prepare(self, root: Path) -> dict:
        if self.measure_baseline and self.command:
            return run_tests(root, self.command, self.timeout)
        return {}

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        result = run_tests(ctx.root, self.command, self.timeout)
        if result["returncode"] == 0:
            note = ""
            base = ctx.baseline.get(self.name) or {}
            if base.get("returncode") == 0:
                note = " (tests were already green before the mission: the fix is not proven by them)"
            return CheckResult(self.name, True, "test command exited 0" + note)
        code = result["returncode"]
        return CheckResult(
            self.name, False,
            "tests did not pass (exit=%s). Output tail: %s" % (code, result["tail"]),
        )


_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_OPTIONAL_END = frozenset("li p td th tr thead tbody tfoot dt dd option optgroup colgroup".split())


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[str] = []
        self.seen = set()
        self.problems: List[str] = []

    def handle_starttag(self, tag, attrs):
        self.seen.add(tag)
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.seen.add(tag)

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if tag in self.stack:
            while self.stack:
                top = self.stack.pop()
                if top == tag:
                    break
                if top not in _OPTIONAL_END:
                    self.problems.append("unclosed <%s>" % top)
        else:
            self.problems.append("stray </%s>" % tag)


def html_problems(text: str) -> List[str]:
    """Structural checks only. Prefer the project's own HTML verifier when injected."""
    if not (text or "").strip():
        return ["empty document"]
    problems: List[str] = []
    if not re.match(r"\s*(<!--.*?-->\s*)*<!doctype\s+html", text, flags=re.I | re.S):
        problems.append("missing <!DOCTYPE html>")
    parser = _StructureParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # pragma: no cover - html.parser is lenient
        problems.append("unparseable: %s" % exc)
    for tag in ("html", "head", "body", "title"):
        if tag not in parser.seen:
            problems.append("missing <%s>" % tag)
    problems.extend(parser.problems)
    for tag in parser.stack:
        if tag not in _OPTIONAL_END:
            problems.append("unclosed <%s>" % tag)
    return list(dict.fromkeys(problems))[:8]


class HtmlValid(Check):
    def __init__(self, checker: Optional[Callable[[str], List[str]]] = None) -> None:
        self.checker = checker or html_problems
        self.name = "html_valid"

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        targets = [p for p in ctx.changed_files if p.lower().endswith((".html", ".htm"))]
        if not targets:
            return CheckResult(self.name, False, "no .html file was created or modified")
        failures = []
        for rel in targets:
            path = _inside(ctx.root, rel)
            try:
                text = path.read_text(encoding="utf-8") if path else ""
            except (OSError, UnicodeDecodeError) as exc:
                failures.append("%s: unreadable (%s)" % (rel, exc))
                continue
            problems = self.checker(text)
            if problems:
                failures.append("%s: %s" % (rel, "; ".join(problems)))
        if failures:
            return CheckResult(self.name, False, " | ".join(failures)[:600])
        return CheckResult(self.name, True, "%d html file(s) structurally valid" % len(targets))


class ClaimsMatchDisk(Check):
    """Every file the run says it modified must actually exist afterwards."""
    name = "claims_match_disk"

    def verify(self, ctx: AcceptanceContext) -> CheckResult:
        missing = []
        root = ctx.root.resolve()
        for claimed in ctx.claimed_modified:
            rel = claimed
            if os.path.isabs(claimed):
                try:
                    rel = Path(claimed).resolve().relative_to(root).as_posix()
                except ValueError:
                    continue
            if any(part in IGNORED_DIRS for part in Path(rel).parts):
                continue
            if rel not in ctx.after:
                missing.append(rel)
        if missing:
            return CheckResult(self.name, False, "reported as modified but not on disk: %s" % ", ".join(missing[:8]))
        return CheckResult(self.name, True, "reported files exist")


# --------------------------------------------------------------------------- #
# Contract compilation from the task text
# --------------------------------------------------------------------------- #
_NUMBERS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}
_FILES_RX = re.compile(
    r"\b(?:alter\w*|modific\w*|edit\w*|atualiz\w*|chang\w*|modify\w*|updat\w*)\s+(\d+|\w+)\s+(?:arquivos?|files?)\b",
    re.I,
)
_TESTS_RX = re.compile(r"\b(testes?|tests?|pytest|unittest)\b", re.I)
_NO_TESTS_RX = re.compile(r"\b(sem|não|nao|without|no|don't|do not)\s+(?:\w+\s+)?(?:testes?|tests?)\b", re.I)
_FIX_RX = re.compile(r"\b(corrij\w*|conserte\w*|consert\w*|fix\w*|bug\w*|resolv\w*)\b", re.I)
_WEB_TOKENS = ("landing page", "página", "pagina", "site", "website", "html", "interface web", "tela web")

_EXACT_RX = re.compile(
    r"arquivo\s+chamado\s+(\"[^\"\n]+\"|'[^'\n]+'|[^\s,;]+)\s+contendo\s+apenas\s*:\s*(.+?)\s*$",
    re.I | re.S,
)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        inner = value[1:-1]
        if value[0] not in inner:
            return inner.strip()
    return value


def parse_exact_text_contract(task: str) -> Optional[Tuple[str, str]]:
    match = _EXACT_RX.search((task or "").strip())
    if not match:
        return None
    name = match.group(1).strip().strip("\"'")
    expected = _unquote(match.group(2).strip())
    expected = re.split(
        r"(?i)(?:\.\s+|;\s+)(?=(?:depois|em seguida|then|after that|rode|execute|verifique|valide)\b)",
        expected, maxsplit=1,
    )[0].rstrip()
    path = Path(name)
    if not name or path.is_absolute() or ".." in path.parts:
        return None
    return name, expected


@dataclass
class AcceptanceContract:
    root: Path
    checks: List[Check]
    before: Dict[str, str] = field(default_factory=dict)
    baseline: Dict[str, dict] = field(default_factory=dict)

    @property
    def explicit_checks(self) -> List[Check]:
        return [c for c in self.checks if not isinstance(c, ClaimsMatchDisk)]

    @property
    def has_explicit_checks(self) -> bool:
        return bool(self.explicit_checks)

    def prepare(self) -> None:
        self.before = snapshot(self.root)
        self.baseline = {c.name: c.prepare(self.root) for c in self.checks}

    def context(self, claimed_modified: Sequence[str] = ()) -> AcceptanceContext:
        return AcceptanceContext(
            root=self.root, before=self.before, after=snapshot(self.root),
            claimed_modified=tuple(claimed_modified), baseline=self.baseline,
        )

    def verify(self, claimed_modified: Sequence[str] = ()) -> Tuple[List[CheckResult], AcceptanceContext]:
        ctx = self.context(claimed_modified)
        return [check.verify(ctx) for check in self.checks], ctx

    def passed(self, claimed_modified: Sequence[str] = ()) -> bool:
        results, _ = self.verify(claimed_modified)
        return bool(results) and all(item.passed for item in results)


def compile_contract(task: str, root, *, html_checker: Optional[Callable[[str], List[str]]] = None,
                     test_command: Optional[Sequence[str]] = None) -> AcceptanceContract:
    root_path = Path(root).resolve()
    text = task or ""
    lowered = text.lower()
    checks: List[Check] = []

    exact = parse_exact_text_contract(text)
    if exact:
        checks.append(ExactTextFile(*exact))

    files = _FILES_RX.search(text)
    if files:
        token = files.group(1).lower()
        count = int(token) if token.isdigit() else _NUMBERS.get(token)
        if count and count > 0:
            checks.append(MinFilesChanged(count))

    fix_task = bool(_FIX_RX.search(text))
    command = list(test_command) if test_command else detect_test_command(root_path)
    tests_named = bool(_TESTS_RX.search(text)) and not _NO_TESTS_RX.search(text)
    tests_expected_for_fix = fix_task and command is not None and not _NO_TESTS_RX.search(text)
    if (tests_named or tests_expected_for_fix) and command:
        checks.append(TestsPass(command, measure_baseline=fix_task))

    if any(token in lowered for token in _WEB_TOKENS):
        checks.append(HtmlValid(html_checker))

    checks.append(ClaimsMatchDisk())
    return AcceptanceContract(root_path, checks)


def format_failures(results: Sequence[CheckResult], limit: int = 2000) -> str:
    lines = ["- %s: %s" % (r.name, r.detail[:500]) for r in results if not r.passed]
    return "\n".join(lines)[:limit]
