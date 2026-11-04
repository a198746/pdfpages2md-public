import unittest

from pdfpages2md.ranges import parse_pages


class ParsePagesTests(unittest.TestCase):
    def test_single_and_range(self):
        self.assertEqual(parse_pages("1-10,50,88-95"), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 50, 88, 89, 90, 91, 92, 93, 94, 95])

    def test_deduplicates_and_sorts(self):
        self.assertEqual(parse_pages("3,1,2,1-2"), [1, 2, 3])

    def test_open_ended_range(self):
        self.assertEqual(parse_pages("98-", page_count=100), [98, 99, 100])

    def test_from_start(self):
        self.assertEqual(parse_pages("-3", page_count=100), [1, 2, 3])

    def test_all_keyword(self):
        self.assertEqual(parse_pages("all", page_count=4), [1, 2, 3, 4])

    def test_invalid_token(self):
        with self.assertRaises(ValueError):
            parse_pages("1,,x")

    def test_reversed_range(self):
        with self.assertRaises(ValueError):
            parse_pages("10-5")


if __name__ == "__main__":
    unittest.main()
