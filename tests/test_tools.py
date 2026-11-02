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


if __name__ == "__main__":
    unittest.main()
