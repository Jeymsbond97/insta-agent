import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import captions  # noqa: E402
import medialog  # noqa: E402
import voicefit  # noqa: E402

WORDS = [{"w": "Bir", "s": 0.0, "e": 0.4}, {"w": "ikki", "s": 0.5, "e": 0.9}, {"w": "uch", "s": 1.0, "e": 1.4}]


class MediaTest(unittest.TestCase):

    def test_logged_file_is_used(self):
        ledger = {"_note": "x", "video one": ["clips/a.mp4", "clips/b.jpg (note)"]}
        self.assertEqual(medialog.check(["clips/a.mp4", "clips/c.mp4", "clips/b.jpg"], ledger),
                         {"clips/a.mp4": "video one", "clips/b.jpg": "video one"})

    def test_add_records_files_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.json"
            medialog.add("v2", ["x.mp4", "x.mp4", "y.mp4"], path)
            self.assertEqual(json.loads(path.read_text())["v2"], ["x.mp4", "y.mp4"])

    def test_captions_only_during_speech(self):
        blank = Image.new("RGB", (captions.W, captions.H))
        idle = captions.draw(blank.copy(), 5.0, WORDS, [[0, 1], [2]], {}, end_time=2.0)
        live = captions.draw(blank.copy(), 0.3, WORDS, [[0, 1], [2]], {1: captions.TEAL}, end_time=2.0)
        self.assertEqual(idle.getbbox(), None)
        self.assertIsNotNone(live.getbbox())

    def test_long_phrase_stays_inside(self):
        long = [{"w": "juda-uzun-soz" * 3, "s": 0.0, "e": 1.0}, {"w": "yana" * 6, "s": 0.0, "e": 1.0}]
        img = captions.draw(Image.new("RGB", (captions.W, captions.H)), 0.5, long, [[0, 1]], {0: captions.ORANGE})
        box = img.getbbox()
        self.assertGreaterEqual(box[0], 0)
        self.assertLessEqual(box[2], captions.W)

    def test_word_times_scale(self):
        out = voicefit.scale_words(WORDS, 1.25)
        self.assertAlmostEqual(out[-1]["e"], 1.12)
        self.assertEqual([w["w"] for w in out], ["Bir", "ikki", "uch"])


if __name__ == "__main__":
    unittest.main()
