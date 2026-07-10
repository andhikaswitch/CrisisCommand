"""device_label(): naming a GPU whose name torch reports as empty.

Observed on the AMD notebook: ROCm 7.2 + gfx1100 returns '' from both
get_device_name() and properties.name (libdrm cannot resolve the marketing
name). A blank device string would render an empty HUD footer.
"""

import pytest
import torch

from backend import device as dev


class _Props:
    def __init__(self, name="", arch="", total=48 * 2**30):
        self.name = name
        self.gcnArchName = arch
        self.total_memory = total


def _patch(monkeypatch, *, available=True, name="", props=None):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: available)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda i: name)
    if props is not None:
        monkeypatch.setattr(torch.cuda, "get_device_properties", lambda i: props)


class TestDeviceLabel:
    def test_cpu_when_no_gpu(self, monkeypatch):
        _patch(monkeypatch, available=False)
        assert dev.device_label() == "cpu"

    def test_marketing_name_wins(self, monkeypatch):
        _patch(monkeypatch, name="AMD Instinct MI300X", props=_Props())
        assert dev.device_label() == "AMD Instinct MI300X"

    def test_gfx1100_empty_name_falls_back_to_arch(self, monkeypatch):
        """The real notebook case: never render a blank device."""
        _patch(monkeypatch, name="", props=_Props(name="", arch="gfx1100"))
        assert dev.device_label() == "AMD GPU (gfx1100)"

    def test_properties_name_used_before_arch(self, monkeypatch):
        _patch(monkeypatch, name="", props=_Props(name="Radeon PRO W7900", arch="gfx1100"))
        assert dev.device_label() == "Radeon PRO W7900"

    def test_generic_when_everything_blank(self, monkeypatch):
        _patch(monkeypatch, name="", props=_Props(name="", arch=""))
        assert dev.device_label() == "AMD GPU"

    def test_never_returns_empty_string(self, monkeypatch):
        _patch(monkeypatch, name="", props=_Props(name="", arch=""))
        assert dev.device_label().strip()

    def test_properties_failure_degrades_to_generic(self, monkeypatch):
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        monkeypatch.setattr(torch.cuda, "get_device_name", lambda i: "")

        def boom(i):
            raise RuntimeError("no device")

        monkeypatch.setattr(torch.cuda, "get_device_properties", boom)
        assert dev.device_label() == "AMD GPU"
