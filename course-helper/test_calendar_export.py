import unittest
from datetime import date
from io import BytesIO

from PIL import Image

from calendar_export import (
    default_course_color,
    default_week_one_monday,
    dates_for_week,
    event_color,
    render_calendar_png,
    valid_calendar_color,
)


class CalendarExportTests(unittest.TestCase):
    def test_default_week_one_date_and_week_dates(self):
        first_monday = default_week_one_monday("1151")
        self.assertEqual(first_monday, date(2026, 9, 7))
        self.assertEqual(
            dates_for_week(first_monday, 2),
            [
                date(2026, 9, 14),
                date(2026, 9, 15),
                date(2026, 9, 16),
                date(2026, 9, 17),
                date(2026, 9, 18),
                date(2026, 9, 19),
                date(2026, 9, 20),
            ],
        )

    def test_rejects_non_monday_week_anchor(self):
        with self.assertRaises(ValueError):
            dates_for_week(date(2026, 9, 8), 1)

    def test_calendar_image_contains_valid_png(self):
        week_dates = dates_for_week(date(2026, 9, 7), 1)
        image_bytes = render_calendar_png(
            [
                {
                    "day": "一",
                    "start": "09:00",
                    "end": "10:50",
                    "title": "課程測試",
                    "offering_id": "CS1001-A",
                    "color": "#DCEBFA",
                }
            ],
            "1151",
            1,
            week_dates,
        )
        self.assertTrue(image_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(image_bytes)) as image:
            self.assertGreater(image.width, image.height)

    def test_color_is_valid_or_uses_stable_course_default(self):
        self.assertTrue(valid_calendar_color("#A1b2C3"))
        self.assertFalse(valid_calendar_color("red"))
        self.assertEqual(
            event_color({"offering_id": "CS1001-A"}),
            default_course_color("CS1001-A"),
        )


if __name__ == "__main__":
    unittest.main()
