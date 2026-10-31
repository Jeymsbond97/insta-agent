"""Bepul manbalardan video, rasm va tovush qidiradi, yuklaydi, manbasini yozib qo'yadi.

Kaliti yo'q yoki javob bermagan provayder o'tkazib yuboriladi.
Kalitlar ekranga va logga chiqarilmaydi.
"""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TIMEOUT = 20
HEADERS = {"User-Agent": "asset-fetcher/0.1 (python-requests)"}
PROVIDERS = {}


@dataclass
class Asset:
    source: str
    kind: str  # video | image | audio
    id: str
    url: str
    page_url: str
    author: str
    license: str
    title: str = ""
    tags: list = field(default_factory=list)
    width: int = 0
    height: int = 0
    duration: float = 0


def provider(name: str, *kinds: str):
    def wrap(fn):
        PROVIDERS[name] = (kinds, fn)
        return fn
    return wrap


def _get(url: str, **kw) -> dict:
    kw.setdefault("timeout", TIMEOUT)
    kw["headers"] = {**HEADERS, **kw.get("headers", {})}
    r = requests.get(url, **kw)
    r.raise_for_status()
    return r.json()


@provider("pixabay", "video", "image")
def pixabay(query: str, kind: str, limit: int) -> list[Asset]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    base = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    data = _get(base, params={"key": key, "q": query[:100], "per_page": max(limit, 3), "safesearch": "true"})
    out = []
    for h in data.get("hits", []):
        if kind == "video":
            v = h["videos"].get("large") or {}
            if not v.get("url"):
                v = h["videos"]["medium"]
            url, w, hh = v["url"], v["width"], v["height"]
        else:
            url, w, hh = h["largeImageURL"], h["imageWidth"], h["imageHeight"]
        out.append(Asset("pixabay", kind, str(h["id"]), url, h["pageURL"], h["user"], "Pixabay Content License",
                         tags=h.get("tags", "").split(", "), width=w, height=hh, duration=h.get("duration", 0)))
    return out


@provider("coverr", "video")
def coverr(query: str, kind: str, limit: int) -> list[Asset]:
    key = os.environ.get("COVERR_API_KEY", "").strip()
    if not key:
        return []
    data = _get("https://api.coverr.co/videos", params={"query": query, "page_size": limit, "urls": "true"},
                headers={"Authorization": f"Bearer {key}"})
    out = []
    for h in data.get("hits", []):
        urls = h.get("urls") or {}
        url = urls.get("mp4_download") or urls.get("mp4")
        if not url:
            continue
        out.append(Asset("coverr", "video", str(h["id"]), url, f"https://coverr.co/videos/{h['id']}", "Coverr",
                         "Coverr License", title=h.get("title", ""), tags=h.get("tags") or [],
                         width=h.get("max_width", 0), height=h.get("max_height", 0),
                         duration=float(h.get("duration") or 0)))
    return out


@provider("unsplash", "image")
def unsplash(query: str, kind: str, limit: int) -> list[Asset]:
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if not key:
        return []
    data = _get("https://api.unsplash.com/search/photos", params={"query": query, "per_page": limit},
                headers={"Authorization": f"Client-ID {key}"})
    return [Asset("unsplash", "image", h["id"], h["urls"]["regular"], h["links"]["html"], h["user"]["name"],
                  "Unsplash License", title=h.get("alt_description") or "", width=h["width"], height=h["height"])
            for h in data.get("results", [])]


# --- qidiruv ---
def search(query: str, kind: str, limit: int = 10) -> list[Asset]:
    found = []
    for name, (kinds, fn) in PROVIDERS.items():
        if kind not in kinds:
            continue
        try:
            found += fn(query, kind, limit)
        except Exception as e:
            # Xato matnida URL (va kalit) bo'lishi mumkin, faqat turini chiqaramiz
            print(f"{name}: o'tkazib yuborildi ({type(e).__name__})", file=sys.stderr)
    return found
