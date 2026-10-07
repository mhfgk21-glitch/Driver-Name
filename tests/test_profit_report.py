import re
import unittest
from datetime import date

import pandas as pd

from profit_report import profit_report_pdf_bytes


class ProfitReportTests(unittest.TestCase):
    def test_report_is_a4_portrait_pdf(self):
        summary = pd.DataFrame([
            {
                "المندوب": "علي",
                "القسم": "مركز",
                "عدد الطلبات": 10,
                "التسعيرة": 2000,
                "المبلغ": 20000,
            },
        ])

        pdf = profit_report_pdf_bytes(
            summary, 100000, 5000, 2000, date(2026, 10, 7), "شركة تجريبية"
        )

        self.assertTrue(pdf.startswith(b"%PDF-"))
        media_box = re.search(rb"/MediaBox\s*\[([^]]+)\]", pdf)
        self.assertIsNotNone(media_box)
        coordinates = [float(value) for value in media_box.group(1).split()]
        width = coordinates[2] - coordinates[0]
        height = coordinates[3] - coordinates[1]
        self.assertAlmostEqual(width, 595.2756, places=2)
        self.assertAlmostEqual(height, 841.8898, places=2)

    def test_driver_details_continue_across_a4_pages(self):
        rows = [
            {
                "المندوب": f"مندوب {index}",
                "القسم": "مركز" if index % 2 else "قضاء",
                "عدد الطلبات": index + 1,
                "التسعيرة": 2000 if index % 2 else 3000,
                "المبلغ": (index + 1) * (2000 if index % 2 else 3000),
            }
            for index in range(80)
        ]
        summary = pd.DataFrame(rows)

        pdf = profit_report_pdf_bytes(
            summary, 10_000_000, 500_000, 100_000, date(2026, 10, 7)
        )

        page_count = len(re.findall(rb"/Type\s*/Page\b", pdf))
        self.assertGreater(page_count, 1)


if __name__ == "__main__":
    unittest.main()
