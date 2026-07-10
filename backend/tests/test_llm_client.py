"""LLM client wrapper: config gating, JSON extraction, unavailability."""

import asyncio

import pytest

from backend.llm.client import (
    LLMBadJSON,
    LLMClient,
    LLMConfig,
    LLMUnavailable,
    parse_json_object,
)


class TestConfig:
    def test_fireworks_needs_key(self):
        assert not LLMConfig("fireworks", "https://x/v1", "m").configured
        assert LLMConfig("fireworks", "https://x/v1", "m", api_key="k").configured

    def test_vllm_needs_only_endpoint(self):
        assert LLMConfig("vllm", "http://localhost:8001/v1", "m").configured


class TestUnconfiguredRaises:
    def test_chat_raises_llm_unavailable(self):
        client = LLMClient(LLMConfig("fireworks", "https://x/v1", "m"))  # no key
        with pytest.raises(LLMUnavailable):
            asyncio.run(client.chat([]))


class TestParseJsonObject:
    def test_plain_object(self):
        assert parse_json_object('{"a": 1}') == {"a": 1}

    def test_strips_json_fence(self):
        text = '```json\n{"a": 1, "b": [2, 3]}\n```'
        assert parse_json_object(text) == {"a": 1, "b": [2, 3]}

    def test_ignores_surrounding_prose(self):
        text = 'Here is the result:\n{"ok": true}\nHope that helps.'
        assert parse_json_object(text) == {"ok": True}

    def test_handles_braces_inside_strings(self):
        text = '{"desc": "use {curly} braces", "n": 2}'
        assert parse_json_object(text) == {"desc": "use {curly} braces", "n": 2}

    def test_first_balanced_object_only(self):
        text = '{"a": {"nested": 1}} trailing {"b": 2}'
        assert parse_json_object(text) == {"a": {"nested": 1}}

    def test_empty_raises(self):
        with pytest.raises(LLMBadJSON):
            parse_json_object("   ")

    def test_no_object_raises(self):
        with pytest.raises(LLMBadJSON):
            parse_json_object("no json here")

    def test_malformed_raises(self):
        with pytest.raises(LLMBadJSON):
            parse_json_object('{"a": 1,,}')


class TestReasoningModelResponses:
    """Reasoning models (gpt-oss, GLM, deepseek) shape responses differently."""

    def _resp(self, message: dict, finish: str = "stop") -> dict:
        return {"choices": [{"message": message, "finish_reason": finish}]}

    def test_reasoning_content_is_accepted_when_content_empty(self, monkeypatch):
        import httpx

        from backend.llm import client as c

        payload = self._resp({"role": "assistant", "reasoning_content": '{"ok": 1}'})

        async def fake_post(self, url, **kw):
            return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        cfg = c.LLMConfig(backend="fireworks", base_url="http://x/v1",
                          model="m", api_key="k")
        out = asyncio.run(c.LLMClient(cfg).chat([c.ChatMessage("user", "hi")]))
        assert c.parse_json_object(out) == {"ok": 1}

    def test_empty_content_raises_bad_json_with_finish_reason(self, monkeypatch):
        import httpx

        from backend.llm import client as c

        payload = self._resp({"role": "assistant", "content": ""}, finish="length")

        async def fake_post(self, url, **kw):
            return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        cfg = c.LLMConfig(backend="fireworks", base_url="http://x/v1",
                          model="m", api_key="k")
        with pytest.raises(c.LLMBadJSON, match="length"):
            asyncio.run(c.LLMClient(cfg).chat([c.ChatMessage("user", "hi")]))

    def test_default_max_tokens_fits_reasoning_preamble(self):
        from backend.llm import client as c

        # 900 truncated GLM 5.2 mid-JSON in live testing; keep real headroom.
        assert c.DEFAULT_MAX_TOKENS >= 2000


class TestDotenvHermeticity:
    def test_load_dotenv_is_noop_under_pytest(self):
        from backend.env import load_dotenv

        assert load_dotenv() == 0  # never spends a developer's live key
