import unittest

import pymupdf

from pdfpages2md.extract import extract_pages, render


def _make_doc(path, n=20):
    doc = pymupdf.open()
    try:
        for i in range(n):
            page = doc.new_page()
            page.insert_text(
                (72, 72),
                f"page {i + 1} content " + "lorem ipsum dolor sit amet " * 4,
            )
        doc.save(path)
    finally:
        doc.close()


class ExtractTests(unittest.TestCase):
    def test_only_selected_pages_are_returned(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "doc.pdf")
            _make_doc(path)
            result = extract_pages(path, "2,4-5")
            self.assertEqual([p.page for p in result.pages], [2, 4, 5])
            self.assertEqual(result.total_pages, 20)

    def test_marker_is_preserved(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "doc.pdf")
            _make_doc(path)
            md = render(extract_pages(path, "3"), fmt="markdown", marker="comment")
            self.assertIn("<!-- page 3 -->", md)

    def test_out_of_range_is_rejected(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "doc.pdf")
            _make_doc(path, n=10)
            with self.assertRaises(ValueError):
                extract_pages(path, "11")

    def test_image_placeholder_is_present(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "with_image.pdf")
            doc = pymupdf.open()
            try:
                page = doc.new_page(width=400, height=300)
                page.insert_text((72, 60), "lorem ipsum dolor sit amet " * 4)
                pix = page.get_pixmap(dpi=72)
                page.insert_image(pymupdf.Rect(72, 120, 200, 220), pixmap=pix)
                doc.save(path)
            finally:
                doc.close()

            result = extract_pages(path, "1")
            self.assertGreaterEqual(result.pages[0].images, 1)
            md = render(result, fmt="markdown", marker="none")
            self.assertIn("<!-- 此处为图片 -->", md)

    def test_translate_uses_injected_translator_and_keeps_marker(self):
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "doc.pdf")
            _make_doc(path)
            result = extract_pages(
                path,
                "3",
                translate=True,
                translator=lambda text: f"译:{text}",
            )
            self.assertTrue(result.pages[0].translated)
            self.assertIn("译:", result.pages[0].translated_markdown)
            md = render(result, fmt="markdown", marker="comment")
            self.assertIn("<!-- page 3 -->", md)
            self.assertIn("译:", md)


if __name__ == "__main__":
    unittest.main()
