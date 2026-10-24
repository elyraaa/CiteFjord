"""Core file workflow for the native desktop application."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.library import (
    APP_NAME, app_home, delete_document, delete_documents, import_document, index_is_current, list_documents,
    mark_index_current, read_document, save_document, validate_name,
)


class LibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        env = patch.dict(os.environ, {"RAG_HOME": str(self.home / "app")})
        env.start()
        self.addCleanup(env.stop)

    def test_import_edit_and_delete_copies(self) -> None:
        original = self.home / "notes.md"
        original.write_text("first version", encoding="utf-8")
        imported = import_document(original)
        self.assertEqual(read_document("notes.md"), "first version")
        self.assertEqual([path.name for path in list_documents()], ["notes.md"])
        save_document("notes.md", "edited version")
        self.assertEqual(read_document("notes.md"), "edited version")
        self.assertEqual(original.read_text(encoding="utf-8"), "first version")
        self.assertEqual(imported.parent.name, "documents")
        delete_document("notes.md")
        self.assertEqual(list_documents(), [])

    def test_reject_unsafe_or_unsupported_names(self) -> None:
        for name in ("../outside.md", r"..\outside.md", ".hidden.md", "program.exe"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_name(name)
        with self.assertRaises(ValueError):
            save_document("report.pdf", "text", create=True)

    def test_index_state_detects_edits(self) -> None:
        self.assertFalse(index_is_current())
        save_document("notes.txt", "one", create=True)
        # A real index is required before the state can be current.
        (self.home / "app" / "chroma_db").mkdir()
        (self.home / "app" / "chroma_db" / "chroma.sqlite3").touch()
        mark_index_current()
        self.assertTrue(index_is_current())
        save_document("notes.txt", "two")
        self.assertFalse(index_is_current())

    def test_batch_delete_removes_copies_and_reports_missing_files(self) -> None:
        original = self.home / "original.md"
        original.write_text("keep me", encoding="utf-8")
        import_document(original)
        save_document("other.txt", "delete me", create=True)
        result = delete_documents(["original.md", "missing.txt", "other.txt", "original.md"])
        self.assertEqual(result.deleted, ("original.md", "other.txt"))
        self.assertEqual([name for name, _ in result.failed], ["missing.txt"])
        self.assertEqual(list_documents(), [])
        self.assertEqual(original.read_text(encoding="utf-8"), "keep me")

    @unittest.skipUnless(os.name == "nt", "Windows application data compatibility")
    def test_existing_library_is_reused_after_rename(self) -> None:
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.home)}):
            os.environ.pop("RAG_HOME", None)
            old_home = self.home / "LocalRAGKnowledgeBase"
            old_home.mkdir()
            self.assertEqual(app_home(), old_home)
            new_home = self.home / APP_NAME
            new_home.mkdir()
            self.assertEqual(app_home(), new_home)


if __name__ == "__main__":
    unittest.main()
