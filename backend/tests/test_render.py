import json
import unittest

from pdfpages2md.models import ConvertResult, PageResult
from pdfpages2md.render import render, render_page


def _page(**overrides):
    values = {
        "page": 7,
        "markdown": "# Title\n\nBody text.",
        "text": "Title\n\nBody text.",
        "scanned": False,
    }
    values.update(overrides)
    return PageResult(**values)


def _result(pages=None):
    pages = pages or [_page()]
    return ConvertResult(
        source="book.pdf",
        total_pages=42,
        selected_pages=[page.page for page in pages],
        pages=pages,
    )


class MarkerTests(unittest.TestCase):
    def test_comment_marker(self):
        md = render(_result(), fmt="markdown", marker="comment")
        self.assertTrue(md.startswith("<!-- page 7 -->"))
        self.assertIn("# Title", md)

    def test_heading_marker(self):
        md = render(_result(), fmt="markdown", marker="heading")
        self.assertIn("## Page 7", md)
        self.assertNotIn("<!-- page 7 -->", md)

    def test_both_and_none_markers(self):
        both = render(_result(), fmt="markdown", marker="both")
        self.assertIn("<!-- page 7 -->", both)
        self.assertIn("## Page 7", both)

        none = render(_result(), fmt="markdown", marker="none")
        self.assertNotIn("page 7", none)

    def test_unknown_marker_is_rejected(self):
        with self.assertRaises(ValueError):
            render(_result(), fmt="markdown", marker="bogus")


class ImageAndNoteTests(unittest.TestCase):
    def test_single_image_placeholder(self):
        md = render(_result([_page(images=1)]), fmt="markdown")
        self.assertIn("<!-- 此处为图片 -->", md)

    def test_multiple_images_placeholder_counts(self):
        md = render(_result([_page(images=3)]), fmt="markdown")
        self.assertIn("<!-- 此处为图片 (共 3 张) -->", md)

    def test_text_format_uses_bracketed_placeholder(self):
        rendered = render(_result([_page(images=2)]), fmt="text", marker="none")
        self.assertIn("[此处为图片 (共 2 张)]", rendered)
        self.assertNotIn("<!--", rendered)

    def test_note_is_rendered_as_comment(self):
        md = render(_result([_page(note="vision fallback failed")]), fmt="markdown")
        self.assertIn("<!-- note: vision fallback failed -->", md)


class FormatTests(unittest.TestCase):
    def test_translated_body_is_preferred(self):
        page = _page(
            translated=True,
            translated_markdown="译文",
            translated_text="译文",
        )
        self.assertIn("译文", render(_result([page]), fmt="markdown"))
        self.assertIn("译文", render(_result([page]), fmt="text"))

    def test_json_has_stable_top_level_shape(self):
        payload = json.loads(render(_result(), fmt="json"))
        self.assertEqual(
            list(payload),
            ["source", "total_pages", "selected_pages", "pages"],
        )
        self.assertEqual(payload["pages"][0]["page"], 7)
        self.assertEqual(payload["selected_pages"], [7])

    def test_unsupported_format_is_rejected(self):
        with self.assertRaises(ValueError):
            render(_result(), fmt="html")

    def test_sections_render_one_block_per_page(self):
        result = _result([_page(page=1), _page(page=2)])
        sections = result.sections(fmt="markdown", marker="comment")
        self.assertEqual(len(sections), 2)
        self.assertIn("<!-- page 1 -->", sections[0])
        self.assertIn("<!-- page 2 -->", sections[1])

    def test_render_page_returns_page_only(self):
        page = _page(page=3)
        rendered = render_page(page, fmt="markdown", marker="comment")
        self.assertTrue(rendered.startswith("<!-- page 3 -->"))


if __name__ == "__main__":
    unittest.main()
