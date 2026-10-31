"""ElevenLabs orqali matndan ovoz va so'z vaqtlarini oladi.

Ishlatish:  python tools/tts.py script.txt --out output/<papka>/voice
Natija:     voice.mp3 va voice.words.json ([{"w": so'z, "s": boshlanish, "e": tugash}, ...])
Oylik belgi limiti config/limits.yaml da. Kalit ekranga chiqarilmaydi.
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
    """Harfma-harf vaqtlarni so'zlarga yig'adi."""
    words, cur, start, end, in_tag = [], "", 0.0, 0.0, False
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        # [curious] kabi ohang teglari aytilmaydi, subtitrga ham kirmaydi
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


def synthesize(text: str, model: str, stability: float | None = None) -> dict:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not key or not voice:
        sys.exit("Avval .env ga ELEVENLABS_API_KEY va ELEVENLABS_VOICE_ID ni yozing.")
    limit = monthly_limit()
    if used_this_month() + len(text) > limit:
        sys.exit(f"Oylik limit: {used_this_month()} + {len(text)} > {limit} belgi. config/limits.yaml ga qarang.")
    body = {"text": text, "model_id": model}
    if stability is not None:
        body["voice_settings"] = {"stability": stability}
    for attempt in range(3):
        try:
            r = requests.post(f"{API}/{voice}/with-timestamps", params={"output_format": "mp3_44100_128"},
                              headers={"xi-api-key": key}, json=body, timeout=180)
            if r.status_code < 500:
                break
        except requests.RequestException as e:
            print(f"Qayta urinilmoqda ({type(e).__name__})", file=sys.stderr)
        if attempt == 2:
            sys.exit("ElevenLabs javob bermadi.")
        time.sleep(3 * (attempt + 1))
    if not r.ok:
        sys.exit(f"ElevenLabs xatosi {r.status_code}: {r.text[:300]}")
    add_usage(len(text))
    return r.json()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", type=Path, help="Matn fayli")
    ap.add_argument("--out", type=Path, required=True, help="Kengaytmasiz nom, masalan output/x/voice")
    ap.add_argument("--model", default="eleven_v4")
    ap.add_argument("--stability", type=float, help="Pastroq qiymat ohangni jonliroq qiladi")
    args = ap.parse_args()

    text = args.script.read_text(encoding="utf-8").strip()
    data = synthesize(text, args.model, args.stability)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".mp3").write_bytes(base64.b64decode(data["audio_base64"]))
    words = words_from_alignment(data.get("normalized_alignment") or data["alignment"])
    args.out.with_suffix(".words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.out.with_suffix('.mp3')}: {len(text)} belgi, {len(words)} so'z, {words[-1]['e']:.1f} s")
    print(f"Bu oy ishlatilgan: {used_this_month()} / {monthly_limit()} belgi")


if __name__ == "__main__":
    main()
