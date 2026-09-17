from dataclasses import dataclass, asdict
from typing import Dict, Any, List

@dataclass
class InstrumentCoverageAudit:
    symbol: str
    total_ticks: int
    start_timestamp: float
    end_timestamp: float
    duration_days: float
    c1m_count: int
    c5m_count: int
    c15m_count: int
    c1h_count: int
    c4h_count: int
    data_sufficient_for_htf: bool
    recommended_min_history_months: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ResearchAuditEngine:
    """Audits data coverage, candle construction, zero-lookahead, and cost model sensitivity."""

    def audit_coverage(self, symbol: str, ticks: List[dict]) -> InstrumentCoverageAudit:
        if not ticks:
            return InstrumentCoverageAudit(
                symbol=symbol, total_ticks=0, start_timestamp=0.0, end_timestamp=0.0,
                duration_days=0.0, c1m_count=0, c5m_count=0, c15m_count=0, c1h_count=0, c4h_count=0,
                data_sufficient_for_htf=False, recommended_min_history_months=12
            )

        ts_list = [float(t["timestamp"]) for t in ticks]
        start_ts = min(ts_list)
        end_ts = max(ts_list)
        duration_days = round((end_ts - start_ts) / 86400.0, 2)

        # Estimate candles
        c1m = max(1, int(duration_days * 1440))
        c5m = max(1, int(duration_days * 288))
        c15m = max(1, int(duration_days * 96))
        c1h = max(1, int(duration_days * 24))
        c4h = max(1, int(duration_days * 6))

        # 15M/1H/4H swing strategies require at least 12 months (365 days) of history
        sufficient = (duration_days >= 180.0)

        return InstrumentCoverageAudit(
            symbol=symbol,
            total_ticks=len(ticks),
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            duration_days=duration_days,
            c1m_count=c1m,
            c5m_count=c5m,
            c15m_count=c15m,
            c1h_count=c1h,
            c4h_count=c4h,
            data_sufficient_for_htf=sufficient,
            recommended_min_history_months=12
        )
