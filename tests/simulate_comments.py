"""Izoh agentini sinov izohlari bilan tekshiradi (DryRun — hech narsa joylanmaydi).
Ishga tushirish: .venv/bin/python -m tests.simulate_comments [video_papka]
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bot.comments import CommentAgent, VideoContext
from bot.config import ROOT
from bot.platforms import DryRun

ctx = VideoContext.load(Path(sys.argv[1])) if len(sys.argv) > 1 else VideoContext.latest()
agent = CommentAgent(DryRun())
comments = json.loads((ROOT / "tests/sample_comments.json").read_text(encoding="utf-8"))

with ThreadPoolExecutor(4) as ex:
    results = list(ex.map(lambda c: (c, agent.analyze(c, ctx)), comments))

for c, d in results:
    print(f"\n💬 @{c['author']}: {c['text']}")
    print(f"   → {d['kind']} ({d['confidence']:.2f}) ⇒ {d['action'].upper()}")
    print(f"   ↳ {d['reply']}")
    print(f"   ℹ {d['reason']}")
