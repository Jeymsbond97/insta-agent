"""Umumiy sozlamalar: yo'llar, .env, yaml konfiglar."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

STATE = ROOT / "state"
OUTPUT = ROOT / "output"
APPROVED = ROOT / "approved"
MEMORY = ROOT / "memory"
for d in (STATE, OUTPUT, APPROVED, MEMORY):
    d.mkdir(exist_ok=True)


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def load_yaml(rel: str, default=None):
    p = ROOT / rel
    if not p.exists():
        return {} if default is None else default
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def owner_chat_id() -> int | None:
    v = env("TELEGRAM_OWNER_CHAT_ID")
    return int(v) if v.lstrip("-").isdigit() else None
