import unittest
import tempfile
from pathlib import Path
from unittest import mock

from pdfpages2md.translate import (
    TranslationUnavailableError,
    _chunk,
    _config,
    _deepseek,
    translate_markdown,
    translate_text,
)


def _bracket(text: str) -> str:
    return f"[{text}]"


class TranslateTextTests(unittest.TestCase):
    def test_injected_translator_is_used(self):
        self.assertEqual(translate_text("hello", translator=_bracket), "[hello]")

    def test_empty_text_is_untouched(self):
        self.assertEqual(translate_text("   ", translator=_bracket), "")

    def test_auto_engine_uses_first_backend(self):
        with mock.patch(
            "pdfpages2md.translate._BACKENDS",
            [("fake", lambda text, source, target: f"[{text}]")],
        ):
            self.assertEqual(translate_text("hello", engine="auto"), "[hello]")

    def test_chunk_stays_within_limit(self):
        chunks = _chunk("One. " * 60, limit=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 50 for chunk in chunks))


class TranslateMarkdownTests(unittest.TestCase):
    def test_preserves_heading_and_paragraphs(self):
        source = "# **Report**\n\nThis is the body."
        out = translate_markdown(source, translator=_bracket)
        self.assertIn("# [**Report**]", out)
        self.assertIn("[This is the body.]", out)

    def test_preserves_list_markers(self):
        source = "- first item\n- second item\n\n1. one\n2. two"
        out = translate_markdown(source, translator=_bracket)
        self.assertIn("- [first item]", out)
        self.assertIn("1. [one]", out)

    def test_preserves_table_separator_and_cells(self):
        source = "| Name | Age |\n| --- | --- |\n| Alice | 30 |"
        out = translate_markdown(source, translator=_bracket)
        self.assertIn("| [Name] | [Age] |", out)
        self.assertIn("| --- | --- |", out)
        self.assertIn("| [Alice] | [30] |", out)

    def test_preserves_blockquote_code_and_rule(self):
        source = "> quoted text\n\n```\ncode stays\n```\n\n---"
        out = translate_markdown(source, translator=_bracket)
        self.assertIn("> [quoted text]", out)
        self.assertIn("```\ncode stays\n```", out)
        self.assertIn("---", out)

    def test_fenced_code_block_with_blank_lines_is_untouched(self):
        source = (
            "```c\n"
            "#include <stdio.h>\n"
            "\n"
            "int main() {\n"
            "    return 0;\n"
            "}\n"
            "```"
        )
        out = translate_markdown(source, translator=_bracket)
        self.assertEqual(out, source)


class DeepSeekBackendTests(unittest.TestCase):
    def test_without_key_raises_clear_error(self):
        with mock.patch("pdfpages2md.translate._config", return_value=""):
            with self.assertRaises(TranslationUnavailableError) as ctx:
                _deepseek("hello", "en", "zh")
        self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))

    def test_config_reads_dotenv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("DEEPSEEK_API_KEY=sk-test\n# comment\n", encoding="utf-8")
            with mock.patch(
                "pdfpages2md.translate._dotenv_candidates",
                return_value=[env_file],
            ):
                self.assertEqual(_config("DEEPSEEK_API_KEY"), "sk-test")

    def test_env_var_overrides_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("DEEPSEEK_API_KEY=from-file\n", encoding="utf-8")
            with mock.patch(
                "pdfpages2md.translate._dotenv_candidates",
                return_value=[env_file],
            ):
                with mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "from-env"}):
                    self.assertEqual(_config("DEEPSEEK_API_KEY"), "from-env")


if __name__ == "__main__":
    unittest.main()
