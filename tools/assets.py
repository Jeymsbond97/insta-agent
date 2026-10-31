"""Search free sources for video, images and audio, download them and record their credits.

A provider with no key or no response is skipped.
Keys are never printed or logged.
"""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TIMEOUT = 20
OPENVERSE_TIMEOUT = 6  # Its search is often slow, so give up early and move on
ARCHIVE_MAX_BYTES = 500 << 20  # Internet Archive items can be whole films
ARCHIVE_MIN_IMAGE_BYTES = 200 << 10  # Its images often have no dimensions, so MIN_SIDE cannot catch tiny ones
HEADERS = {"User-Agent": "asset-fetcher/0.1 (https://github.com/Jeymsbond97/insta-agent)"}  # Required by Wikimedia
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
    ping_url: str = ""  # Unsplash rule: notify this URL on download


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
    params = {"key": key, "q": query[:100], "per_page": max(limit, 3), "safesearch": "true"}
    if kind == "image":
        params["image_type"] = "photo"
    data = _get(base, params=params)
    out = []
    for h in data.get("hits", [])[:limit]:
        if kind == "video":
            v = h["videos"].get("large") or {}
            if not v.get("url"):
                v = h["videos"]["medium"]
            url, w, hh = v["url"], v["width"], v["height"]
        else:
            url, w, hh = h["largeImageURL"], h["imageWidth"], h["imageHeight"]
        out.append(Asset("pixabay", kind, str(h["id"]), url, h["pageURL"], h["user"], "Pixabay Content License",
                         tags=[*h.get("tags", "").split(", "), h.get("type", "")], width=w, height=hh, duration=h.get("duration", 0)))
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
                  "Unsplash License", title=h.get("alt_description") or "", width=h["width"], height=h["height"],
                  ping_url=h["links"]["download_location"])
            for h in data.get("results", [])]


@provider("freesound", "audio")
def freesound(query: str, kind: str, limit: int) -> list[Asset]:
    key = os.environ.get("FREESOUND_API_KEY", "").strip()
    if not key:
        return []
    data = _get("https://freesound.org/apiv2/search/text/",
                params={"query": query, "token": key, "page_size": limit,
                        "fields": "id,name,url,username,license,previews,duration,tags"})
    return [Asset("freesound", "audio", str(h["id"]), h["previews"]["preview-hq-mp3"], h["url"], h["username"],
                  h["license"], title=h["name"], tags=h.get("tags") or [], duration=h.get("duration", 0))
            for h in data.get("results", [])]


@provider("wikimedia", "video", "image")
def wikimedia(query: str, kind: str, limit: int) -> list[Asset]:
    q = f"{query} filetype:{'video' if kind == 'video' else 'bitmap'}"
    data = _get("https://commons.wikimedia.org/w/api.php",
                params={"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                        "gsrsearch": q, "gsrlimit": limit, "prop": "imageinfo",
                        "iiprop": "url|size|extmetadata"})  # video duration is also returned by "size"
    out = []
    for p in (data.get("query") or {}).get("pages", {}).values():
        info = p["imageinfo"][0]
        meta = info.get("extmetadata") or {}
        author = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()
        out.append(Asset("wikimedia", kind, str(p["pageid"]), info["url"], info["descriptionurl"], author,
                         (meta.get("LicenseShortName") or {}).get("value", ""), title=p["title"],
                         width=info.get("width", 0), height=info.get("height", 0),
                         duration=float(info.get("duration") or 0)))
    return out


@provider("nasa", "video", "image")
def nasa(query: str, kind: str, limit: int) -> list[Asset]:
    data = _get("https://images-api.nasa.gov/search", params={"q": query, "media_type": kind})
    out = []
    for item in data["collection"]["items"][:limit]:
        d = item["data"][0]
        # File URLs live in a separate list
        files = _get(item["href"])
        ext = ".mp4" if kind == "video" else ".jpg"
        urls = [u for u in files if u.endswith(ext)]
        if not urls:
            continue
        url = next((u for u in urls if "~medium" in u or "~large" in u), urls[0]).replace("http://", "https://")
        out.append(Asset("nasa", kind, d["nasa_id"], url, f"https://images.nasa.gov/details/{d['nasa_id']}",
                         d.get("photographer") or d.get("center") or "NASA", "NASA Media Guidelines",
                         title=d.get("title", ""), tags=d.get("keywords") or []))
    return out


OPENVERSE_LICENSES = {"cc0": "CC0", "pdm": "Public Domain Mark", "by": "CC BY", "by-sa": "CC BY-SA"}


@provider("openverse", "image", "audio")
def openverse(query: str, kind: str, limit: int) -> list[Asset]:
    # Anonymous requests may not ask for more than 20 results per page
    data = _get(f"https://api.openverse.org/v1/{'images' if kind == 'image' else 'audio'}/",
                params={"q": query, "page_size": min(limit, 20), "license": ",".join(OPENVERSE_LICENSES)},
                timeout=OPENVERSE_TIMEOUT)
    out = []
    for h in data.get("results", []):
        name = OPENVERSE_LICENSES.get(h.get("license"), "")
        out.append(Asset("openverse", kind, h["id"], h["url"], h.get("foreign_landing_url") or h["url"],
                         h.get("creator") or "", f"{name} {h.get('license_version') or ''}".strip() if name else "",
                         title=h.get("title") or "",
                         tags=[*(t["name"] for t in h.get("tags") or []), h.get("category") or ""],
                         width=h.get("width") or 0, height=h.get("height") or 0,
                         duration=(h.get("duration") or 0) / 1000))  # Openverse reports milliseconds
    return out


def _archive_license(url: str) -> str:
    # The uploader chooses this value and the Archive does not verify it, so the credit says so
    url = str(url).lower()
    if "creativecommons.org/publicdomain/zero" in url:
        return "CC0 1.0 (uploader-declared)"
    if re.search(r"creativecommons\.org/(publicdomain/(mark|certification)|licenses/publicdomain)", url):
        return "Public Domain (uploader-declared)"
    return ""


def _archive_file(files: list, kind: str) -> dict | None:
    if kind == "video":
        usable = [f for f in files if f["name"].lower().endswith(".mp4")
                  and int(f.get("size") or 0) <= ARCHIVE_MAX_BYTES]
    else:
        usable = [f for f in files if f["name"].lower().endswith((".jpg", ".jpeg", ".png"))
                  and f.get("source") == "original"
                  and (f.get("width") or int(f.get("size") or 0) >= ARCHIVE_MIN_IMAGE_BYTES)]
    # Sharpest first, then the smallest file of that sharpness
    return max(usable, default=None, key=lambda f: (min(int(f.get("width") or 0), int(f.get("height") or 0)),
                                                    -int(f.get("size") or 0)))


@provider("internetarchive", "video", "image")
def internetarchive(query: str, kind: str, limit: int) -> list[Asset]:
    q = re.sub(r"[^\w\s-]", " ", query).strip()
    media = "movies" if kind == "video" else "image"
    data = _get("https://archive.org/advancedsearch.php",
                params={"q": f"(title:({q}) OR subject:({q})) AND mediatype:({media}) AND licenseurl:(*publicdomain*)",
                        "fl[]": ["identifier", "title", "creator", "licenseurl", "subject"],
                        "rows": limit, "output": "json"})
    out = []
    for h in data["response"]["docs"]:
        lic = _archive_license(h.get("licenseurl", ""))
        if not lic:
            continue
        # File details live in a separate document; one bad item must not lose the others
        try:
            f = _archive_file(_get(f"https://archive.org/metadata/{quote(h['identifier'])}").get("files", []), kind)
            if not f:
                continue
            duration = sum(float(p) * 60 ** i for i, p in enumerate(reversed(str(f.get("length") or 0).split(":"))))
            width, height = int(f.get("width") or 0), int(f.get("height") or 0)
        except (requests.RequestException, KeyError, ValueError):
            continue
        creator, subject = h.get("creator") or "", h.get("subject") or []
        out.append(Asset("internetarchive", kind, h["identifier"],
                         f"https://archive.org/download/{quote(h['identifier'])}/{quote(f['name'])}",
                         f"https://archive.org/details/{h['identifier']}",
                         ", ".join(creator) if isinstance(creator, list) else creator, lic,
                         title=str(h.get("title") or ""), tags=[subject] if isinstance(subject, str) else subject,
                         width=width, height=height, duration=duration))
    return out


# --- filter ---
AI_WORDS = ("ai generated", "ai-generated", "midjourney", "stable diffusion", "dall-e", "dalle", "generative ai")
RENDERED_RE = re.compile(
    r"(?<![a-z0-9])(?:3d|renders?|rendered|rendering|animations?|animated|cartoons?|illustrations?|cgi|simulations?"
    r"|green[\s_-]?screen|chroma[\s_-]?key|computer[\s_-]generated|artist'?s?[\s_-]concept(?:ion)?)(?![a-z0-9])")
MIN_SIDE = {"video": 720, "image": 1080}
MIN_VIDEO_SECONDS = 3
OPEN_LICENSE_RE = re.compile(r"(?:cc0|public domain(?: mark)?|cc by(?:-sa)?)(?: |$)")  # Excludes every NC and ND form


def license_ok(a: Asset) -> bool:
    lic = a.license.lower()
    if a.source == "freesound":
        # CC0 and CC-BY only
        return "publicdomain/zero" in lic or "creative commons 0" in lic or "/by/" in lic or lic == "attribution"
    if a.source in ("openverse", "internetarchive"):
        return bool(OPEN_LICENSE_RE.match(lic))
    if a.source == "wikimedia":
        if "-nc" in lic or "-nd" in lic:
            return False
        return lic.startswith(("cc0", "cc by", "public domain", "pd"))
    return bool(lic)


def keep(a: Asset, allow_rendered: bool = False) -> bool:
    text = " ".join([a.title, *a.tags]).lower()
    if any(w in text for w in AI_WORDS) or not license_ok(a):
        return False
    if not allow_rendered and RENDERED_RE.search(text):
        return False
    side = MIN_SIDE.get(a.kind, 0)
    if a.width and a.height and min(a.width, a.height) < side:
        return False
    if a.kind == "video" and a.duration and a.duration < MIN_VIDEO_SECONDS:
        return False
    return True


# --- search ---
def search(query: str, kind: str, limit: int = 10, only: str | None = None,
           allow_rendered: bool = False) -> list[Asset]:
    found = []
    for name, (kinds, fn) in PROVIDERS.items():
        if kind not in kinds or (only and name != only):
            continue
        # Uploaders set these licences themselves, so check each item by hand: explicit use only
        if name == "internetarchive" and only != name:
            continue
        try:
            found += fn(query, kind, limit)
        except Exception as e:
            # The error text may contain the URL (and key), so print only its type
            print(f"{name}: skipped ({type(e).__name__})", file=sys.stderr)
    return [a for a in found if keep(a, allow_rendered)]


# --- download ---
def download(a: Asset, out_dir: Path) -> Path:
    """Download the file to <out_dir>/assets/ and record it in credits.json. Existing files are not fetched again."""
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(urlparse(a.url).path).suffix or {"video": ".mp4", "image": ".jpg", "audio": ".mp3"}[a.kind]
    path = assets_dir / f"{a.source}_{re.sub(r'[^A-Za-z0-9_-]', '_', a.id)}{ext}"
    if not path.exists():
        tmp = path.with_suffix(path.suffix + ".part")
        with requests.get(a.url, headers=HEADERS, stream=True, timeout=TIMEOUT) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        tmp.rename(path)
        if a.ping_url:
            key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
            requests.get(a.ping_url, headers={**HEADERS, "Authorization": f"Client-ID {key}"}, timeout=TIMEOUT)
    add_credit(a, path, out_dir)
    return path


def add_credit(a: Asset, path: Path, out_dir: Path):
    credits_path = out_dir / "credits.json"
    data = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else []
    # A dict keeps its other sections; stock entries go in its "stock" list
    credits = data.setdefault("stock", []) if isinstance(data, dict) else data
    rel = str(path.relative_to(out_dir))
    if any(c.get("file") == rel for c in credits):
        return
    credits.append({"file": rel, "source": a.source, "url": a.page_url, "author": a.author,
                    "license": a.license, "fetched_at": date.today().isoformat()})
    credits_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("--type", "--kind", choices=["video", "image", "audio"], default="video")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", type=Path, help="If given, download the results to this folder")
    ap.add_argument("--provider", choices=sorted(PROVIDERS), help="Search only this provider")
    ap.add_argument("--allow-rendered", action="store_true",
                    help="Keep rendered, 3D, animated and green screen results, which are excluded by default")
    args = ap.parse_args()
    if args.provider and args.type not in PROVIDERS[args.provider][0]:
        ap.error(f"{args.provider} has no {args.type} results")
    for a in search(args.query, args.type, args.limit, args.provider, args.allow_rendered):
        print(f"{a.source:15} {a.width}x{a.height} {a.duration:5.0f}s  {a.license[:24]:24} {a.page_url}")
        if args.out:
            try:
                print("  ->", download(a, args.out))
            except requests.RequestException as e:
                print(f"  -> download failed ({type(e).__name__})", file=sys.stderr)


if __name__ == "__main__":
    main()
