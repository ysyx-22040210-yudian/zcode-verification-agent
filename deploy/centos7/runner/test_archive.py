"""Import, source-grounding and recovery through the same API used by MCP."""
import concurrent.futures
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
import knowledge
import model_archive
from manual_import import import_manual


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.library = root / "library"
        self.binding = patch.object(knowledge, "LIBRARY", self.library)
        self.binding.start()
        self.pdf = root / "guide.pdf"
        doc = fitz.open()
        for number in range(1, model_archive.BATCH_SIZE + 2):
            page = doc.new_page()
            page.insert_text((60, 70), "Design guide page {}: fifo_clock samples incoming data.".format(number))
        doc.save(str(self.pdf))
        doc.close()
        self.source = import_manual(self.pdf, self.library)
        self.ref = {"sourceId": self.source["id"], "sha256": self.source["sha256"]}
        self.topic = {"title": "Clock sampling", "keywords": ["采样时刻", "fifo_clock"],
                      "summary": "The clock samples incoming data.", "page": 2,
                      "quote": "fifo_clock samples incoming data."}

    def tearDown(self):
        self.binding.stop()
        self.temp.cleanup()

    def test_duplicate_bytes_version_identity_and_retention(self):
        renamed = self.pdf.with_name("another name.pdf")
        renamed.write_bytes(self.pdf.read_bytes())
        self.assertEqual(import_manual(renamed, self.library)["id"], self.ref["sourceId"])
        doc = fitz.open()
        doc.new_page()
        doc.save(str(renamed.with_name("new.pdf")))
        doc.close()
        self.pdf.write_bytes(renamed.with_name("new.pdf").read_bytes())
        other = import_manual(self.pdf, self.library)
        self.assertNotEqual(other["id"], self.ref["sourceId"])
        _, folder = knowledge.resolve(self.ref["sourceId"])
        self.assertEqual((folder / "source.pdf").read_bytes(), renamed.read_bytes())

    def test_resume_concurrent_retry_search_and_original_review(self):
        batch = model_archive.next_batch(self.ref)
        self.assertEqual([row["page"] for row in batch["pages"]], list(range(1, model_archive.BATCH_SIZE + 1)))
        save = dict(self.ref, firstPage=1, topics=[self.topic], reviewPages=[])
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(model_archive.save_batch, [save, save]))
        for result in results:
            self.assertEqual(result["filedPages"], model_archive.BATCH_SIZE)
        self.assertEqual(model_archive.next_batch(self.ref)["firstPage"], model_archive.BATCH_SIZE + 1)
        hit = knowledge.search(dict(self.ref, query="采样时刻"))["results"][0]
        self.assertEqual((hit["page"], hit["origin"]), (2, "model_guide"))
        last = model_archive.BATCH_SIZE + 1
        state = model_archive.save_batch(dict(self.ref, firstPage=last, topics=[], reviewPages=[last]))
        self.assertEqual((state["status"], state["reviewCount"]), ("needs_review", 1))
        self.assertTrue(model_archive.next_batch(self.ref)["done"])
        self.assertEqual(model_archive.guide(self.ref)["topics"], [self.topic])
        self.assertEqual(model_archive.guide(self.ref)["reviewPages"], [last])

    def test_bad_citations_stale_digest_and_out_of_order_leave_progress_pending(self):
        for data in (dict(self.ref, firstPage=2), dict(self.ref, sha256="invalid", firstPage=1)):
            with self.assertRaises(ValueError):
                model_archive.save_batch(dict(data, topics=[self.topic], reviewPages=[]))
        for bad in (dict(self.topic, page=99999), dict(self.topic, quote="invented quote")):
            with self.assertRaises(ValueError):
                model_archive.save_batch(dict(self.ref, firstPage=1, topics=[bad], reviewPages=[]))
        self.assertEqual(model_archive.next_batch(self.ref)["firstPage"], 1)

    def test_image_only_page_requires_review_or_verified_original(self):
        pdf = self.pdf.with_name("diagram.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.draw_rect(fitz.Rect(48, 48, 180, 90))
        doc.save(str(pdf))
        doc.close()
        s = import_manual(pdf, self.library)
        ref = {"sourceId": s["id"], "sha256": s["sha256"]}
        visual = {"title": "Diagram", "summary": "The diagram shows a box.", "page": 1,
                  "keywords": ["示意图"], "visual": True}
        pending = dict(ref, firstPage=1, topics=[], reviewPages=[1])
        self.assertEqual(model_archive.save_batch(pending)["status"], "needs_review")
        with self.assertRaisesRegex(ValueError, "originalEvidence"):
            model_archive.save_batch(dict(pending, reviewOnly=True, topics=[visual], reviewPages=[]))
        with patch.object(knowledge, "read_pages", return_value=[{"page": 1, "images": [{"mimeType": "image/png"}]}]):
            token = knowledge.read_original(dict(ref, page=1))["pages"][0]["originalEvidence"]
        filed = model_archive.save_batch(dict(pending, reviewOnly=True, topics=[dict(visual, originalEvidence=token)],
                                              reviewPages=[]))
        self.assertEqual((filed["status"], filed["reviewCount"]), ("filed", 0))
        self.assertEqual(model_archive.guide(ref)["topics"][0], visual)

