"""Single source of truth for naming the compute device.

ROCm reality check: on some AMD cards `torch.cuda.get_device_name()` and
`properties.name` return an EMPTY string (observed on gfx1100 / Radeon PRO
W7900 under ROCm 7.2 — libdrm cannot resolve the marketing name, and even
`rocm-smi --showproductname` reports "get_name, Error when calling libdrm").

We therefore fall back through: marketing name -> properties.name ->
gcnArchName (always present) -> a generic label. The UI shows whatever this
returns, so a blank footer becomes an honest "AMD GPU (gfx1100)" instead.

CLAUDE.md: never hardcode or guess a GPU model. gfx1100 is RDNA3, NOT an
Instinct part — claiming otherwise would be the same fake precision this
project forbids for casualty numbers.
"""

from __future__ import annotations

import torch

GENERIC = "AMD GPU"


def device_label(index: int = 0) -> str:
    """Best available human name for CUDA/ROCm device `index`."""
    if not torch.cuda.is_available():
        return "cpu"
    name = ""
    try:
        name = (torch.cuda.get_device_name(index) or "").strip()
    except (RuntimeError, AssertionError):
        name = ""
    if name:
        return name

    try:
        props = torch.cuda.get_device_properties(index)
    except (RuntimeError, AssertionError):
        return GENERIC

    prop_name = (getattr(props, "name", "") or "").strip()
    if prop_name:
        return prop_name

    arch = (getattr(props, "gcnArchName", "") or "").strip()
    if arch:
        # e.g. "AMD GPU (gfx1100)" — truthful, and enough for judges to look up
        return f"{GENERIC} ({arch})"
    return GENERIC
