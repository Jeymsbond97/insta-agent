"""Sound effects from a text description with ElevenLabs.

Usage: python tools/sfx.py "laptop keyboard typing, close mic" --seconds 5 --out path.mp3
"""
import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
URL = "https://api.elevenlabs.io/v1/sound-generation"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text")
    ap.add_argument("--seconds", type=float, help="0.5 to 30; chosen by the model when left out")
    ap.add_argument("--influence", type=float, default=0.5, help="0 to 1; higher follows the text more closely")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY in .env first.")
    body = {"text": args.text, "prompt_influence": args.influence}
    if args.seconds:
        body["duration_seconds"] = args.seconds
    r = requests.post(URL, headers={"xi-api-key": key}, json=body, timeout=180)
    if not r.ok:
        sys.exit(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(r.content)
    print("ok", args.out)


if __name__ == "__main__":
    main()
