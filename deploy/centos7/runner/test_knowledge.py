"""Boundary and retrieval regressions for the native knowledge adapter."""
import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import knowledge
import mcp


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.library = Path(self.directory.name)
        self.binding = patch.object(knowledge, "LIBRARY", self.library)
        self.binding.start()
        generation = "documents/" + "a" * 32
        self.generation = self.library / generation
        self.generation.mkdir(parents=True)
        self.source = {
            "id": "vc-apps-npi", "title": "Example manual", "version": "1.0",
            "pageCount": 2, "sha256": hashlib.sha256(b"%PDF-1.7").hexdigest(), "generation": generation,
            "pdfBytes": 8, "chapters": [],
        }
        (self.library / "catalog.json").write_text(json.dumps({"format": 1, "sources": [self.source]}))
        (self.generation / "source.pdf").write_bytes(b"%PDF-1.7")
        connection = sqlite3.connect(str(self.generation / "index.sqlite3"))
        connection.executescript("""
            CREATE TABLE pages(page INTEGER PRIMARY KEY, label TEXT, section TEXT, text TEXT);
            CREATE VIRTUAL TABLE search USING fts4(heading, text, tokenize=simple);
            INSERT INTO pages VALUES(1, 'i', 'API', 'int npi_init(int argc, char** argv);');
            INSERT INTO pages VALUES(2, '1', 'FSDB', 'npi_fsdb_open opens an FSDB file.');
            INSERT INTO search(docid, heading, text) SELECT page, section, text FROM pages;
        """)
        connection.close()

    def tearDown(self):
        self.binding.stop()
        self.directory.cleanup()

    def test_exact_api_and_chinese_topic_return_cited_pages(self):
        for query, page in (("npi_fsdb_open()", 2), ("初始化", 1)):
            result = knowledge.search({"query": query, "sourceId": "vc-apps-npi"})
            self.assertEqual(result["results"][0]["page"], page)
            self.assertEqual(result["results"][0]["version"], "1.0")
        self.assertEqual(knowledge.search({"query": "unmatchedterm"})["total"], 0)

    def test_read_preserves_source_labels_and_neighbor_pages(self):
        result = knowledge.read({"sourceId": "vc-apps-npi", "page": 1, "count": 3})
        self.assertEqual([item["page"] for item in result["pages"]], [1, 2])
        self.assertEqual(result["pages"][0]["pageLabel"], "i")
        self.assertNotIn("generation", result["source"])

    def test_invalid_selection_and_range_are_rejected(self):
        for request in (
            {"sourceId": "../example", "page": 1},
            {"sourceId": "vc-apps-npi", "sha256": "changed", "page": 1},
            {"sourceId": "vc-apps-npi", "page": True},
            {"sourceId": "vc-apps-npi", "page": 0},
            {"sourceId": "vc-apps-npi", "page": 3},
            {"sourceId": "vc-apps-npi", "page": 1, "count": 4},
        ):
            with self.assertRaises(ValueError):
                knowledge.read(request)
        for offset, length in ((-1, 4), (8, 4), (0, 0), (0, 2 * 1024 * 1024)):
            with self.assertRaises(ValueError):
                knowledge.pdf_range({"sourceId": "vc-apps-npi", "offset": offset, "length": length})
        self.assertEqual(knowledge.pdf_range({"sourceId": "vc-apps-npi", "offset": 0, "length": 4}),
                         {"base64": "JVBERg=="})

    def test_missing_and_corrupt_indexes_are_errors(self):
        index = self.generation / "index.sqlite3"
        index.write_bytes(b"invalid sqlite data")
        with self.assertRaises(sqlite3.DatabaseError):
            knowledge.read({"sourceId": "vc-apps-npi", "page": 1})
        index.unlink()
        with self.assertRaises(ValueError):
            knowledge.read({"sourceId": "vc-apps-npi", "page": 1})

    def test_query_operators_are_literals_and_limit_is_bounded(self):
        self.assertEqual(knowledge.search({"query": 'npi_fsdb_open" OR absent'})["total"], 0)
        for request in ({"query": ""}, {"query": "x" * 301}, {"query": "fsdb", "limit": 51}):
            with self.assertRaises(ValueError):
                knowledge.search(request)

    def test_empty_library_is_discoverable(self):
        (self.library / "catalog.json").unlink()
        self.assertEqual(knowledge.dispatch("knowledgeList", {}), [])
        self.assertEqual(knowledge.search({"query": "fsdb"})["results"], [])

    def test_original_document_read_works_without_the_text_index(self):
        (self.generation / "index.sqlite3").unlink()
        pages = [{"page": 2, "text": "Original source content", "images": []}]
        with patch.object(knowledge, "read_pages", return_value=pages) as renderer:
            result = knowledge.dispatch("knowledgeOriginal", {"sourceId": "vc-apps-npi", "page": 2})
        renderer.assert_called_once_with(self.generation / "source.pdf", 2, 2, include_images=True)
        self.assertEqual(result["origin"], "original_pdf")
        self.assertEqual(result["pages"][0]["text"], "Original source content")
        self.assertEqual(result["source"]["originalPath"], str(self.generation / "source.pdf"))

    def test_text_only_original_has_no_visual_evidence(self):
        with patch.object(knowledge, "read_pages", return_value=[{"page": 2, "text": "API", "images": []}]) as read:
            result = knowledge.read_original({"sourceId": "vc-apps-npi", "page": 2, "includeImages": False})
        read.assert_called_once_with(self.generation / "source.pdf", 2, 2, include_images=False)
        self.assertNotIn("originalEvidence", result["pages"][0])
        self.assertEqual(result["pages"][0]["text"], "API")

    def test_mcp_original_follows_each_calls_model_and_hides_visual_receipts(self):
        args = {"sourceId": "vc-apps-npi", "page": 2}
        page = {"page": 2, "text": "clk", "originalEvidence": "test-receipt",
                "images": [{"mimeType": "image/png", "data": "cG5n", "region": {}}]}
        for capability in (None, False, True, False, "true"):
            meta = {} if capability is None else {"com.zcode/request-context": {"model_supports_image": capability}}
            with patch.object(mcp, "call", return_value={"pages": [page]}) as send:
                result = mcp.dispatch("tools/call", {"name": "knowledge_read_original", "arguments": args,
                                                     "_meta": meta}, str(self.directory.name))
            self.assertIs(send.call_args[0][1]["includeImages"], capability is True)
            self.assertEqual(any(b["type"] == "image" for b in result["content"]), capability is True)
            self.assertEqual("test-receipt" in result["content"][-1]["text"], capability is True)
            self.assertNotIn("cG5n", result["content"][-1]["text"])

    def test_text_model_cannot_reuse_a_visual_receipt_from_history(self):
        args = {"sourceId": "vc-apps-npi", "sha256": "test", "firstPage": 1, "reviewPages": [],
                "topics": [{"visual": True, "originalEvidence": "earlier-turn"}]}
        with patch.object(mcp, "call") as send:
            result = mcp.dispatch("tools/call", {"name": "knowledge_archive_save", "arguments": args}, ".")
        self.assertTrue(result["isError"])
        send.assert_not_called()

    def test_original_document_rejects_invalid_pages_and_changed_pdf(self):
        for request in ({"sourceId": "vc-apps-npi", "page": 0},
                        {"sourceId": "vc-apps-npi", "page": 3},
                        {"sourceId": "vc-apps-npi", "page": 1, "count": 4}):
            with self.assertRaises(ValueError):
                knowledge.read_original(request)
        (self.generation / "source.pdf").write_bytes(b"%PDF-1.8")
        with self.assertRaisesRegex(ValueError, "digest"):
            knowledge.read_original({"sourceId": "vc-apps-npi", "page": 1})


if __name__ == "__main__":
    unittest.main()
