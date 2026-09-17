"""Broker-adapter selection honoring EXECUTION_MODE (H-2 parity).

Single selection point shared by the API process (`app.api.deps`) and the
autonomous runner (`app.runner`) so both obey the same mode rules:

- ``PAPER`` / ``BACKTEST`` always return the mock adapter — paper workflows
  never depend on (or touch) a real terminal, on any host.
- ``DEMO`` / ``LIVE`` try the real terminal first and fall back to the mock.

The fallback is itself constrained by the safety gate: in ``LIVE`` a mock
destination is refused (``core.safety``), so a "live" process whose terminal
is down refuses orders instead of simulating fills. The DEMO fallback is
surfaced via ``/api/health`` ``simulated_execution``.
"""
from typing import Optional

from app.core import config as _config
from app.core.config import ExecutionMode
from app.data.mt5_interface import AbstractMT5Adapter
from app.data.mt5_mock import MockMT5Adapter
from app.data.mt5_real import RealMT5Adapter


def build_adapter(mode: Optional[ExecutionMode] = None) -> AbstractMT5Adapter:
    """Return the adapter appropriate for the effective (or given) mode."""
    mode = mode or _config.settings.EXECUTION_MODE
    if mode in (ExecutionMode.PAPER, ExecutionMode.BACKTEST):
        mock = MockMT5Adapter()
        mock.connect()
        return mock
    real_mt5 = RealMT5Adapter()
    if real_mt5.connect():
        return real_mt5
    mock = MockMT5Adapter()
    mock.connect()
    return mock
