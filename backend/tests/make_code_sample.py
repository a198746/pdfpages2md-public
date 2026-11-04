"""Generate a small code-listing PDF for layout-preservation tests."""

from __future__ import annotations

from pathlib import Path

import pymupdf


CODE_LINES = [
    "#include <stdio.h>",
    "#include <stdlib.h>",
    "",
    "int",
    "main(int argc, char *argv[])",
    "{",
    "    if (argc != 2) {",
    '        fprintf(stderr, "usage: square <number>\\n");',
    "        return 1;",
    "    }",
    "",
    "    int value = atoi(argv[1]);",
    '    printf("%d squared is %d\\n", value, value * value);',
    "    return 0;",
    "}",
]


def build(path: str | Path) -> Path:
    path = Path(path)
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=612, height=792)  # US Letter
        page.insert_text(
            (88, 72),
            "INTRODUCTION TO SYSTEMS PROGRAMMING",
            fontsize=12,
            fontname="tiro",
        )
        page.insert_text((470, 72), "3", fontsize=12, fontname="tiro")
        page.draw_line((88, 78), (524, 78), width=0.8)

        first_y = 112
        line_height = 14
        for index, line in enumerate(CODE_LINES, start=1):
            y = first_y + (index - 1) * line_height
            page.insert_text(
                (84, y),
                str(index),
                fontsize=8,
                fontname="cour",
            )
            page.insert_text(
                (112, y),
                line,
                fontsize=9.5,
                fontname="cour",
            )
        doc.save(str(path))
    finally:
        doc.close()
    return path


if __name__ == "__main__":
    target = Path(__file__).with_name("code_sample.pdf")
    build(target)
    print(f"wrote {target}")
