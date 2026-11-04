import unittest

from pdfpages2md.ocr import OcrLine
from pdfpages2md.ocr_layout import reconstruct_ocr_markdown


def _line(text, x0, y0, x1=None, y1=None, height=30.0):
    return OcrLine(
        text=text,
        x0=x0,
        y0=y0,
        x1=x1 if x1 is not None else x0 + 200,
        y1=y1 if y1 is not None else y0 + height,
        score=0.9,
    )


def _code_page_lines():
    lines = [
        _line("INTRODUCTION TO SYSTEMS PROGRAMMING", 259, 233),
        _line("#include <stdio.h>", 258, 323),
        _line("#include <stdlib.h>", 258, 360),
        _line("int", 255, 430),
        _line("main(int argc, char *argv[])", 253, 466),
        _line("{", 253, 502),
        _line("10", 193, 538),
        _line("if", 333, 534),
        _line("（argc != 2）{", 389, 534),
        _line("11", 193, 574),
        _line('fprintf(stderr, "usage: square <number>\\n");', 412, 570),
        _line("12", 192, 610),
        _line("return 1;", 413, 606),
        _line("13", 192, 646),
        _line("}", 333, 642),
        _line("14", 192, 682),
        _line("int value = atoi(argv[l]);", 333, 678),
        _line("15", 192, 718),
        _line('printf("%d squared is %d\\n"， value, value * value);', 409, 714),
        _line("16", 192, 754),
        _line("return ;", 333, 750),
        _line("17", 192, 790),
        _line("}", 253, 786),
        _line("Figure 2.1: Example: A Small Squaring Program", 294, 1090),
        _line("2.1 Building And Running Programs", 178, 1149, height=39),
        _line(
            "Figure 2.1 shows a small program that squares a number.",
            298,
            1221,
            height=33,
        ),
    ]
    return lines


class OcrLayoutTests(unittest.TestCase):
    def test_code_region_is_fenced_and_repaired(self):
        markdown = reconstruct_ocr_markdown(_code_page_lines())
        self.assertIn("```c", markdown)
        self.assertIn("#include <stdlib.h>", markdown)
        self.assertIn("if (argc != 2) {", markdown)
        self.assertIn("int value = atoi(argv[1]);", markdown)
        self.assertIn(
            'printf("%d squared is %d\\n", value, value * value);',
            markdown,
        )
        self.assertIn("return 0;", markdown)
        self.assertEqual(markdown.count("{"), markdown.count("}"))
        self.assertNotIn("\n10 ", markdown)
        self.assertIn("## 2.1 Building And Running Programs", markdown)

    def test_prose_only_page_has_no_fence(self):
        lines = [
            _line("This is ordinary prose about operating systems.", 200, 200, height=33),
            _line("It continues on the next line.", 200, 240, height=33),
        ]
        markdown = reconstruct_ocr_markdown(lines)
        self.assertNotIn("```", markdown)
        self.assertIn("ordinary prose", markdown)

    def test_shell_output_stays_inside_fence(self):
        lines = [
            _line(
                "prompt> ./job A & ./job B & ./job C & ./job D &",
                353,
                319,
                height=38,
            ),
            _line("[1] 7353", 361, 357, height=35),
            _line("[2]", 360, 394, height=33),
            _line("7354", 430, 395, height=28),
            _line("[3]", 360, 430, height=34),
            _line("7355", 432, 431, height=28),
            _line("7356", 433, 467, height=28),
            _line("Figure 2.2: Running Many Programs At Once", 546, 871),
        ]
        markdown = reconstruct_ocr_markdown(lines)
        self.assertIn("```shell", markdown)
        fenced = markdown.split("```shell", 1)[1].split("```", 1)[0]
        self.assertIn("[1] 7353", fenced)
        self.assertIn("[2] 7354", fenced)
        self.assertIn("[3] 7355", fenced)
        self.assertIn("[4] 7356", fenced)
        self.assertNotIn("Figure 2.2", fenced)


if __name__ == "__main__":
    unittest.main()
