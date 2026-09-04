"""Tests for direction-aware signal monitoring (SearchAlert.action).

Covers the smart-signal-center fixes:
1. ``SignalMonitorService._resolve_direction`` — explicit action wins
   (sell → short, buy → long); hold/watch and legacy rows fall back to the
   historical target<entry geometry.
2. ``_evaluate_alert`` uses short semantics for sell alerts
   (price >= stop → stop-loss trigger; price <= target → target trigger).
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from python_service.app.db.models import SearchAlert
from python_service.app.services.signal_monitor_service import SignalMonitorService


def _make_alert(**kwargs) -> SearchAlert:
    defaults = {
        "symbol": "600378",
        "market": "A-Share",
        "name": "昊华科技",
        "entry_price": 30.0,
        "target_price": 25.0,
        "stop_loss": 32.0,
        "currency": "CNY",
    }
    defaults.update(kwargs)
    return SearchAlert(**defaults)


def _service() -> SignalMonitorService:
    return SignalMonitorService(MagicMock())


# ---------------------------------------------------------------------------
# 1. _resolve_direction
# ---------------------------------------------------------------------------

def test_explicit_sell_action_is_short_even_with_long_geometry():
    alert = _make_alert(action="sell", target_price=35.0)  # target ABOVE entry
    assert SignalMonitorService._resolve_direction(alert) is True


def test_explicit_buy_action_is_long_even_with_short_geometry():
    alert = _make_alert(action="buy")  # target below entry by default
    assert SignalMonitorService._resolve_direction(alert) is False


def test_hold_watch_and_legacy_rows_fall_back_to_geometry():
    assert SignalMonitorService._resolve_direction(_make_alert(action="hold")) is True
    assert SignalMonitorService._resolve_direction(_make_alert(action="watch")) is True
    assert SignalMonitorService._resolve_direction(_make_alert()) is True  # legacy: no action
    assert SignalMonitorService._resolve_direction(
        _make_alert(action="hold", target_price=35.0)
    ) is False


def test_blank_or_case_variant_action_normalizes():
    assert SignalMonitorService._resolve_direction(_make_alert(action="SELL")) is True
    assert SignalMonitorService._resolve_direction(_make_alert(action=" Buy ")) is False
    assert SignalMonitorService._resolve_direction(_make_alert(action="")) is True  # geometry


# ---------------------------------------------------------------------------
# 2. _evaluate_alert semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sell_alert_triggers_stop_loss_when_price_rises_above_stop():
    svc = _service()
    alert = _make_alert(action="sell")
    await svc._evaluate_alert(alert, current_price=33.0)  # 33 >= stop 32
    svc.alert_repo.mark_triggered.assert_called_once()
    args = svc.alert_repo.mark_triggered.call_args[0]
    assert args[1] == "stop_loss"


@pytest.mark.asyncio
async def test_sell_alert_triggers_target_when_price_falls_to_target():
    svc = _service()
    alert = _make_alert(action="sell")
    await svc._evaluate_alert(alert, current_price=24.0)  # 24 <= target 25
    svc.alert_repo.mark_triggered.assert_called_once()
    args = svc.alert_repo.mark_triggered.call_args[0]
    assert args[1] == "target"


@pytest.mark.asyncio
async def test_buy_alert_keeps_long_semantics():
    svc = _service()
    alert = _make_alert(action="buy", entry_price=10.0, target_price=12.0, stop_loss=9.0)
    await svc._evaluate_alert(alert, current_price=12.5)  # 12.5 >= target 12
    svc.alert_repo.mark_triggered.assert_called_once()
    args = svc.alert_repo.mark_triggered.call_args[0]
    assert args[1] == "target"


@pytest.mark.asyncio
async def test_legacy_alert_without_action_uses_geometry_fallback():
    """Legacy row with target < entry keeps short semantics (backward compat)."""
    svc = _service()
    alert = _make_alert()  # no action, target 25 < entry 30 → short
    await svc._evaluate_alert(alert, current_price=24.0)
    svc.alert_repo.mark_triggered.assert_called_once()
    args = svc.alert_repo.mark_triggered.call_args[0]
    assert args[1] == "target"
