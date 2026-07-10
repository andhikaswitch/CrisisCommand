"""WebSocket hub: sim_progress, gpu_stats, event_new (ARCHITECTURE.md §6).

One ConnectionManager broadcasts JSON messages to every connected client.
The GPU stats ticker runs only while clients are connected, so an idle
backend costs nothing. Message shapes:

  {"type": "sim_progress", "event_id": ..., "stage": "monte_carlo",
   "runs_done": 6000, "runs_total": 10000, "gpu_util_pct": ..., "vram_gb": ...}
  {"type": "gpu_stats", "device": ..., "vram_used_gb": ..., "vram_total_gb": ...}
  {"type": "event_new", "event": {...}}          # Day 5, live ingestion
"""

from __future__ import annotations

import asyncio
import logging

import torch
from fastapi import WebSocket

logger = logging.getLogger(__name__)

GPU_TICK_SECONDS = 2.0


def gpu_snapshot() -> dict:
    """Current device stats for the HUD readout (also served over REST)."""
    # ROCM: ROCm presents as cuda; on any AMD Instinct card (MI300X, MI250,
    # MI210...) this self-reports the real device name and HBM numbers. Never
    # hardcode a model — the UI shows whatever this returns.
    if torch.cuda.is_available():
        idx = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(idx)
        return {
            "device": torch.cuda.get_device_name(idx),
            "backend": "gpu",
            "vram_total_gb": round(props.total_memory / 2**30, 1),
            "vram_used_gb": round(torch.cuda.memory_allocated(idx) / 2**30, 2),
        }
    return {"device": "cpu", "backend": "cpu", "vram_total_gb": None,
            "vram_used_gb": None}


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._gpu_task: asyncio.Task | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        if self._gpu_task is None or self._gpu_task.done():
            self._gpu_task = asyncio.create_task(self._gpu_ticker())

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_json(message)
            except Exception:  # client vanished mid-send
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_threadsafe(self, message: dict) -> None:
        """Fire-and-forget broadcast from sync code inside the event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (unit tests calling sync paths) — drop silently
        loop.create_task(self.broadcast(message))

    async def _gpu_ticker(self) -> None:
        while self._clients:
            await self.broadcast({"type": "gpu_stats", **gpu_snapshot()})
            await asyncio.sleep(GPU_TICK_SECONDS)


manager = ConnectionManager()
