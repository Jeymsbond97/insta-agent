"""Get speech audio and word timings for a text from ElevenLabs.

Usage:   python tools/tts.py script.txt --out output/<folder>/voice
Output:  voice.mp3 and voice.words.json ([{"w": word, "s": start, "e": end}, ...])
The monthly character limit is in config/limits.yaml. The key is never printed.
"""
import argparse
import base64
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

USAGE = ROOT / "state" / "elevenlabs_usage.json"
API = "https://api.elevenlabs.io/v1/text-to-speech"


def monthly_limit() -> int:
    limits = yaml.safe_load((ROOT / "config" / "limits.yaml").read_text(encoding="utf-8"))
    return limits["elevenlabs"]["characters_per_month"]


def used_this_month() -> int:
    if not USAGE.exists():
        return 0
    return json.loads(USAGE.read_text(encoding="utf-8")).get(date.today().strftime("%Y-%m"), 0)


def add_usage(chars: int):
    data = json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}
    month = date.today().strftime("%Y-%m")
    data[month] = data.get(month, 0) + chars
    USAGE.parent.mkdir(exist_ok=True)
    USAGE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def words_from_alignment(al: dict) -> list[dict]:
    """Group per-character timings into words."""
    words, cur, start, end, in_tag = [], "", 0.0, 0.0, False
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        # Tone tags such as [curious] are not spoken and stay out of the subtitles
        if ch == "[":
            in_tag = True
        if in_tag:
            in_tag = ch != "]"
            continue
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": start, "e": end})
            cur = ""
            continue
        if not cur:
            start = s
        cur += ch
        end = e
    if cur:
        words.append({"w": cur, "s": start, "e": end})
    return words


def synthesize(text: str, model: str, stability: float | None = None, speed: float | None = None) -> dict:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not key or not voice:
        sys.exit("Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env first.")
    limit = monthly_limit()
    if used_this_month() + len(text) > limit:
        sys.exit(f"Monthly limit: {used_this_month()} + {len(text)} > {limit} characters. See config/limits.yaml.")
    body = {"text": text, "model_id": model}
    settings = {}
    if stability is not None:
        settings["stability"] = stability
    if speed is not None:
        settings["speed"] = speed
    if settings:
        body["voice_settings"] = settings
    for attempt in range(3):
        try:
            r = requests.post(f"{API}/{voice}/with-timestamps", params={"output_format": "mp3_44100_128"},
                              headers={"xi-api-key": key}, json=body, timeout=180)
            if r.status_code < 500:
                break
        except requests.RequestException as e:
            print(f"Retrying ({type(e).__name__})", file=sys.stderr)
        if attempt == 2:
            sys.exit("ElevenLabs did not respond.")
        time.sleep(3 * (attempt + 1))
    if not r.ok:
        sys.exit(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    add_usage(len(text))
    return r.json()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", type=Path, help="Text file")
    ap.add_argument("--out", type=Path, required=True, help="Name without extension, e.g. output/x/voice")
    ap.add_argument("--model", default="eleven_v4")
    ap.add_argument("--stability", type=float, help="A lower value makes the tone livelier")
    ap.add_argument("--speed", type=float, help="0.7 to 1.2; above 1 speaks faster")
    args = ap.parse_args()

    text = args.script.read_text(encoding="utf-8").strip()
    data = synthesize(text, args.model, args.stability, args.speed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".mp3").write_bytes(base64.b64decode(data["audio_base64"]))
    words = words_from_alignment(data.get("normalized_alignment") or data["alignment"])
    args.out.with_suffix(".words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.out.with_suffix('.mp3')}: {len(text)} characters, {len(words)} words, {words[-1]['e']:.1f} s")
    print(f"Used this month: {used_this_month()} / {monthly_limit()} characters")


if __name__ == "__main__":
    main()
