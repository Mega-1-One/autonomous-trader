import pytest
from app.research.audit_engine import ResearchAuditEngine

def test_research_audit_coverage():
    audit_engine = ResearchAuditEngine()
    fake_ticks = [{"timestamp": 1000.0 + i*10, "bid": 2400.0, "ask": 2400.2} for i in range(1000)]

    coverage = audit_engine.audit_coverage("XAUUSD", fake_ticks)
    assert coverage.total_ticks == 1000
    assert coverage.symbol == "XAUUSD"
    assert coverage.recommended_min_history_months == 12

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
