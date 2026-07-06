"""In-process + on-disk cache for LLM/simulation outputs (ARCHITECTURE.md §4.3, §5).

Re-clicking an event must be instant and must not re-spend droplet hours
(PROMPTS.md cache policy). Keys:
  - P1 briefing:   ("brief", event_id, event_revision)
  - simulation:    ("sim", event_id, horizon, baseline_hash)

Values are pydantic models; on disk they are stored as JSON so the cache
survives a restart during the demo. The in-process dict is the fast path;
disk is the warm-start fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

_CACHE_DIR = Path(os.getenv("CACHE_DIR", ".cache"))
_MEM: dict[str, dict] = {}

T = TypeVar("T", bound=BaseModel)


def event_revision(event) -> str:
    """Stable short hash of the fields that would invalidate a briefing."""
    basis = f"{event.id}|{event.severity:.4f}|{event.title}|{event.started_at.isoformat()}"
    return hashlib.sha1(basis.encode()).hexdigest()[:12]


def baseline_hash(exposed_p10: int, exposed_p90: int) -> str:
    return hashlib.sha1(f"{exposed_p10}:{exposed_p90}".encode()).hexdigest()[:12]


def _key(*parts: str) -> str:
    return ":".join(parts)


def _disk_path(key: str) -> Path:
    safe = key.replace(":", "__").replace("/", "_")
    return _CACHE_DIR / f"{safe}.json"


def get(key_parts: tuple[str, ...], model: type[T]) -> T | None:
    key = _key(*key_parts)
    if key in _MEM:
        return model.model_validate(_MEM[key])
    path = _disk_path(key)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _MEM[key] = data
            return model.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError):
            return None
    return None


def put(key_parts: tuple[str, ...], value: BaseModel) -> None:
    key = _key(*key_parts)
    data = value.model_dump(mode="json")
    _MEM[key] = data
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _disk_path(key).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        # Disk cache is best-effort; the in-process copy still serves the demo.
        pass


def clear_memory() -> None:
    """Test hook — drop the in-process layer (disk untouched)."""
    _MEM.clear()
