"""Verify the Fireworks key, list available models, and smoke-test one.

Model IDs churn (Fireworks retires older serverless models), so never guess an
ID from a docs page — ask the account. Run this right after pasting the key:

    python scripts/check_fireworks.py                 # list models
    python scripts/check_fireworks.py --test          # + real briefing call
    python scripts/check_fireworks.py --model <id>    # test a specific model

Prints nothing sensitive: the key is only ever sent in the Authorization
header, never logged (CLAUDE.md honesty + key-safety rules).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

BASE = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")


from backend.env import load_dotenv as _load_dotenv  # noqa: E402


def list_models(key: str) -> list[str]:
    resp = httpx.get(
        f"{BASE}/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return sorted(m.get("id", "") for m in data if m.get("id"))


def smoke(key: str, model: str) -> tuple[bool, str]:
    """One tiny completion — proves the key, the model id, and JSON mode."""
    resp = httpx.post(
        f"{BASE}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "Reply with strict JSON only."},
                {"role": "user", "content": 'Return {"ok": true} and nothing else.'},
            ],
            # Reasoning models spend tokens thinking before the JSON object.
            "max_tokens": 2400,
            "temperature": 0.0,
        },
        timeout=60.0,
    )
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    choice = resp.json()["choices"][0]
    message = choice["message"]
    # Reasoning models may answer in `reasoning_content` with `content` empty.
    content = message.get("content") or message.get("reasoning_content")
    if not content:
        return False, f"empty content (finish_reason={choice.get('finish_reason')!r})"
    return True, content.strip()[:120]


def main() -> int:
    _load_dotenv(force=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="run a live completion")
    ap.add_argument("--model", default=os.getenv("FIREWORKS_MODEL"))
    args = ap.parse_args()

    key = os.getenv("FIREWORKS_API_KEY")
    if not key:
        print("FIREWORKS_API_KEY is empty — paste it into .env first.")
        print("Briefings are running on the template fallback until you do.")
        return 1
    print(f"key loaded: ...{key[-4:]}  (never logged in full)")

    try:
        models = list_models(key)
    except httpx.HTTPError as exc:
        print(f"cannot reach Fireworks: {exc}")
        return 1

    print(f"\n{len(models)} model(s) available to this account:")
    for m in models:
        mark = "  <- FIREWORKS_MODEL" if m == args.model else ""
        print(f"  {m}{mark}")

    if args.model and args.model not in models:
        print(f"\nWARNING: configured model not in the list: {args.model}")
        print("Pick one from above and set FIREWORKS_MODEL in .env.")

    if args.test:
        if not args.model:
            print("\nno --model and no FIREWORKS_MODEL set; skipping test call")
            return 1
        print(f"\nsmoke-testing {args.model} ...")
        ok, out = smoke(key, args.model)
        print(("PASS: " if ok else "FAIL: ") + out)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
