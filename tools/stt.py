"""Speech to text with ElevenLabs Scribe: words with timings and sound events (music, laughter, keyboard).

Usage: python tools/stt.py audio_or_video [more files] --out-dir DIR [--language uzb]
Writes DIR/<name>.json. Files already transcribed are skipped.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
URL = "https://api.elevenlabs.io/v1/speech-to-text"


def transcribe(path: Path, language: str | None) -> dict:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY in .env first.")
    data = {"model_id": "scribe_v2", "tag_audio_events": "true", "timestamps_granularity": "word"}
    if language:
        data["language_code"] = language
    for attempt in range(3):
        try:
            with path.open("rb") as f:
                r = requests.post(URL, headers={"xi-api-key": key}, data=data, files={"file": f}, timeout=300)
            if r.status_code < 500:
                break
        except requests.RequestException as e:
            print(f"Retrying ({type(e).__name__})", file=sys.stderr)
        if attempt == 2:
            sys.exit("ElevenLabs did not respond.")
        time.sleep(3 * (attempt + 1))
    if not r.ok:
        sys.exit(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    return r.json()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--language", help="ISO code such as uzb or eng; detected when left out")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for f in args.files:
        dest = args.out_dir / (f.stem + ".json")
        if dest.exists():
            continue
        res = transcribe(f, args.language)
        dest.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print("ok", f.name, res.get("language_code"), len(res.get("text", "").split()), "words", flush=True)


if __name__ == "__main__":
    main()
