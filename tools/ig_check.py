"""Check the Instagram token: which host it works on, which account, and until when.

Usage:  python tools/ig_check.py
The token is never printed.
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
    sys.exit("Set IG_USER_ID and IG_ACCESS_TOKEN in .env first.")


def try_host(host: str) -> dict | None:
    r = requests.get(f"https://{host}/{VERSION}/{ig_id}",
                     params={"fields": "username,followers_count,media_count", "access_token": token},
                     timeout=30)
    data = r.json()
    if "error" in data:
        print(f"  {host}: failed ({data['error'].get('message')})")
        return None
    print(f"  {host}: WORKS → @{data.get('username')}, "
          f"{data.get('followers_count', '?')} followers, {data.get('media_count', '?')} posts")
    return data


print("1) Account:")
ok = [h for h in ("graph.facebook.com", "graph.instagram.com") if try_host(h)]

print("2) Token expiry:")
if app_id and app_secret:
    r = requests.get(f"https://graph.facebook.com/{VERSION}/debug_token",
                     params={"input_token": token, "access_token": f"{app_id}|{app_secret}"}, timeout=30)
    d = r.json().get("data", {})
    if d:
        exp = d.get("expires_at", 0)
        when = "never" if not exp else datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%d")
        print(f"  type: {d.get('type')}, valid: {d.get('is_valid')}, expires: {when}")
        print(f"  scopes: {', '.join(sorted(d.get('scopes', [])))}")
    else:
        print(f"  could not determine: {r.json().get('error', {}).get('message')}")
else:
    print("  META_APP_ID / META_APP_SECRET missing, skipped.")

print("\nResult:", "OK, " + ", ".join(ok) if ok else "token did not work on any host")
