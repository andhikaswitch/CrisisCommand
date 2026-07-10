"""Minimal .env loader — no extra dependency.

Docker passes env vars through `env_file`, but a bare `uvicorn backend.main:app`
would otherwise never see FIREWORKS_API_KEY, and the app would silently serve
template briefings. Import this before anything reads os.getenv.

Real environment variables always win: values are only set when absent, so
`SIM_BACKEND=vllm uvicorn ...` still overrides the file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None, force: bool = False) -> int:
    """Populate os.environ from a .env file. Returns how many keys were set.

    Under pytest this is a no-op: tests must be hermetic and must never spend
    a live API key just because a developer has one in .env. Pass force=True
    to load explicitly (check_fireworks.py does).
    """
    if not force and "pytest" in sys.modules:
        return 0
    env_path = path or _ROOT / ".env"
    if not env_path.exists():
        return 0
    count = 0
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count
