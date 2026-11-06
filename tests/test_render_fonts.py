import os
import unittest

import media


class HindiFontTests(unittest.TestCase):
    def test_hindi_font_exists_and_contains_devanagari_glyphs(self):
        path = media._font_path()
        self.assertTrue(os.path.exists(path))
        f = media.font(64)
        # A blank mask indicates missing glyphs; DejaVu previously produced tofu.
        self.assertIsNotNone(f.getmask("हिंदी तकनीक").getbbox())
        self.assertNotEqual(f.getmask("हिंदी").getbbox(), f.getmask("□□□□").getbbox())

    def test_ass_styles_use_hindi_font_family(self):
        self.assertEqual(media.FONT_NAME, "Noto Sans Devanagari")


if __name__ == "__main__":
    unittest.main()
