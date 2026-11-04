import os
import tempfile
import unittest

import pymupdf

from pdfpages2md.code import extract_code_markdown
from pdfpages2md.extract import extract_pages, render

from .make_code_sample import build


def _make_split_span_pdf(path):
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text((88, 72), "Code Listing", fontsize=12, fontname="tiro")
        rows = [
            [(72, "1"), (100, "#include"), (150, "<stdio.h>")],
            [(72, "2"), (100, "int")],
            [(72, "3"), (100, "main(int argc, char *argv[])")],
            [(72, "4"), (100, "{")],
            [(72, "5"), (123, "if (argc != 2) {")],
            [(72, "6"), (145, 'printf("hi");')],
            [(72, "7"), (123, "}")],
            [(72, "8"), (123, "return 0;")],
            [(72, "9"), (100, "}")],
        ]
        for index, row in enumerate(rows):
            y = 110 + index * 14
            for x, text in row:
                page.insert_text((x, y), text, fontname="cour", fontsize=9.5)
        doc.save(path)
    finally:
        doc.close()


def _make_inline_number_pdf(path):
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=612, height=792)
        lines = [
            "1 #include <stdio.h>",
            "2 #include <stdlib.h>",
            "3 int main(int argc, char *argv[])",
            "4 {",
            "5     if (argc != 2) {",
            "6         return 1;",
            "7     }",
            "8     return 0;",
            "9 }",
        ]
        for index, line in enumerate(lines):
            page.insert_text(
                (90, 110 + index * 14),
                line,
                fontname="cour",
                fontsize=9.5,
            )
        doc.save(path)
    finally:
        doc.close()


class CodeExtractionTests(unittest.TestCase):
    def test_line_numbers_and_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "code.pdf")
            build(path)
            with pymupdf.open(path) as doc:
                markdown = extract_code_markdown(doc[0])
            self.assertIsNotNone(markdown)
            self.assertIn("```c", markdown)
            self.assertIn("#include <stdlib.h>", markdown)
            self.assertIn("    if (argc != 2) {", markdown)
            self.assertIn("        fprintf(stderr", markdown)
            self.assertIn("    return 0;", markdown)
            self.assertNotIn("\n1 #include", markdown)

    def test_split_spans_and_positional_indent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "split.pdf")
            _make_split_span_pdf(path)
            with pymupdf.open(path) as doc:
                markdown = extract_code_markdown(doc[0])
            self.assertIsNotNone(markdown)
            self.assertIn("#include <stdio.h>", markdown)
            self.assertIn("    if (argc != 2) {", markdown)
            self.assertIn('        printf("hi");', markdown)
            self.assertIn("    return 0;", markdown)

    def test_prose_page_is_not_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prose.pdf")
            doc = pymupdf.open()
            try:
                page = doc.new_page()
                page.insert_text(
                    (72, 72),
                    "This is ordinary prose about operating systems.",
                    fontname="tiro",
                )
                doc.save(path)
            finally:
                doc.close()
            with pymupdf.open(path) as doc:
                self.assertIsNone(extract_code_markdown(doc[0]))

    def test_inline_sequential_numbers_are_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "inline.pdf")
            _make_inline_number_pdf(path)
            with pymupdf.open(path) as doc:
                markdown = extract_code_markdown(doc[0])
            self.assertIsNotNone(markdown)
            self.assertIn("#include <stdio.h>", markdown)
            self.assertIn("    if (argc != 2) {", markdown)
            self.assertNotIn("1 #include", markdown)

    def test_translation_leaves_code_fence_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "code.pdf")
            build(path)
            result = extract_pages(
                path,
                "1",
                translate=True,
                translator=lambda text: "译:" + text,
            )
            markdown = render(result, fmt="markdown", marker="none")
            self.assertIn("```c\n#include <stdio.h>", markdown)
            self.assertNotIn("译:#include", markdown)
            self.assertIn("译:INTRODUCTION", markdown)


if __name__ == "__main__":
    unittest.main()
