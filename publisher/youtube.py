"""Upload an approved video to YouTube (a short vertical video becomes a Short).

Runs separately from the agent: accepts only a folder inside approved/.
Usage:
  python -m publisher.youtube --login                               # once: authorize in the browser
  python -m publisher.youtube approved/<slug> --ai no               # check only
  python -m publisher.youtube approved/<slug> --ai no --publish     # really uploads
Until the audit passes, YouTube forces API uploads to private anyway, so private is the default.
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

# force-ssl is needed for comments (stage 8); requested now to avoid asking for consent again
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
        sys.exit(f"Not found: {CLIENT_FILE}")
    creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES).run_local_server(port=0)
    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return creds


def credentials() -> Credentials:
    if not TOKEN_FILE.exists():
        sys.exit("First run once: python -m publisher.youtube --login")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError:
            sys.exit("Authorization expired. Run again: python -m publisher.youtube --login")
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
        found.append("no title")
    if len(title) > TITLE_LIMIT:
        found.append(f"title is {len(title)} characters, limit {TITLE_LIMIT}")
    if len(description) > DESCRIPTION_LIMIT:
        found.append(f"description is {len(description)} characters, limit {DESCRIPTION_LIMIT}")
    # YouTube does not accept the < and > characters
    if any(c in title + description for c in "<>"):
        found.append("title or description contains < or >")
    if stream["height"] <= stream["width"]:
        found.append("video is not vertical, it will not be a Short")
    if float(info["format"]["duration"]) > SHORTS_SECONDS:
        found.append(f"longer than {SHORTS_SECONDS} s, it will not be a Short")
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
                sys.exit(f"Upload failed: HTTP {e.resp.status}: {e.reason}")
            attempt += 1
            time.sleep(2 ** attempt + random.random())
        except OSError as e:
            if attempt >= 5:
                sys.exit(f"Upload failed: {type(e).__name__}")
            attempt += 1
            time.sleep(2 ** attempt + random.random())
    return response["id"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, nargs="?", help="approved/<slug>")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--ai", choices=["yes", "no"], help="Platform AI label")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    ap.add_argument("--publish", action="store_true", help="Without this flag, only check")
    args = ap.parse_args()

    if args.login:
        login()
        print("Authorization saved.")
        return
    if not args.folder or not args.ai:
        ap.error("approved/<slug> and --ai yes|no are required")
    folder = args.folder.resolve()
    if (ROOT / "approved") not in folder.parents:
        sys.exit("Only a folder inside approved/ can be published.")
    video = folder / "final.mp4"
    if not video.exists():
        sys.exit(f"Not found: {video}")
    marker = folder / "published_youtube.json"
    if marker.exists():
        sys.exit(f"Already uploaded: {marker}")

    title, description = metadata(folder)
    found = problems(video, title, description)
    if found:
        sys.exit("Check failed: " + "; ".join(found))
    print(f"File: {video} ({video.stat().st_size >> 20} MB), AI label: {args.ai}, privacy: {args.privacy}")
    print(f"Title: {title}")
    if not args.publish:
        print("Check finished. Add --publish to upload.")
        return
    video_id = upload(video, title, description, args.ai == "yes", args.privacy)
    marker.write_text(json.dumps({"video_id": video_id, "ts": time.time(), "ai_label": args.ai}), encoding="utf-8")
    print(f"Uploaded: https://youtube.com/shorts/{video_id}")


if __name__ == "__main__":
    main()
