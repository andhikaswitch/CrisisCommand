"""Active-event store with GPU dedup and per-source freshness.

Holds the events shown on the globe. In SEED mode it is preloaded with the
curated seed events and never mutated. In LIVE mode the scheduler feeds it
batches from each ingestor; new events are embedded on the GPU and matched
against the active set — a cosine match above threshold within
DEDUP_RADIUS_KM is merged, not duplicated (ARCHITECTURE.md §3).

Freshness per source (last success, error, staleness) drives the HUD dots.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import torch

from backend.ingest import embeddings
from backend.models import CrisisEvent

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=30)


@dataclass
class SourceHealth:
    source: str
    last_success: datetime | None = None
    last_error: str | None = None
    event_count: int = 0

    def status(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        if self.last_success is None:
            return "error" if self.last_error else "idle"
        if now - self.last_success > STALE_AFTER:
            return "stale"
        return "ok"


@dataclass
class IngestResult:
    source: str
    added: int = 0
    merged: int = 0
    skipped_error: bool = False
    added_events: list[CrisisEvent] = field(default_factory=list)


@dataclass
class EventStore:
    seed: bool = True
    force_cpu: bool = False
    _events: dict[str, CrisisEvent] = field(default_factory=dict)
    _emb: dict[str, torch.Tensor] = field(default_factory=dict)
    _sources: dict[str, SourceHealth] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.device = embeddings.get_device(self.force_cpu)
        if self.seed:
            self._load_seed()

    def _load_seed(self) -> None:
        from scripts.seed_events import load_seed_events

        for e in load_seed_events():
            self._insert(e)
        self._sources["SEED"] = SourceHealth(
            "SEED", last_success=datetime.now(timezone.utc), event_count=len(self._events)
        )

    @staticmethod
    def _text(e: CrisisEvent) -> str:
        return f"{e.kind} {e.title} {e.country}"

    def _insert(self, e: CrisisEvent, vec: torch.Tensor | None = None) -> None:
        self._events[e.id] = e
        if vec is None:
            vec = embeddings.embed([self._text(e)], self.device)[0]
        self._emb[e.id] = vec

    def _find_duplicate(self, e: CrisisEvent, vec: torch.Tensor) -> str | None:
        if not self._emb:
            return None
        ids = list(self._emb)
        mat = torch.stack([self._emb[i] for i in ids])  # [M, D]
        sims = embeddings.cosine_matrix(vec.unsqueeze(0), mat)[0]  # [M], one matmul
        # geographic gate on the above-threshold candidates only
        for j in torch.nonzero(sims >= embeddings.SIM_THRESHOLD).flatten().tolist():
            cid = ids[j]
            other = self._events[cid]
            if embeddings.haversine_km(e.lat, e.lon, other.lat, other.lon) <= embeddings.DEDUP_RADIUS_KM:
                return cid
        return None

    def _merge(self, existing_id: str, incoming: CrisisEvent) -> None:
        """Keep the existing event; adopt the higher severity + newer info."""
        cur = self._events[existing_id]
        if incoming.severity > cur.severity:
            self._events[existing_id] = cur.model_copy(
                update={"severity": incoming.severity, "raw": {**cur.raw, "merged_from": incoming.source}}
            )

    def add_from_source(
        self, source: str, events: list[CrisisEvent], error: str | None = None
    ) -> IngestResult:
        """Ingest a batch: dedup against the active set, update freshness."""
        health = self._sources.setdefault(source, SourceHealth(source))
        if error is not None:
            health.last_error = error
            logger.warning("ingest error from %s: %s", source, error)
            return IngestResult(source, skipped_error=True)

        result = IngestResult(source)
        if events:
            vecs = embeddings.embed([self._text(e) for e in events], self.device)
            for idx, e in enumerate(events):
                vec = vecs[idx]
                dup = self._find_duplicate(e, vec)
                if dup is not None:
                    self._merge(dup, e)
                    result.merged += 1
                else:
                    self._insert(e, vec)
                    result.added += 1
                    result.added_events.append(e)

        health.last_success = datetime.now(timezone.utc)
        health.last_error = None
        health.event_count = sum(1 for e in self._events.values() if e.source == source)
        logger.info(
            "ingest %s: +%d new, %d merged (%d active total)",
            source, result.added, result.merged, len(self._events),
        )
        return result

    # --- read API ---------------------------------------------------------
    def snapshot(self) -> list[CrisisEvent]:
        return list(self._events.values())

    def get(self, event_id: str) -> CrisisEvent | None:
        return self._events.get(event_id)

    def source_health(self) -> list[SourceHealth]:
        return list(self._sources.values())
