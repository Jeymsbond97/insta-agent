"""Tasdiqlangan videoni Instagram'ga Reels yoki Story qilib joylaydi.

Agentdan alohida ishlaydi: faqat approved/ ichidagi papkani qabul qiladi.
Ishlatish:
  python -m publisher.instagram approved/<slug> --ai no            # faqat tekshiradi, tarmoqqa yozmaydi
  python -m publisher.instagram approved/<slug> --ai no --publish  # haqiqatan joylaydi
  python -m publisher.instagram approved/<slug> --ai no --publish --story
--ai yes|no majburiy: platformadagi AI belgisi har video uchun egasining qarori.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

VERSION = os.environ.get("META_GRAPH_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{VERSION}"
CAPTION_LIMIT = 2200
MAX_SECONDS = 90  # API chegarasi bo'yicha manbalar har xil, shuning uchun ehtiyotkor qiymat
POLL_SECONDS = 10
POLL_TRIES = 60  # 10 daqiqa


class PublishError(Exception):
    pass


def auth() -> tuple[str, dict]:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    ig_id = os.environ.get("IG_USER_ID", "").strip()
    if not token or not ig_id:
        sys.exit("Avval .env ga IG_USER_ID va IG_ACCESS_TOKEN ni yozing.")
    return ig_id, {"Authorization": f"Bearer {token}"}


def _call(method: str, url: str, headers: dict, **kw) -> dict:
    for attempt in range(3):
        try:
            r = requests.request(method, url, headers=headers, timeout=kw.pop("timeout", 60), **kw)
        except requests.RequestException as e:
            if attempt == 2:
                raise PublishError(f"Tarmoq xatosi: {type(e).__name__}") from None
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code >= 500 and attempt < 2:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise PublishError(f"HTTP {r.status_code}: {r.text[:500]}")
        return r.json()


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height,bit_rate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def problems(path: Path, caption: str) -> list[str]:
    info = probe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    found = []
    if video["codec_name"] != "h264":
        found.append(f"video kodek {video['codec_name']}, h264 kerak")
    if audio is None:
        found.append("ovoz yo'q")
    if float(info["format"]["duration"]) > MAX_SECONDS:
        found.append(f"{MAX_SECONDS} s dan uzun")
    if len(caption) > CAPTION_LIMIT:
        found.append(f"caption {len(caption)} belgi, chegara {CAPTION_LIMIT}")
    return found


def to_720p(path: Path) -> Path:
    """Instagram katta faylni rad etsa ishlatiladigan zaxira nusxa."""
    out = path.with_name(f"{path.stem}_720p.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vf", "scale=720:1280", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac",
                    "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(out)], check=True)
    return out


def upload(path: Path, params: dict, ig_id: str, headers: dict) -> str:
    created = _call("POST", f"{GRAPH}/{ig_id}/media", headers, params={"upload_type": "resumable", **params})
    container = created["id"]
    size = path.stat().st_size
    offset = 0
    for attempt in range(3):
        try:
            with path.open("rb") as f:
                f.seek(offset)
                r = requests.post(created["uri"], data=f, timeout=900, headers={
                    "Authorization": headers["Authorization"].replace("Bearer", "OAuth"),
                    "offset": str(offset), "file_size": str(size)})
            if r.ok:
                return container
            if r.status_code < 500:
                raise PublishError(f"Yuklash xatosi {r.status_code}: {r.text[:500]}")
        except requests.RequestException as e:
            print(f"Yuklash uzildi ({type(e).__name__})", file=sys.stderr)
        # Uzilgan joydan davom etamiz
        status = _call("GET", f"{GRAPH}/{container}", headers, params={"fields": "video_status"})
        offset = int((status.get("video_status") or {}).get("uploading_phase", {}).get("bytes_transferred", 0))
        time.sleep(5 * (attempt + 1))
    raise PublishError("Yuklash 3 urinishdan keyin ham tugamadi")


def wait_ready(container: str, headers: dict):
    for _ in range(POLL_TRIES):
        status = _call("GET", f"{GRAPH}/{container}", headers, params={"fields": "status,status_code"})
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram videoni qabul qilmadi: {status.get('status')}")
        time.sleep(POLL_SECONDS)
    raise PublishError("Instagram videoni 10 daqiqada qayta ishlab bo'lmadi")


def publish(path: Path, params: dict, ig_id: str, headers: dict) -> str:
    container = upload(path, params, ig_id, headers)
    wait_ready(container, headers)
    return _call("POST", f"{GRAPH}/{ig_id}/media_publish", headers, params={"creation_id": container})["id"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="approved/<slug>")
    ap.add_argument("--ai", choices=["yes", "no"], required=True, help="Platformadagi AI belgisi")
    ap.add_argument("--story", action="store_true")
    ap.add_argument("--publish", action="store_true", help="Bu bo'lmasa faqat tekshiradi")
    args = ap.parse_args()

    folder = args.folder.resolve()
    if (ROOT / "approved") not in folder.parents:
        sys.exit("Faqat approved/ ichidagi papka joylanadi.")
    video = folder / "final.mp4"
    if not video.exists():
        sys.exit(f"Topilmadi: {video}")
    kind = "story" if args.story else "reel"
    marker = folder / f"published_{kind}.json"
    if marker.exists():
        sys.exit(f"Bu {kind} allaqachon joylangan: {marker}")

    caption_file = folder / "caption.txt"
    caption = caption_file.read_text(encoding="utf-8").strip() if caption_file.exists() else ""
    found = problems(video, caption)
    if found:
        sys.exit("Tekshiruvdan o'tmadi: " + "; ".join(found))
    print(f"Fayl: {video} ({video.stat().st_size >> 20} MB), tur: {kind}, AI belgisi: {args.ai}")
    if not args.story:
        print(f"Caption boshi: {caption[:125]!r}")
    if not args.publish:
        print("Tekshiruv tugadi. Joylash uchun --publish qo'shing.")
        return

    ig_id, headers = auth()
    limit = _call("GET", f"{GRAPH}/{ig_id}/content_publishing_limit", headers)
    print("Kunlik limit holati:", limit.get("data"))
    if args.story:
        params = {"media_type": "STORIES"}
    else:
        params = {"media_type": "REELS", "caption": caption}
        if args.ai == "yes":
            params["is_ai_generated"] = "true"
    try:
        media_id = publish(video, params, ig_id, headers)
    except PublishError as e:
        print(f"Birinchi urinish o'tmadi: {e}\n720p nusxa bilan qayta urinilmoqda.", file=sys.stderr)
        try:
            media_id = publish(to_720p(video), params, ig_id, headers)
        except PublishError as e2:
            sys.exit(f"Joylanmadi: {e2}")
    marker.write_text(json.dumps({"media_id": media_id, "ts": time.time(), "ai_label": args.ai}), encoding="utf-8")
    print("Joylandi, media id:", media_id)


if __name__ == "__main__":
    main()
