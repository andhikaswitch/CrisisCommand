"""OpenAI-compatible chat client — one wrapper, two configs (CLAUDE.md).

Both Fireworks AI and the local vLLM server on the AMD GPU speak the same
OpenAI `/chat/completions` protocol, so a single async client serves both;
only the base URL, key, and model differ. Callers pick a backend by role:

    get_briefing_client()   -> Fireworks  (P1, quality-critical)
    get_scenario_client()   -> vLLM       (P2/P3, batched)  with Fireworks
                               fallback when the droplet is unreachable

If no backend is configured/reachable (typical local dev with no key and no
droplet), calls raise LLMUnavailable and the higher layers degrade to their
documented fallbacks (P1 -> raw-data brief, P2 -> template option). This is
what lets the whole simulate flow run offline in SEED mode.

JSON parsing tolerates models that wrap output in ```json fences despite
instructions, and extracts the first balanced object.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import httpx

# No default model that we cannot verify exists: Fireworks retires serverless
# models, so an unset FIREWORKS_MODEL must fail loudly via check_fireworks.py
# rather than 404 at demo time.
DEFAULT_FIREWORKS_MODEL = "accounts/fireworks/models/glm-5p2"
DEFAULT_VLLM_MODEL = "local-model"
# Reasoning-capable models spend hundreds of tokens thinking before the JSON
# object. 900 truncated GLM 5.2 mid-object; 2400 leaves room for the answer.
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2400"))
_TIMEOUT = httpx.Timeout(90.0, connect=10.0)


class LLMUnavailable(RuntimeError):
    """No usable backend, or the backend could not be reached."""


class LLMBadJSON(ValueError):
    """The model returned text that is not a usable JSON object."""


@dataclass(frozen=True)
class LLMConfig:
    backend: str  # "fireworks" | "vllm"
    base_url: str
    model: str
    api_key: str | None = None

    @property
    def configured(self) -> bool:
        # vLLM needs only a reachable endpoint; Fireworks needs a key.
        if self.backend == "fireworks":
            return bool(self.api_key)
        return bool(self.base_url)


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

    def as_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class LLMClient:
    """Async chat client for one OpenAI-compatible backend."""

    def __init__(self, config: LLMConfig):
        self.config = config

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.3,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        if not self.config.configured:
            raise LLMUnavailable(
                f"backend {self.config.backend!r} is not configured "
                "(missing API key or endpoint)"
            )
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "messages": [m.as_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
                resp = await http.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(
                f"{self.config.backend} call failed: {exc}"
            ) from exc
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMBadJSON(f"unexpected response shape: {exc}") from exc
        # Reasoning models (GLM, gpt-oss, deepseek...) may leave `content`
        # empty/absent and put the answer in `reasoning_content`. Accept both;
        # parse_json_object() strips any thinking prose around the object.
        content = message.get("content") or message.get("reasoning_content")
        if not content:
            finish = data["choices"][0].get("finish_reason")
            raise LLMBadJSON(f"empty response content (finish_reason={finish!r})")
        return content


def parse_json_object(text: str) -> dict:
    """Extract the first balanced JSON object from a model response.

    Tolerates ```json fences and leading/trailing prose. Raises LLMBadJSON
    when no parseable object is present.
    """
    if not text or not text.strip():
        raise LLMBadJSON("empty response")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # strip a leading ```json / ``` fence and its closing counterpart
        cleaned = cleaned.split("```", 2)
        cleaned = cleaned[1] if len(cleaned) > 1 else text
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start = cleaned.find("{")
    if start == -1:
        raise LLMBadJSON("no JSON object found in response")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise LLMBadJSON(f"malformed JSON object: {exc}") from exc
    raise LLMBadJSON("unbalanced JSON braces in response")


# --- Backend factories (config from env) ----------------------------------

def _fireworks_config() -> LLMConfig:
    return LLMConfig(
        backend="fireworks",
        base_url=os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"),
        model=os.getenv("FIREWORKS_MODEL", DEFAULT_FIREWORKS_MODEL),
        api_key=os.getenv("FIREWORKS_API_KEY"),
    )


def _vllm_config() -> LLMConfig:
    return LLMConfig(
        backend="vllm",
        base_url=os.getenv("VLLM_ENDPOINT", "http://localhost:8001/v1"),
        model=os.getenv("VLLM_MODEL", DEFAULT_VLLM_MODEL),
        api_key=os.getenv("VLLM_API_KEY"),  # vLLM usually needs none
    )


# Cached vLLM reachability probe — drives the honest fallback banner (§8).
_vllm_probe: dict = {"ts": 0.0, "ok": False}


async def vllm_reachable(ttl: float = 30.0) -> bool:
    """Whether the vLLM endpoint answers, cached for `ttl` seconds.

    Used by /api/status so the UI can show the FIREWORKS (FALLBACK) banner
    truthfully when the local vLLM endpoint isn't serving.
    """
    now = time.time()
    if now - _vllm_probe["ts"] < ttl:
        return _vllm_probe["ok"]
    cfg = _vllm_config()
    ok = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5, connect=1.0)) as http:
            resp = await http.get(cfg.base_url.rstrip("/") + "/models")
            ok = resp.status_code < 500
    except httpx.HTTPError:
        ok = False
    _vllm_probe.update(ts=now, ok=ok)
    return ok


def get_briefing_client() -> LLMClient:
    """P1 briefing — Fireworks (quality-critical, low volume)."""
    return LLMClient(_fireworks_config())


def get_scenario_client() -> LLMClient:
    """P2/P3 — vLLM on the AMD GPU, or Fireworks fallback per SIM_BACKEND.

    SIM_BACKEND=vllm (default on droplet) tries vLLM; if that config is not
    usable we fall through to Fireworks so local dev still works. The actual
    network-level fallback (droplet up but unreachable mid-call) is handled by
    callers catching LLMUnavailable.
    """
    backend = os.getenv("SIM_BACKEND", "fireworks").lower()
    if backend == "vllm":
        vllm = _vllm_config()
        if vllm.configured:
            return LLMClient(vllm)
    return LLMClient(_fireworks_config())
