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
