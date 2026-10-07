import unittest
from datetime import date

import arabic_reshaper
from bidi.algorithm import get_display

from pdf_formatting import format_pdf_date


class PdfDateFormattingTests(unittest.TestCase):
    def test_date_keeps_slashes_and_order_in_arabic_pdf_text(self):
        formatted_date = format_pdf_date(date(2026, 10, 7))
        displayed_text = get_display(
            arabic_reshaper.reshape(f"تاريخ الكشف: {formatted_date}")
        )

        self.assertIn("2026/10/07", formatted_date)
        self.assertIn("2026/10/07", displayed_text)


if __name__ == "__main__":
    unittest.main()
