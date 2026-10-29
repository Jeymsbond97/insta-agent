"""Oddiy JSON holat ombori: atomik yozish va jarayon ichidagi qulf."""
import json
import threading
from pathlib import Path
from typing import Any, Callable


class JsonStore:
    def __init__(self, path: Path, default: Any):
        self.path = path
        self.default = default
        self._lock = threading.Lock()

    def load(self) -> Any:
        if not self.path.exists():
            return json.loads(json.dumps(self.default))
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: Any) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def update(self, fn: Callable[[Any], Any]) -> Any:
        """fn holatni joyida o'zgartiradi (yoki yangisini qaytaradi); natija saqlanadi."""
        with self._lock:
            data = self.load()
            out = fn(data)
            data = data if out is None else out
            self.save(data)
            return data


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
