import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import hlg2sdr  # noqa: E402
import sfx  # noqa: E402
import stt  # noqa: E402
import textcheck  # noqa: E402
import tts  # noqa: E402


class TextcheckTest(unittest.TestCase):
    def errors(self, text):
        return textcheck.check(text)[0]

    def test_plain_apostrophe_after_o_is_an_error(self):
        self.assertTrue(any("U+02BB" in e for e in self.errors("o'zbek")))

    def test_glottal_mark_after_g_is_an_error(self):
        self.assertTrue(any("U+02BB" in e for e in self.errors("tog\u02bc")))

    def test_apostrophe_inside_a_word_wants_the_glottal_mark(self):
        self.assertTrue(any("U+02BC" in e for e in self.errors("ma'no")))

    def test_correct_text_has_no_errors(self):
        self.assertEqual(self.errors("Kitob \u2014 bilim. Ma\u02bcno o\u02bbzbekcha."), [])

    def test_double_space_is_an_error(self):
        self.assertTrue(any("double space" in e for e in self.errors("katta  uy")))

    def test_dash_is_only_a_note(self):
        errors, notes = textcheck.check("bir \u2014 ikki")
        self.assertEqual(errors, [])
        self.assertTrue(any("dash" in n for n in notes))

    def test_too_long_is_an_error(self):
        self.assertTrue(any("too long" in e for e in self.errors("soz " * 200)))


class Hlg2SdrTest(unittest.TestCase):
    def convert(self, value):
        return hlg2sdr.hlg_to_sdr(np.full((1, 1, 3), value, np.float32))[0, 0]

    def test_black_stays_black(self):
        self.assertTrue(np.allclose(self.convert(0.0), 0.0, atol=1e-3))

    def test_peak_stays_in_range(self):
        out = self.convert(1.0)
        self.assertTrue(((out >= 0) & (out <= 1)).all())


if __name__ == "__main__":
    unittest.main()
