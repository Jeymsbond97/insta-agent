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

    def test_brightness_order_is_kept(self):
        values = [float(self.convert(v)[0]) for v in np.linspace(0, 1, 21)]
        self.assertEqual(values, sorted(values))

    def test_grey_stays_neutral(self):
        r, g, b = self.convert(0.5)
        self.assertAlmostEqual(float(r), float(g), places=3)
        self.assertAlmostEqual(float(g), float(b), places=3)


class TtsTest(unittest.TestCase):
    def alignment(self, text):
        n = len(text)
        return {"characters": list(text), "character_start_times_seconds": [i * 0.1 for i in range(n)],
                "character_end_times_seconds": [i * 0.1 + 0.1 for i in range(n)]}

    def sent_body(self, **kw):
        reply = mock.Mock(status_code=200, ok=True)
        reply.json.return_value = {}
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}), \
                mock.patch.object(tts, "used_this_month", return_value=0), mock.patch.object(tts, "add_usage"), \
                mock.patch.object(tts.requests, "post", return_value=reply) as post:
            tts.synthesize("salom", "eleven_v4", **kw)
        return post.call_args.kwargs["json"]

    def test_characters_group_into_words(self):
        words = tts.words_from_alignment(self.alignment("salom dunyo"))
        self.assertEqual([w["w"] for w in words], ["salom", "dunyo"])
        self.assertAlmostEqual(words[1]["s"], 0.6)

    def test_tone_tags_are_not_words(self):
        words = tts.words_from_alignment(self.alignment("[curious] salom"))
        self.assertEqual([w["w"] for w in words], ["salom"])


if __name__ == "__main__":
    unittest.main()
