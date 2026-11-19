"""A file is staged in the app namespace; the runner may index it after a restart."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
import knowledge
import knowledge_import as imports


class ImportReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for owner, name, value in ((imports, "INBOX", self.root / "inbox"), (knowledge, "LIBRARY", self.root / "library")):
            bound = patch.object(owner, name, value)
            bound.start()
            self.addCleanup(bound.stop)

    def test_pending_snapshot_import_survives_source_removal_and_status_retry(self):
        pdf = self.root / "two words.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()
        original = pdf.read_bytes()
        job = imports.stage(pdf.name, str(self.root))
        pdf.unlink()
        imports.resume_pending()
        result = imports.status(job, wait=10)
        self.assertEqual(result["status"], "indexed")
        self.assertEqual(imports.status(job), result)
        _, directory = knowledge.resolve(result["sourceId"], result["sha256"])
        self.assertEqual((directory / "source.pdf").read_bytes(), original)
        self.assertFalse((imports.INBOX / job / "input.pdf").exists())

    def test_bad_input_does_not_publish_and_retains_failure_receipt(self):
        pdf = self.root / "broken.pdf"
        pdf.write_bytes(b"wrong format")
        with self.assertRaisesRegex(ValueError, "PDF header"):
            imports.stage(str(pdf), str(self.root))
        pdf.write_bytes(b"%PDF-1.4\ninvalid body")
        job = imports.stage(str(pdf), str(self.root))
        result = imports.status(job, wait=10)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["error"])
        self.assertEqual(knowledge.catalog(), [])
        self.assertEqual(imports.status(job), result)

