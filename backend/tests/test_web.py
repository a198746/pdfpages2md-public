import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pdfpages2md.web import config_store
from pdfpages2md.web.handler import resolve_static
from pdfpages2md.web.multipart import as_bool, as_int, field, parse_multipart
from pdfpages2md.web.service import ConvertRequest


def _multipart_body(boundary: str) -> bytes:
    return (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="pages"\r\n\r\n'
        "1-10\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="sample.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
        "%PDF-1.4\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")


class MultipartTests(unittest.TestCase):
    def test_fields_and_files_are_separated(self):
        boundary = "test-boundary"
        fields, files = parse_multipart(
            f"multipart/form-data; boundary={boundary}",
            _multipart_body(boundary),
        )
        self.assertEqual(field(fields, "pages"), "1-10")
        self.assertEqual(files["file"], ("sample.pdf", b"%PDF-1.4"))

    def test_missing_field_returns_none(self):
        self.assertIsNone(field({}, "pages"))

    def test_boolean_spellings(self):
        for value in ("1", "true", "YES", " on "):
            self.assertTrue(as_bool(value))
        self.assertFalse(as_bool("0"))
        self.assertFalse(as_bool(None))
        self.assertTrue(as_bool(None, default=True))

    def test_integer_parsing_and_errors(self):
        self.assertEqual(as_int("12", 0), 12)
        self.assertEqual(as_int("", 50), 50)
        self.assertEqual(as_int(None, 50), 50)
        with self.assertRaises(ValueError):
            as_int("abc", 0)


class ConvertRequestTests(unittest.TestCase):
    def test_defaults_match_the_web_form(self):
        request = ConvertRequest.from_fields({})
        self.assertIsNone(request.pages)
        self.assertEqual(request.fmt, "markdown")
        self.assertEqual(request.marker, "comment")
        self.assertTrue(request.ocr)
        self.assertTrue(request.vision)
        self.assertFalse(request.translate)
        self.assertEqual(request.min_chars, 50)
        self.assertEqual(request.dpi, 200)

    def test_fields_are_parsed(self):
        request = ConvertRequest.from_fields(
            {
                "pages": ["3,5"],
                "format": ["text"],
                "marker": ["none"],
                "ocr": ["false"],
                "ocr_lang": ["chi_sim"],
                "min_chars": ["10"],
                "dpi": ["300"],
                "translate": ["on"],
                "translate_engine": ["auto"],
                "vision": ["off"],
            },
            translate_api_key="key",
        )
        self.assertEqual(request.pages, "3,5")
        self.assertEqual(request.fmt, "text")
        self.assertEqual(request.marker, "none")
        self.assertFalse(request.ocr)
        self.assertEqual(request.ocr_lang, "chi_sim")
        self.assertEqual(request.min_chars, 10)
        self.assertEqual(request.dpi, 300)
        self.assertTrue(request.translate)
        self.assertIsNone(request.translate_engine)
        self.assertFalse(request.vision)
        self.assertEqual(request.translate_api_key, "key")


class ConfigStoreTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            with mock.patch.object(config_store, "CONFIG_FILE", config_path):
                self.assertEqual(config_store.load(), {})
                config_store.save(
                    {"deepseek_api_key": " sk-1 ", "unknown": "ignored"}
                )
                self.assertEqual(
                    config_store.load(), {"deepseek_api_key": "sk-1"}
                )
                config_store.save({"deepseek_api_key": ""})
                self.assertEqual(config_store.load(), {})

    def test_effective_key_prefers_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            with mock.patch.object(config_store, "CONFIG_FILE", config_path):
                config_store.save({"deepseek_api_key": "from-file"})
                with mock.patch.dict(
                    os.environ, {"PDF_REFACTOR_TEST_KEY": "from-env"}
                ):
                    self.assertEqual(
                        config_store.effective_api_key(
                            "PDF_REFACTOR_TEST_KEY", "deepseek_api_key"
                        ),
                        "from-env",
                    )
                self.assertEqual(
                    config_store.effective_api_key(
                        "PDF_REFACTOR_TEST_ABSENT", "deepseek_api_key"
                    ),
                    "from-file",
                )


class StaticResolutionTests(unittest.TestCase):
    def test_frontend_assets_resolve(self):
        self.assertIsNotNone(resolve_static("/"))
        self.assertIsNotNone(resolve_static("/index.html"))
        self.assertIsNotNone(resolve_static("/app.js"))
        self.assertIsNotNone(resolve_static("/js/tooltip.js"))

    def test_non_frontend_paths_are_rejected(self):
        self.assertIsNone(resolve_static("/README.md"))
        self.assertIsNone(resolve_static("/../README.md"))
        self.assertIsNone(resolve_static("/..%2FREADME.md"))
        self.assertIsNone(resolve_static("/js/"))


if __name__ == "__main__":
    unittest.main()
