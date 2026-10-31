"""The agent's "brain": calls the Claude Code CLI in headless mode (within the Pro subscription).

Each call runs in an empty temporary directory, without project settings or MCP servers.
When `tools` is empty the model cannot use any tool (files, terminal, internet), so that
a "command" inside untrusted text (a comment, a page) cannot do anything.
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
            log.warning("LLM attempt %d/%d failed: %s", attempt, retries, e)
            time.sleep(2 * attempt)
    raise LLMError(f"LLM did not respond: {last}")
