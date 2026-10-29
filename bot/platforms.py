"""Izohlar uchun platforma adapterlari.

DryRun — hech narsa joylamaydi, faqat `state/dryrun_actions.jsonl` ga yozadi (kalitlar ulanmaguncha).
Instagram — Graph API (Business akkaunt). Endpointlar 6-bosqichda haqiqiy token bilan tekshiriladi.
"""
import logging
import time

import requests

from .config import STATE, env
from .store import append_jsonl

log = logging.getLogger(__name__)


class Platform:
    name = "base"

    def list_comments(self, media_id: str) -> list[dict]:
        raise NotImplementedError

    def reply(self, comment_id: str, text: str) -> str:
        raise NotImplementedError

    def hide(self, comment_id: str) -> None:
        raise NotImplementedError


class DryRun(Platform):
    name = "dryrun"

    def _log(self, action: str, **kw):
        append_jsonl(STATE / "dryrun_actions.jsonl", {"ts": time.time(), "action": action, **kw})
        log.info("[dry-run] %s %s", action, kw)

    def list_comments(self, media_id):
        return []

    def reply(self, comment_id, text):
        self._log("reply", comment_id=comment_id, text=text)
        return f"dry-{int(time.time())}"

    def hide(self, comment_id):
        self._log("hide", comment_id=comment_id)


class Instagram(Platform):
    name = "instagram"

    def __init__(self):
        self.token = env("IG_ACCESS_TOKEN")
        self.base = f"https://graph.facebook.com/{env('META_GRAPH_VERSION', 'v23.0')}"

    def _req(self, method, path, **params):
        params["access_token"] = self.token
        for attempt in range(3):
            try:
                r = requests.request(method, f"{self.base}/{path}", params=params, timeout=30)
                if r.status_code >= 500:
                    raise requests.HTTPError(r.text)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                log.warning("Instagram so'rovi qayta urinilmoqda: %s", e)
                time.sleep(3 * (attempt + 1))

    def list_comments(self, media_id):
        data = self._req("GET", f"{media_id}/comments", fields="id,text,username,timestamp,like_count")
        return [{"id": c["id"], "text": c.get("text", ""), "author": c.get("username", ""),
                 "ts": c.get("timestamp"), "media_id": media_id, "platform": self.name} for c in data.get("data", [])]

    def reply(self, comment_id, text):
        return self._req("POST", f"{comment_id}/replies", message=text).get("id", "")

    def hide(self, comment_id):
        self._req("POST", comment_id, hide="true")


def get_platform(name: str) -> Platform:
    if name == "instagram" and env("IG_ACCESS_TOKEN"):
        return Instagram()
    return DryRun()
