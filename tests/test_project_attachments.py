import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from olympus.cloud.attachments import (
    AttachmentTooLarge,
    MAX_ATTACHMENT_BYTES,
    ProjectAttachmentStore,
)
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class ProjectAttachmentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.projects = ProjectWorkspaceManager(self.temporary.name)
        self.project = self.projects.create("Projeto", "project-1", tenant_id="tenant-a")
        self.store = ProjectAttachmentStore(self.projects)

    def test_text_attachment_is_stored_and_added_to_mission_context(self):
        record = self.store.save("project-1", "dados.csv", b"nome,valor\nA,10\n", "text/csv", "tenant-a")
        self.assertEqual(record.kind, "text")
        self.assertEqual(record.name, "dados.csv")
        self.assertTrue(Path(self.project.root, record.path).is_file())
        self.assertTrue(Path(self.project.root, record.context_path).is_file())
        task = self.store.augment_task("project-1", "Analise os dados", [record.attachment_id], "tenant-a")
        self.assertIn("Analise os dados", task)
        self.assertIn(record.path, task)
        self.assertIn(record.context_path, task)

    def test_image_is_available_as_project_asset_with_dimensions(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (32).to_bytes(4, "big") + (24).to_bytes(4, "big")
        record = self.store.save("project-1", "foto.png", png, "image/png", "tenant-a")
        context = Path(self.project.root, record.context_path).read_text(encoding="utf-8")
        self.assertIn("32x24 pixels", context)
        self.assertIn("ativo visual", context)

    def test_zip_is_safely_imported_for_the_agent(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("src/index.ts", "export const value = 1;")
        record = self.store.save("project-1", "codigo.zip", payload.getvalue(), "application/zip", "tenant-a")
        self.assertEqual(record.kind, "archive")
        self.assertEqual(len(record.related_paths), 1)
        self.assertTrue(Path(self.project.root, record.related_paths[0]).is_file())
        task = self.store.augment_task("project-1", "Melhore", [record.attachment_id], "tenant-a")
        self.assertIn("imports/", task)

    def test_zip_path_traversal_is_rejected(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("../outside.txt", "unsafe")
        with self.assertRaisesRegex(ValueError, "unsafe archive"):
            self.store.save("project-1", "unsafe.zip", payload.getvalue(), "application/zip", "tenant-a")
        self.assertFalse(Path(self.temporary.name, "outside.txt").exists())
        self.assertEqual(self.store.list("project-1", "tenant-a"), [])
        self.assertEqual(list(Path(self.project.root, "attachments").glob("*.zip")), [])

    def test_docx_text_becomes_searchable_without_external_dependency(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="w"><w:p><w:r><w:t>Contrato Olympus</w:t></w:r></w:p></w:document>')
        record = self.store.save("project-1", "contrato.docx", payload.getvalue(), tenant_id="tenant-a")
        context = Path(self.project.root, record.context_path).read_text(encoding="utf-8")
        self.assertIn("Contrato Olympus", context)

    def test_simple_pdf_text_becomes_searchable(self):
        payload = b"%PDF-1.4\n1 0 obj<<>>stream\nBT (Resumo financeiro) Tj ET\nendstream\nendobj\n%%EOF"
        record = self.store.save("project-1", "relatorio.pdf", payload, tenant_id="tenant-a")
        context = Path(self.project.root, record.context_path).read_text(encoding="utf-8")
        self.assertIn("Resumo financeiro", context)

    def test_xlsx_shared_and_numeric_cells_become_searchable(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "xl/sharedStrings.xml",
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Receita</t></si></sst>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="s"><v>0</v></c><c><v>1200</v></c></row></sheetData></worksheet>',
            )
        record = self.store.save("project-1", "dados.xlsx", payload.getvalue(), tenant_id="tenant-a")
        context = Path(self.project.root, record.context_path).read_text(encoding="utf-8")
        self.assertIn("Receita | 1200", context)

    def test_unsupported_empty_and_large_files_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.store.save("project-1", "program.exe", b"x", tenant_id="tenant-a")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.store.save("project-1", "empty.txt", b"", tenant_id="tenant-a")
        with self.assertRaises(AttachmentTooLarge):
            self.store.save("project-1", "large.txt", b"x" * (MAX_ATTACHMENT_BYTES + 1), tenant_id="tenant-a")

    def test_tenant_isolation_and_unknown_attachment(self):
        record = self.store.save("project-1", "a.txt", b"a", tenant_id="tenant-a")
        with self.assertRaises(KeyError):
            self.store.list("project-1", tenant_id="tenant-b")
        with self.assertRaisesRegex(ValueError, "attachment not found"):
            self.store.augment_task("project-1", "task", ["missing"], tenant_id="tenant-a")
        self.assertEqual(self.store.list("project-1", "tenant-a")[0].attachment_id, record.attachment_id)

    def test_delete_removes_file_context_and_manifest_record(self):
        record = self.store.save("project-1", "notes.md", b"hello", tenant_id="tenant-a")
        self.assertTrue(self.store.delete("project-1", record.attachment_id, "tenant-a"))
        self.assertFalse(Path(self.project.root, record.path).exists())
        self.assertFalse(Path(self.project.root, record.context_path).exists())
        self.assertEqual(self.store.list("project-1", "tenant-a"), [])
        self.assertFalse(self.store.delete("project-1", record.attachment_id, "tenant-a"))

    def test_internal_manifest_is_not_in_project_export(self):
        self.store.save("project-1", "briefing.txt", b"conteudo", tenant_id="tenant-a")
        archive_path = self.projects.export_zip("project-1", tenant_id="tenant-a")
        with zipfile.ZipFile(archive_path) as archive:
            self.assertNotIn(".olympus-attachments.json", archive.namelist())
            self.assertTrue(any(name.startswith("attachments/") for name in archive.namelist()))


if __name__ == "__main__":
    unittest.main()
