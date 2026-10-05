from __future__ import annotations

from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import Iterable, Optional
import json
import re
import shutil
import stat
import struct
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
import zlib

from .project_workspace import ProjectWorkspaceManager


MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_PROJECT_ATTACHMENTS = 25
MAX_ARCHIVE_FILES = 500
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml",
    ".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx",
    ".py", ".sh", ".sql",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ARCHIVE_EXTENSIONS = {".zip"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | ARCHIVE_EXTENSIONS
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_CONTEXT_LIMIT = 200_000


class AttachmentTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class AttachmentRecord:
    attachment_id: str
    project_id: str
    name: str
    path: str
    content_type: str
    size: int
    kind: str
    created_at: float
    context_path: Optional[str] = None
    related_paths: tuple[str, ...] = ()


class ProjectAttachmentStore:
    """Dependency-free, tenant-aware attachments for cloud project workspaces."""

    def __init__(self, projects: ProjectWorkspaceManager) -> None:
        self.projects = projects
        self._lock = Lock()

    @staticmethod
    def _kind(extension: str) -> str:
        if extension in IMAGE_EXTENSIONS:
            return "image"
        if extension in ARCHIVE_EXTENSIONS:
            return "archive"
        if extension in DOCUMENT_EXTENSIONS:
            return "document"
        return "text"

    @staticmethod
    def _clean_name(filename: str) -> str:
        original = Path(str(filename).replace("\\", "/")).name.strip()
        stem = _SAFE_NAME.sub("-", Path(original).stem).strip("-._")[:80] or "arquivo"
        extension = Path(original).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("unsupported attachment type")
        return stem + extension

    def _root(self, project_id: str, tenant_id: str) -> Path:
        return self.projects.project_root(project_id, tenant_id=tenant_id).resolve()

    @staticmethod
    def _manifest_path(root: Path) -> Path:
        return root / ".olympus-attachments.json"

    def _load(self, root: Path) -> dict[str, dict]:
        path = self._manifest_path(root)
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, root: Path, records: dict[str, dict]) -> None:
        path = self._manifest_path(root)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _record(value: dict) -> AttachmentRecord:
        data = dict(value)
        data["related_paths"] = tuple(data.get("related_paths") or ())
        return AttachmentRecord(**data)

    def list(self, project_id: str, tenant_id: str = "local") -> list[AttachmentRecord]:
        root = self._root(project_id, tenant_id)
        records = [self._record(value) for value in self._load(root).values()]
        return sorted(records, key=lambda item: item.created_at)

    def save(
        self,
        project_id: str,
        filename: str,
        data: bytes,
        content_type: Optional[str] = None,
        tenant_id: str = "local",
    ) -> AttachmentRecord:
        if not data:
            raise ValueError("empty attachment")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise AttachmentTooLarge("attachment exceeds 20 MB")
        clean_name = self._clean_name(filename)
        extension = Path(clean_name).suffix.lower()
        root = self._root(project_id, tenant_id)
        with self._lock:
            records = self._load(root)
            if len(records) >= MAX_PROJECT_ATTACHMENTS:
                raise ValueError("project attachment limit reached")
            attachment_id = uuid.uuid4().hex[:12]
            relative = Path("attachments") / (attachment_id + "-" + clean_name)
            target = (root / relative).resolve()
            target.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(target)

            context_path = None
            try:
                context_path = self._write_context(root, attachment_id, clean_name, target, extension)
                related = self._extract_archive(root, attachment_id, target) if extension == ".zip" else ()
            except Exception:
                if context_path:
                    context_file = root / context_path
                    if context_file.is_file():
                        context_file.unlink()
                if target.is_file():
                    target.unlink()
                import_root = (root / "imports" / attachment_id).resolve()
                import_root.relative_to(root)
                if import_root.is_dir():
                    shutil.rmtree(import_root)
                raise
            record = AttachmentRecord(
                attachment_id=attachment_id,
                project_id=project_id,
                name=clean_name,
                path=relative.as_posix(),
                content_type=(content_type or "application/octet-stream")[:128],
                size=len(data),
                kind=self._kind(extension),
                created_at=time.time(),
                context_path=context_path,
                related_paths=tuple(related),
            )
            records[attachment_id] = asdict(record)
            self._save(root, records)
            return record

    def delete(self, project_id: str, attachment_id: str, tenant_id: str = "local") -> bool:
        root = self._root(project_id, tenant_id)
        with self._lock:
            records = self._load(root)
            value = records.get(attachment_id)
            if value is None:
                return False
            record = self._record(value)
            for relative in (record.path, record.context_path):
                if not relative:
                    continue
                candidate = (root / relative).resolve()
                candidate.relative_to(root)
                if candidate.is_file():
                    candidate.unlink()
            import_root = (root / "imports" / attachment_id).resolve()
            import_root.relative_to(root)
            if import_root.is_dir():
                shutil.rmtree(import_root)
            del records[attachment_id]
            self._save(root, records)
            return True

    def augment_task(
        self,
        project_id: str,
        task: str,
        attachment_ids: Iterable[str],
        tenant_id: str = "local",
    ) -> str:
        selected_ids = tuple(dict.fromkeys(str(value) for value in attachment_ids if value))
        if not selected_ids:
            return task.strip()
        root = self._root(project_id, tenant_id)
        records = self._load(root)
        selected = []
        for attachment_id in selected_ids:
            if attachment_id not in records:
                raise ValueError("attachment not found")
            selected.append(self._record(records[attachment_id]))
        lines = [task.strip(), "", "[OLYMPUS_ATTACHMENTS]", "Use os arquivos enviados abaixo como parte do pedido:"]
        for record in selected:
            lines.append("- %s (%s): %s" % (record.name, record.kind, record.path))
            if record.context_path:
                lines.append("  Conteúdo pesquisável: %s" % record.context_path)
            if record.related_paths:
                lines.append("  Arquivos importados: %s" % ", ".join(record.related_paths[:50]))
        lines.append("[/OLYMPUS_ATTACHMENTS]")
        return "\n".join(lines)

    def _write_context(self, root: Path, attachment_id: str, name: str, target: Path, extension: str) -> Optional[str]:
        extracted = ""
        if extension in TEXT_EXTENSIONS:
            extracted = target.read_text(encoding="utf-8", errors="replace")
        elif extension == ".docx":
            extracted = self._extract_docx(target)
        elif extension == ".xlsx":
            extracted = self._extract_xlsx(target)
        elif extension == ".pdf":
            extracted = self._extract_pdf(target.read_bytes())
        elif extension in IMAGE_EXTENSIONS:
            dimensions = self._image_dimensions(target.read_bytes(), extension)
            detail = ("%dx%d pixels" % dimensions) if dimensions else "dimensões não identificadas"
            extracted = "Imagem enviada pelo usuário: %s (%s). Use o arquivo original como ativo visual do projeto." % (name, detail)
        if not extracted.strip():
            return None
        relative = Path("attachments") / "_context" / (attachment_id + ".md")
        context_file = root / relative
        context_file.parent.mkdir(parents=True, exist_ok=True)
        context_file.write_text(("# Anexo: %s\n\n" % name) + extracted[:_CONTEXT_LIMIT], encoding="utf-8")
        return relative.as_posix()

    @staticmethod
    def _extract_docx(path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
            xml = re.sub(r"</w:p>", "\n", xml)
            return unescape(re.sub(r"<[^>]+>", "", xml))
        except (OSError, KeyError, zipfile.BadZipFile):
            return ""

    @staticmethod
    def _extract_xlsx(path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                shared = []
                if "xl/sharedStrings.xml" in archive.namelist():
                    shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                    shared = ["".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")) for item in shared_root if item.tag.endswith("}si")]
                rows = []
                for name in sorted(value for value in archive.namelist() if value.startswith("xl/worksheets/sheet") and value.endswith(".xml")):
                    sheet_root = ET.fromstring(archive.read(name))
                    rows.append("## %s" % Path(name).stem)
                    for row in (node for node in sheet_root.iter() if node.tag.endswith("}row")):
                        cells = []
                        for cell in (node for node in row if node.tag.endswith("}c")):
                            cell_type = cell.attrib.get("t")
                            if cell_type == "inlineStr":
                                value = "".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t"))
                            else:
                                value_node = next((node for node in cell if node.tag.endswith("}v")), None)
                                value = value_node.text or "" if value_node is not None else ""
                            if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                                value = shared[int(value)]
                            cells.append(value)
                        if cells:
                            rows.append(" | ".join(cells))
                return "\n".join(rows)
        except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile):
            return ""

    @staticmethod
    def _decode_pdf_literal(value: bytes) -> str:
        value = re.sub(rb"\\([nrtbf()\\])", lambda match: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}[match.group(1)], value)
        value = re.sub(rb"\\([0-7]{1,3})", lambda match: bytes([int(match.group(1), 8) % 256]), value)
        return value.decode("utf-8", errors="replace")

    @classmethod
    def _extract_pdf(cls, data: bytes) -> str:
        parts = []
        for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
            stream = match.group(1)
            dictionary = data[max(0, match.start() - 300):match.start()]
            if b"/FlateDecode" in dictionary:
                try:
                    stream = zlib.decompress(stream)
                except zlib.error:
                    continue
            for block in re.findall(rb"BT(.*?)ET", stream, re.S):
                for literal in re.findall(rb"\((.*?)(?<!\\)\)\s*Tj", block, re.S):
                    parts.append(cls._decode_pdf_literal(literal))
                for array in re.findall(rb"\[(.*?)\]\s*TJ", block, re.S):
                    values = re.findall(rb"\((.*?)(?<!\\)\)", array, re.S)
                    if values:
                        parts.append("".join(cls._decode_pdf_literal(value) for value in values))
        return "\n".join(value.strip() for value in parts if value.strip())

    @staticmethod
    def _image_dimensions(data: bytes, extension: str) -> Optional[tuple[int, int]]:
        try:
            if extension == ".png" and data[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", data[16:24])
            if extension == ".gif" and data[:3] == b"GIF":
                return struct.unpack("<HH", data[6:10])
            if extension in {".jpg", ".jpeg"}:
                index = 2
                while index + 9 < len(data):
                    if data[index] != 0xFF:
                        index += 1
                        continue
                    marker = data[index + 1]
                    length = struct.unpack(">H", data[index + 2:index + 4])[0]
                    if marker in range(0xC0, 0xC4):
                        height, width = struct.unpack(">HH", data[index + 5:index + 9])
                        return width, height
                    index += 2 + length
        except (IndexError, struct.error):
            return None
        return None

    @staticmethod
    def _extract_archive(root: Path, attachment_id: str, target: Path) -> tuple[str, ...]:
        try:
            with zipfile.ZipFile(target) as archive:
                files = [info for info in archive.infolist() if not info.is_dir()]
                if len(files) > MAX_ARCHIVE_FILES or sum(info.file_size for info in files) > MAX_ARCHIVE_BYTES:
                    raise AttachmentTooLarge("archive expands beyond the safe limit")
                safe = []
                for info in files:
                    relative = PurePosixPath(info.filename)
                    mode = info.external_attr >> 16
                    if relative.is_absolute() or ".." in relative.parts or stat.S_ISLNK(mode):
                        raise ValueError("unsafe archive entry")
                    safe.append((info, relative))
                import_root = (root / "imports" / attachment_id).resolve()
                imported = []
                for info, relative in safe:
                    destination = (import_root / Path(*relative.parts)).resolve()
                    destination.relative_to(import_root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    imported.append(destination.relative_to(root).as_posix())
                return tuple(imported)
        except zipfile.BadZipFile:
            raise ValueError("invalid zip attachment")
