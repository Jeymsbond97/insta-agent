"""Speed a voice track up or down to a target length and rescale its word timings to match.

Usage: python tools/voicefit.py voice.mp3 voice.words.json --seconds 52 --out voice_fit
Writes voice_fit.mp3 and voice_fit.words.json. Speeds above MAX_SPEED sound rushed and are refused.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

MAX_SPEED = 1.35
MIN_SPEED = 0.8


def speed_for(current: float, target: float) -> float:
    s = current / target
    if not MIN_SPEED <= s <= MAX_SPEED:
        raise ValueError(f"speed {s:.2f} is outside {MIN_SPEED}-{MAX_SPEED}; shorten or lengthen the text instead")
    return s


def scale_words(words: list[dict], speed: float) -> list[dict]:
    return [dict(w, s=round(w["s"] / speed, 3), e=round(w["e"] / speed, 3)) for w in words]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("voice", type=Path)
    ap.add_argument("words", type=Path)
    ap.add_argument("--seconds", type=float, required=True)
    ap.add_argument("--out", type=Path, required=True, help="Name without extension")
    args = ap.parse_args()
    words = json.loads(args.words.read_text(encoding="utf-8"))
    try:
        s = speed_for(words[-1]["e"], args.seconds)
    except ValueError as e:
        sys.exit(str(e))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(args.voice), "-af", f"atempo={s:.4f}",
                    str(args.out.with_suffix(".mp3"))], check=True)
    args.out.with_suffix(".words.json").write_text(json.dumps(scale_words(words, s), ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print(f"speed {s:.3f}, {words[-1]['e'] / s:.1f} s")


if __name__ == "__main__":
    main()
