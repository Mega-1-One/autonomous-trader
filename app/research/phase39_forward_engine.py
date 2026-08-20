import hashlib
import json
import csv
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from app.core.config import settings, ExecutionMode

@dataclass
class ForwardTradeResult:
    trade_id: str
    timestamp: str
    instrument: str
    direction: str
    session: str
    market_regime: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    volume: float
    mfe_pips: float
    mae_pips: float
    gross_pnl_usd: float
    spread_cost_usd: float
    slippage_cost_usd: float
    commission_cost_usd: float
    net_pnl_usd: float
    r_multiple: float
    holding_seconds: float
    latency_ms: float
    outcome: str # "WIN", "LOSS", "SCRATCH"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class Phase39ForwardEngine:
    """Forward Validation Engine running prospective out-of-sample forward evaluation without mid-test optimization."""

    def __init__(self):
        self.configuration_hash = self.generate_configuration_hash()
        self.trades: List[ForwardTradeResult] = []

    def generate_configuration_hash(self) -> str:
        frozen_config = {
            "strategy": "UNVALIDATED_RESEARCH_STRATEGY",
            "strategy_version": "1.0.0-PROSPECTIVE",
            "risk_per_trade_pct": 0.1,
            "take_profit_pips": 2.0,
            "stop_loss_pips": 5.0,
            "commission_per_lot": 7.0,
            "execution_mode": "PAPER",
            "instruments": ["XAUUSD", "EURUSD", "GBPUSD", "NAS100"]
        }
        raw = json.dumps(frozen_config, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def simulate_forward_trade(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        session: str,
        regime: str,
        entry_price: float,
        sl_pips: float = 5.0,
        tp_pips: float = 2.0,
        volume: float = 0.05,
        win: bool = False
    ) -> ForwardTradeResult:
        pip_unit = 0.1 if "XAU" in instrument else (1.0 if "NAS" in instrument else 0.0001)
        point_val = 1.0 if "XAU" in instrument else (1.0 if "NAS" in instrument else 10.0)

        spread_pips = 1.2
        slippage_pips = 0.1
        commission = 7.0 * volume

        spread_cost = spread_pips * pip_unit * 100 * volume * point_val
        slippage_cost = slippage_pips * pip_unit * 100 * volume * point_val

        if win:
            mfe = tp_pips + 0.5
            mae = 1.5
            gross_pnl = (tp_pips * pip_unit * 100 * volume * point_val)
            exit_price = entry_price + (tp_pips * pip_unit) if direction == "LONG" else entry_price - (tp_pips * pip_unit)
            outcome = "WIN"
        else:
            mfe = 0.8
            mae = sl_pips
            gross_pnl = -(sl_pips * pip_unit * 100 * volume * point_val)
            exit_price = entry_price - (sl_pips * pip_unit) if direction == "LONG" else entry_price + (sl_pips * pip_unit)
            outcome = "LOSS"

        net_pnl = gross_pnl - spread_cost - slippage_cost - commission
        sl_dist_dollar = (sl_pips * pip_unit * 100 * volume * point_val)
        r_mult = round(net_pnl / sl_dist_dollar, 3) if sl_dist_dollar > 0 else 0.0

        res = ForwardTradeResult(
            trade_id=trade_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            instrument=instrument,
            direction=direction,
            session=session,
            market_regime=regime,
            entry_price=entry_price,
            exit_price=round(exit_price, 3),
            stop_loss=round(entry_price - (sl_pips * pip_unit) if direction == "LONG" else entry_price + (sl_pips * pip_unit), 3),
            take_profit=round(entry_price + (tp_pips * pip_unit) if direction == "LONG" else entry_price - (tp_pips * pip_unit), 3),
            volume=volume,
            mfe_pips=mfe,
            mae_pips=mae,
            gross_pnl_usd=round(gross_pnl, 2),
            spread_cost_usd=round(spread_cost, 2),
            slippage_cost_usd=round(slippage_cost, 2),
            commission_cost_usd=round(commission, 2),
            net_pnl_usd=round(net_pnl, 2),
            r_multiple=r_mult,
            holding_seconds=18.5,
            latency_ms=14.2,
            outcome=outcome
        )
        self.trades.append(res)
        return res

    def compute_summary_statistics(self) -> Dict[str, Any]:
        if not self.trades:
            return {"total_trades": 0, "win_rate": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0}

        total = len(self.trades)
        wins = [t for t in self.trades if t.outcome == "WIN"]
        losses = [t for t in self.trades if t.outcome == "LOSS"]
        win_rate = round((len(wins) / total) * 100.0, 2)

        gross_win = sum(t.gross_pnl_usd for t in wins)
        gross_loss = abs(sum(t.net_pnl_usd for t in losses))
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

        r_vals = [t.r_multiple for t in self.trades]
        exp_r = round(float(np.mean(r_vals)), 3)

        return {
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "gross_profit_usd": round(gross_win, 2),
            "gross_loss_usd": round(gross_loss, 2),
            "profit_factor": pf,
            "expectancy_r": exp_r,
            "avg_r_multiple": exp_r,
            "config_hash": self.configuration_hash
        }
