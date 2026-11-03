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


if __name__ == "__main__":
    unittest.main()
