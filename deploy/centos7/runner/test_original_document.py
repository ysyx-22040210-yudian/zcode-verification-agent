"""Regressions for original PDF tool errors and Agent image limits."""
import base64
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import time

import original_document


class OriginalDocumentTests(unittest.TestCase):
    def test_missing_renderer_has_an_explicit_error(self):
        with patch.object(original_document.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "pdftoppm and pdftotext"):
                original_document.read_pages(Path("source.pdf"), 1, 1)

    def test_text_mode_reads_layout_without_a_renderer(self):
        with patch.object(original_document.shutil, "which", side_effect=lambda tool: tool if tool == "pdftotext" else None), \
                patch.object(original_document, "command", return_value=b"clk   0    1") as run:
            pages = original_document.read_pages(Path("source.pdf"), 2, 2, include_images=False)
        self.assertEqual(run.call_count, 1)
        self.assertIn("-layout", run.call_args[0][0])
        self.assertEqual(pages, [{"page": 2, "text": "clk   0    1", "textTruncated": False, "images": []}])

    def test_timeout_is_an_explicit_tool_error(self):
        with self.assertRaisesRegex(ValueError, "timed out"):
            original_document.command(["renderer"], time.monotonic() - 1)

    def test_oversized_page_preserves_full_resolution_in_bounded_regions(self):
        def renderer(arguments, deadline):
            cropped = "-x" in arguments
            width = int(arguments[arguments.index("-W") + 1]) if cropped else 1200
            height = int(arguments[arguments.index("-H") + 1]) if cropped else 1600
            header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height)
            data = header + b"x" * (1024 if cropped else 200 * 1024)
            Path(arguments[-1]).with_suffix(".png").write_bytes(data)
            return b""

        with tempfile.TemporaryDirectory() as folder:
            with patch.object(original_document, "command", side_effect=renderer):
                result = original_document.render_images("renderer", Path("source.pdf"), 7,
                                                         Path(folder), time.monotonic() + 10)
        self.assertEqual((result["width"], result["height"]), (1200, 1600))
        regions = [image["region"] for image in result["images"]]
        self.assertEqual(regions, [{"x": 0, "y": 0, "width": 1200, "height": 800},
                                   {"x": 0, "y": 800, "width": 1200, "height": 800}])
        self.assertTrue(all(len(base64.b64decode(image["data"])) <= original_document.INLINE_IMAGE_BYTES
                            for image in result["images"]))


if __name__ == "__main__":
    unittest.main()
