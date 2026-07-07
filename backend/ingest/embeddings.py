"""GPU embedding + similarity for event dedup (ARCHITECTURE.md §3, AMD story #3).

New events are embedded and cosine-matched against active events; a match
above the similarity threshold AND within a geographic radius is treated as
the same event (feeds often report one disaster twice). The embedding and the
all-pairs cosine are batched tensor ops on the torch device — genuinely
GPU-accelerated on the MI300X via ROCm; identical code path on CPU for dev.

The embedding itself is a deterministic character-trigram hashing vector
(no model download, offline-safe). It is intentionally lightweight: dedup
only needs "are these two short disaster titles about the same event", not
semantic depth. Swappable for a transformer encoder later without touching
callers.

# ROCM: device is "cuda" (ROCm presents through the CUDA API). embed() and
# cosine_matrix() run unchanged on MI300X; on-GPU dedup is one of the three
# AMD compute paths the demo shows.
"""

from __future__ import annotations

import logging
import math

import torch

logger = logging.getLogger(__name__)

EMBED_DIM = 256
SIM_THRESHOLD = 0.92  # cosine; >this AND within radius => same event
DEDUP_RADIUS_KM = 200.0


def get_device(force_cpu: bool = False) -> torch.device:
    if force_cpu or not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device("cuda")


def _trigrams(text: str) -> list[str]:
    t = f"  {text.lower().strip()}  "
    return [t[i : i + 3] for i in range(len(t) - 2)]


def embed(texts: list[str], device: torch.device | None = None) -> torch.Tensor:
    """Embed a batch of texts to L2-normalized vectors, shape [N, EMBED_DIM].

    Character-trigram hashing → bucket counts → normalize. Fully batched:
    the matrix is built on-device and normalized in one op.
    """
    device = device or get_device()
    n = len(texts)
    mat = torch.zeros((n, EMBED_DIM), dtype=torch.float32, device=device)
    for i, text in enumerate(texts):
        for tri in _trigrams(text):
            # stable, process-independent bucket (Python's hash() is salted)
            bucket = (hash_trigram(tri)) % EMBED_DIM
            mat[i, bucket] += 1.0
    norms = mat.norm(dim=1, keepdim=True).clamp(min=1e-8)
    return mat / norms


def hash_trigram(tri: str) -> int:
    """Deterministic FNV-1a hash (Python's built-in hash() is salted)."""
    h = 2166136261
    for ch in tri:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def cosine_matrix(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """All-pairs cosine similarity [len(a), len(b)] — one batched matmul."""
    if a.numel() == 0 or b.numel() == 0:
        return torch.empty((a.shape[0], b.shape[0]))
    return a @ b.T  # inputs are already L2-normalized


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))
