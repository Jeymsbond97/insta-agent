"""Instagram tokenini tekshiradi: qaysi serverda ishlaydi, qaysi akkaunt, qachongacha.

Ishlatish:  python tools/ig_check.py
Token ekranga chiqarilmaydi.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

VERSION = os.environ.get("META_GRAPH_VERSION", "v23.0")
token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
ig_id = os.environ.get("IG_USER_ID", "").strip()
app_id = os.environ.get("META_APP_ID", "").strip()
app_secret = os.environ.get("META_APP_SECRET", "").strip()

if not token or not ig_id:
    sys.exit("Avval .env ga IG_USER_ID va IG_ACCESS_TOKEN ni yozing.")


def try_host(host: str) -> dict | None:
    r = requests.get(f"https://{host}/{VERSION}/{ig_id}",
                     params={"fields": "username,followers_count,media_count", "access_token": token},
                     timeout=30)
    data = r.json()
    if "error" in data:
        print(f"  {host}: ishlamadi ({data['error'].get('message')})")
        return None
    print(f"  {host}: ISHLAYDI → @{data.get('username')}, "
          f"{data.get('followers_count', '?')} obunachi, {data.get('media_count', '?')} post")
    return data


print("1) Akkaunt:")
ok = [h for h in ("graph.facebook.com", "graph.instagram.com") if try_host(h)]

print("2) Token muddati:")
if app_id and app_secret:
    r = requests.get(f"https://graph.facebook.com/{VERSION}/debug_token",
                     params={"input_token": token, "access_token": f"{app_id}|{app_secret}"}, timeout=30)
    d = r.json().get("data", {})
    if d:
        exp = d.get("expires_at", 0)
        when = "hech qachon" if not exp else datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%d")
        print(f"  turi: {d.get('type')}, amal qiladi: {d.get('is_valid')}, tugaydi: {when}")
        print(f"  ruxsatlar: {', '.join(sorted(d.get('scopes', [])))}")
    else:
        print(f"  aniqlab bo'lmadi: {r.json().get('error', {}).get('message')}")
else:
    print("  META_APP_ID / META_APP_SECRET yo'q, o'tkazib yuborildi.")

print("\nNatija:", "OK, " + ", ".join(ok) if ok else "token hech qaysi serverda ishlamadi")
