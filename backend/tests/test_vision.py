import json
import os
import tempfile
import unittest
from unittest import mock

import pymupdf

from pdfpages2md.extract import extract_pages
from pdfpages2md.ocr import OcrLine
from pdfpages2md.vision import (
    should_use_vision,
    vision_page_markdown,
)

from .make_code_sample import build


def _ocr_line(text, score=0.9):
    return OcrLine(
        text=text,
        x0=100,
        y0=100,
        x1=300,
        y1=130,
        score=score,
    )


def _ocr_line_at(text, y0, score=0.9):
    return OcrLine(
        text=text,
        x0=100,
        y0=y0,
        x1=300,
        y1=y0 + 30,
        score=score,
    )


class VisionHeuristicTests(unittest.TestCase):
    def test_code_fence_requests_vision(self):
        self.assertTrue(
            should_use_vision("```c\nint main() {}\n```", [_ocr_line("int")])
        )

    def test_table_requests_vision(self):
        markdown = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        self.assertTrue(should_use_vision(markdown, [_ocr_line("A")]))

    def test_low_confidence_requests_vision(self):
        lines = [_ocr_line("garbled", 0.4), _ocr_line("text", 0.5)]
        self.assertTrue(should_use_vision("ordinary text", lines))

    def test_clean_prose_does_not_request_vision(self):
        lines = [_ocr_line("This is ordinary prose.", 0.95)]
        self.assertFalse(should_use_vision("This is ordinary prose.", lines))


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(
            {
                "choices": [
                    {"message": {"content": "```c\nint main() {}\n```"}}
                ]
            }
        ).encode("utf-8")


class VisionBackendTests(unittest.TestCase):
    def test_request_contains_image_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "code.pdf")
            build(path)
            with pymupdf.open(path) as doc:
                with mock.patch(
                    "pdfpages2md.vision._config",
                    side_effect=lambda name, default="": {
                        "VISION_API_KEY": "sk-test",
                        "VISION_BASE_URL": "https://example.com/v1",
                        "VISION_MODEL": "glm-4v-flash",
                    }.get(name, default),
                ):
                    with mock.patch(
                        "urllib.request.urlopen", return_value=FakeResponse()
                    ) as urlopen:
                        result = vision_page_markdown(doc[0], dpi=72)
            self.assertIn("int main", result)
            request = urlopen.call_args[0][0]
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["model"], "glm-4v-flash")
            image_url = payload["messages"][1]["content"][0]["image_url"]["url"]
            self.assertTrue(image_url.startswith("data:image/png;base64,"))

    def test_extract_uses_injected_vision_transcriber_for_code_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "code.pdf")
            build(path)
            ocr_lines = [
                _ocr_line_at("#include <stdio.h>", 100),
                _ocr_line_at("int main()", 130),
                _ocr_line_at("return 0;", 160),
            ]
            with mock.patch(
                "pdfpages2md.extract.is_scanned", return_value=True
            ), mock.patch(
                "pdfpages2md.extract.ocr_page_layout",
                return_value=(ocr_lines, "\n".join(l.text for l in ocr_lines), "fake"),
            ):
                result = extract_pages(
                    path,
                    "1",
                    vision_transcriber=lambda page: "```c\nint main() {}\n```",
                )
            self.assertTrue(result.pages[0].used_vision)
            self.assertIn("int main()", result.pages[0].markdown)


if __name__ == "__main__":
    unittest.main()
