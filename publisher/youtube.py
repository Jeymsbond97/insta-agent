"""Tasdiqlangan videoni YouTube'ga yuklaydi (vertikal va qisqa video Shorts bo'ladi).

Agentdan alohida ishlaydi: faqat approved/ ichidagi papkani qabul qiladi.
Ishlatish:
  python -m publisher.youtube --login                               # bir marta: brauzerda ruxsat
  python -m publisher.youtube approved/<slug> --ai no               # faqat tekshiradi
  python -m publisher.youtube approved/<slug> --ai no --publish     # haqiqatan yuklaydi
Audit o'tguncha YouTube API yuklagan videoni baribir private qiladi, shuning uchun standart holat private.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# force-ssl izohlar uchun kerak (8-bosqich), qayta ruxsat so'ramaslik uchun hozirdan olinadi
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
CLIENT_FILE = ROOT / os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "secrets/client_secret.json")
TOKEN_FILE = ROOT / "secrets" / "token_youtube.json"
CATEGORY_SCIENCE_TECH = "28"
TITLE_LIMIT = 100
DESCRIPTION_LIMIT = 5000
SHORTS_SECONDS = 180
RETRY_STATUS = {500, 502, 503, 504}


def login() -> Credentials:
    if not CLIENT_FILE.exists():
        sys.exit(f"Topilmadi: {CLIENT_FILE}")
    creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES).run_local_server(port=0)
    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return creds


def credentials() -> Credentials:
    if not TOKEN_FILE.exists():
        sys.exit("Avval bir marta: python -m publisher.youtube --login")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError:
            sys.exit("Ruxsat muddati tugagan. Qayta: python -m publisher.youtube --login")
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def metadata(folder: Path) -> tuple[str, str]:
    caption_file = folder / "caption.txt"
    caption = caption_file.read_text(encoding="utf-8").strip() if caption_file.exists() else ""
    title_file = folder / "title.txt"
    title = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else caption.split("\n", 1)[0].strip()
    return title, caption


def problems(video: Path, title: str, description: str) -> list[str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    stream = info["streams"][0]
    found = []
    if not title:
        found.append("sarlavha yo'q")
    if len(title) > TITLE_LIMIT:
        found.append(f"sarlavha {len(title)} belgi, chegara {TITLE_LIMIT}")
    if len(description) > DESCRIPTION_LIMIT:
        found.append(f"tavsif {len(description)} belgi, chegara {DESCRIPTION_LIMIT}")
    # YouTube < va > belgilarini qabul qilmaydi
    if any(c in title + description for c in "<>"):
        found.append("sarlavha yoki tavsifda < yoki > bor")
    if stream["height"] <= stream["width"]:
        found.append("video vertikal emas, Shorts bo'lmaydi")
    if float(info["format"]["duration"]) > SHORTS_SECONDS:
        found.append(f"{SHORTS_SECONDS} s dan uzun, Shorts bo'lmaydi")
    return found


def upload(video: Path, title: str, description: str, ai: bool, privacy: str) -> str:
    youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    request = youtube.videos().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": description, "categoryId": CATEGORY_SCIENCE_TECH,
                    "defaultLanguage": "uz", "defaultAudioLanguage": "uz"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": ai},
    }, media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True))
    response, attempt = None, 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as e:
            if e.resp.status not in RETRY_STATUS or attempt >= 5:
                sys.exit(f"Yuklanmadi: HTTP {e.resp.status}: {e.reason}")
            attempt += 1
            time.sleep(2 ** attempt + random.random())
        except OSError as e:
            if attempt >= 5:
                sys.exit(f"Yuklanmadi: {type(e).__name__}")
            attempt += 1
            time.sleep(2 ** attempt + random.random())
    return response["id"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, nargs="?", help="approved/<slug>")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--ai", choices=["yes", "no"], help="Platformadagi AI belgisi")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    ap.add_argument("--publish", action="store_true", help="Bu bo'lmasa faqat tekshiradi")
    args = ap.parse_args()

    if args.login:
        login()
        print("Ruxsat saqlandi.")
        return
    if not args.folder or not args.ai:
        ap.error("approved/<slug> va --ai yes|no kerak")
    folder = args.folder.resolve()
    if (ROOT / "approved") not in folder.parents:
        sys.exit("Faqat approved/ ichidagi papka joylanadi.")
    video = folder / "final.mp4"
    if not video.exists():
        sys.exit(f"Topilmadi: {video}")
    marker = folder / "published_youtube.json"
    if marker.exists():
        sys.exit(f"Allaqachon yuklangan: {marker}")

    title, description = metadata(folder)
    found = problems(video, title, description)
    if found:
        sys.exit("Tekshiruvdan o'tmadi: " + "; ".join(found))
    print(f"Fayl: {video} ({video.stat().st_size >> 20} MB), AI belgisi: {args.ai}, holat: {args.privacy}")
    print(f"Sarlavha: {title}")
    if not args.publish:
        print("Tekshiruv tugadi. Yuklash uchun --publish qo'shing.")
        return
    video_id = upload(video, title, description, args.ai == "yes", args.privacy)
    marker.write_text(json.dumps({"video_id": video_id, "ts": time.time(), "ai_label": args.ai}), encoding="utf-8")
    print(f"Yuklandi: https://youtube.com/shorts/{video_id}")


if __name__ == "__main__":
    main()
