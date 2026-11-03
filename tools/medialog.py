"""Ledger of media already used in finished videos, so no clip, photo or still is used twice.

Usage:
  python tools/medialog.py check FILE [FILE ...]      exit 1 if any file was used before
  python tools/medialog.py add VIDEO FILE [FILE ...]  record files as used by VIDEO
The ledger is assets/used_clips.json: {"video name": ["path", ...], keys starting with "_" are notes}.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "assets/used_clips.json"


def load(path: Path = LEDGER) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def used(ledger: dict) -> dict:
    """Map each used file to the first video it appeared in."""
    seen = {}
    for video, files in ledger.items():
        if video.startswith("_") or not isinstance(files, list):
            continue
        for f in files:
            seen.setdefault(f.split(" ")[0], video)
    return seen


def check(files: list[str], ledger: dict) -> dict:
    seen = used(ledger)
    return {f: seen[f] for f in files if f in seen}


def add(video: str, files: list[str], path: Path = LEDGER) -> dict:
    ledger = load(path)
    entry = ledger.setdefault(video, [])
    for f in files:
        if f not in entry:
            entry.append(f)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False), encoding="utf-8")
    return ledger


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("files", nargs="+")
    a = sub.add_parser("add")
    a.add_argument("video")
    a.add_argument("files", nargs="+")
    args = ap.parse_args()
    if args.cmd == "add":
        add(args.video, args.files)
        print("recorded", len(args.files), "files for", args.video)
        return
    clash = check(args.files, load())
    for f, video in clash.items():
        print(f"USED  {f}  (in {video})")
    sys.exit(1 if clash else 0)


if __name__ == "__main__":
    main()
