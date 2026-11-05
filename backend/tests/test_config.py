import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pdfpages2md.config import get_config, load_dotenv


class DotenvTests(unittest.TestCase):
    def test_parses_quotes_and_skips_comments_and_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "PLAIN=one\n"
                "# comment\n"
                "\n"
                'DQ="two words"\n'
                "SQ='three'\n"
                "NO_EQUALS\n"
                "= empty-key\n",
                encoding="utf-8",
            )
            values = load_dotenv([env_file])
        self.assertEqual(
            values,
            {"PLAIN": "one", "DQ": "two words", "SQ": "three"},
        )

    def test_earlier_file_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.env"
            second = Path(tmp) / "second.env"
            first.write_text("KEY=first\n", encoding="utf-8")
            second.write_text("KEY=second\nOTHER=only\n", encoding="utf-8")
            values = load_dotenv([first, second])
        self.assertEqual(values["KEY"], "first")
        self.assertEqual(values["OTHER"], "only")


class GetConfigTests(unittest.TestCase):
    def test_environment_wins_over_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("PDF_REFACTOR_TEST_KEY=from-file\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ, {"PDF_REFACTOR_TEST_KEY": "from-env"}
            ):
                value = get_config("PDF_REFACTOR_TEST_KEY", candidates=[env_file])
        self.assertEqual(value, "from-env")

    def test_dotenv_used_when_environment_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("PDF_REFACTOR_TEST_KEY=from-file\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PDF_REFACTOR_TEST_KEY": "  "}):
                value = get_config("PDF_REFACTOR_TEST_KEY", candidates=[env_file])
        self.assertEqual(value, "from-file")

    def test_default_is_returned_when_nothing_is_configured(self):
        value = get_config("PDF_REFACTOR_TEST_ABSENT", "fallback", candidates=[])
        self.assertEqual(value, "fallback")


if __name__ == "__main__":
    unittest.main()
