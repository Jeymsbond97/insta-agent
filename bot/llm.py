"""Agent "miyasi": Claude Code CLI'ni headless rejimda chaqiradi (Pro obuna doirasida).

Har chaqiruv bo'sh vaqtinchalik papkada, loyiha sozlamalari va MCP serverlarsiz ishlaydi.
`tools` bo'sh bo'lsa, model hech qanday vosita (fayl, terminal, internet) ishlata olmaydi —
begona matn (izoh, sahifa) ichidagi "buyruq" hech narsa qila olmasligi uchun.
"""
import json
import logging
import subprocess
import tempfile
import time

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def ask_json(system: str, prompt: str, schema: dict, *, model: str = "sonnet",
             tools: tuple[str, ...] = (), timeout: int = 180, retries: int = 3) -> dict:
    cmd = ["claude", "-p", "--model", model,
           "--tools", ",".join(tools),
           "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "",
           "--output-format", "json",
           "--system-prompt", system,
           "--json-schema", json.dumps(schema, ensure_ascii=False)]
    if tools:
        cmd += ["--allowedTools", *tools]
    last = None
    for attempt in range(1, retries + 1):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=tmp)
            data = json.loads(r.stdout)
            if data.get("is_error") or not isinstance(data.get("structured_output"), dict):
                raise LLMError(data.get("result") or r.stderr[:300])
            return data["structured_output"]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, LLMError) as e:
            last = e
            log.warning("LLM urinish %d/%d muvaffaqiyatsiz: %s", attempt, retries, e)
            time.sleep(2 * attempt)
    raise LLMError(f"LLM javob bermadi: {last}")
