import unittest

from openpyxl import Workbook

from scripts.convert_dexa_xlsx import _find_height_inches


class FindHeightInchesTest(unittest.TestCase):
    def test_finds_height_below_label_when_rows_shift(self):
        sheet = Workbook().active
        sheet["D9"] = "Height"
        sheet["D10"] = 72

        self.assertEqual(_find_height_inches(sheet), 72.0)

    def test_rejects_height_label_without_numeric_value(self):
        sheet = Workbook().active
        sheet["B12"] = "Height"

        with self.assertRaises(ValueError):
            _find_height_inches(sheet)


if __name__ == "__main__":
    unittest.main()
