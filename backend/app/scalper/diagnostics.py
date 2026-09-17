from dataclasses import dataclass, field
from typing import Dict, List, Any

@dataclass
class DiagnosticFunnel:
    raw_ticks_ingested: int = 0
    ticks_passed_validation: int = 0
    ticks_passed_spread: int = 0
    ticks_regime_allowed: int = 0
    strategy_signals_evaluated: int = 0
    signals_passed_momentum: int = 0
    signals_passed_imbalance: int = 0
    signals_passed_fusion: int = 0
    signals_passed_risk: int = 0
    paper_trades_executed: int = 0
    near_misses: List[Dict[str, Any]] = field(default_factory=list)

    def print_funnel_summary(self, symbol: str) -> None:
        total = max(1, self.raw_ticks_ingested)
        print("\n==================================================")
        print(f" DIAGNOSTIC FUNNEL SUMMARY: {symbol}")
        print("==================================================")
        print(f"1. Raw Ticks Ingested:        {self.raw_ticks_ingested:,} (100.0%)")
        print(f"2. Passed Tick Validation:     {self.ticks_passed_validation:,} ({(self.ticks_passed_validation/total)*100:.2f}%)")
        print(f"3. Passed Spread Gate:         {self.ticks_passed_spread:,} ({(self.ticks_passed_spread/total)*100:.2f}%)")
        print(f"4. Passed Market Regime:       {self.ticks_regime_allowed:,} ({(self.ticks_regime_allowed/total)*100:.2f}%)")
        print(f"5. Strategy Signals Evaluated: {self.strategy_signals_evaluated:,} ({(self.strategy_signals_evaluated/total)*100:.2f}%)")
        print(f"6. Passed Momentum Gate:       {self.signals_passed_momentum:,} ({(self.signals_passed_momentum/total)*100:.2f}%)")
        print(f"7. Passed Imbalance Gate:      {self.signals_passed_imbalance:,} ({(self.signals_passed_imbalance/total)*100:.2f}%)")
        print(f"8. Passed Fusion Gate:         {self.signals_passed_fusion:,} ({(self.signals_passed_fusion/total)*100:.2f}%)")
        print(f"9. Passed Risk Gate:           {self.signals_passed_risk:,} ({(self.signals_passed_risk/total)*100:.2f}%)")
        print(f"10. Paper Trades Executed:     {self.paper_trades_executed:,} ({(self.paper_trades_executed/total)*100:.2f}%)")

        if hasattr(self, 'risk_rejection_reasons') and self.risk_rejection_reasons:
            print("\n[RISK REJECTION REASONS]:")
            for r_reason, r_cnt in self.risk_rejection_reasons.items():
                print(f"  - {r_reason}: {r_cnt:,} times")

        if self.near_misses:

            print(f"\n[NEAR MISSES RECORDED: {len(self.near_misses)}]")
            for nm in self.near_misses[:5]:
                print(f"  - {nm['symbol']} {nm['direction']} | Score: {nm['score']} (Req: {nm['required']}) | Would trade if threshold <= {nm['score']}")
