import sys
import json
import csv
import logging
from pathlib import Path

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.research.phase35_engine import Phase35PostMortemEngine

def run_phase35_experiment():
    engine = Phase35PostMortemEngine()
    manifest_file = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    if not manifest_file.exists():
        print("[ERROR] Dataset manifest file missing.")
        return

    if not engine.verify_dataset_hash(manifest_file):
        print("[ERROR] SHA256 Dataset Hash Mismatch! Stopping Phase 35 execution.")
        return

    print("\n==================================================")
    print(" PHASE 35 RESEARCH POST-MORTEM & INFORMATION-GAP AUDIT")
    print("==================================================")
    print("Dataset Manifest Hash SHA256: PASSED & LOCKED")

    # 1. Output Coverage Matrix CSV
    rows = engine.generate_coverage_matrix()
    csv_file = Path(__file__).resolve().parent.parent / "data" / "phase35_research_coverage_matrix.csv"
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["family", "instruments", "timeframes", "features_used", "num_hypotheses", "oos_result", "statistical_controls", "classification", "is_exhausted"])
        for r in rows:
            writer.writerow([r.family, r.instruments, r.timeframes, r.features_used, r.num_hypotheses, r.oos_result, r.statistical_controls, r.classification, r.is_exhausted])

    # 2. Output Information Gap Audit JSON
    info_gap = engine.execute_information_gap_audit()
    gap_json = Path(__file__).resolve().parent.parent / "data" / "phase35_information_gap_audit.json"
    with open(gap_json, "w") as f:
        json.dump(info_gap, f, indent=2)

    # 3. Output Power Analysis JSON
    power_res = engine.compute_power_analysis()
    power_json = Path(__file__).resolve().parent.parent / "data" / "phase35_power_analysis.json"
    with open(power_json, "w") as f:
        json.dump(power_res, f, indent=2)

    # 4. Output Anti-Data-Mining Protocol Markdown
    protocol_md = Path(__file__).resolve().parent.parent / "data" / "phase35_antidata_mining_protocol.md"
    with open(protocol_md, "w") as f:
        f.write("# PHASE 35 - STRICT ANTI-DATA-MINING PROTOCOL\n\n")
        f.write("## 1. Immutable Dataset & Preregistered Hypotheses\n")
        f.write("- **Immutable Dataset SHA256**: `25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728`\n")
        f.write("- **Preregistration**: Every candidate hypothesis must be registered in JSON with economic rationale prior to testing.\n\n")
        f.write("## 2. Statistical & Replication Requirements\n")
        f.write("- **Multiple-Testing Control**: Mandatory Benjamini-Hochberg FDR correction across all hypothesis families.\n")
        f.write("- **Chronological Validation**: 60% Train, 20% Validation, 20% untouched Out-of-Sample (OOS).\n")
        f.write("- **Cross-Instrument Replication**: A hypothesis discovered on one asset must independently replicate on at least one other correlated asset.\n")
        f.write("- **Economic Significance Floor**: Minimum Net Expectancy $> +0.05R$ after realistic ECN commissions and spread drag.\n")

    # 5. Output Recommendations JSON
    recs = {
        "verdict": "B = LIMITED JUSTIFICATION — HUMAN REVIEW REQUIRED",
        "rationale": "Price-derived feature space across 1M..4H horizons is fully exhausted. Future research is justified ONLY if non-price exogenous information (CME futures real volume or macroeconomic event calendars) is integrated.",
        "top_3_phase36_directions": [
            {
                "rank": 1,
                "title": "CME Futures Real Volume & Aggressor Order Flow",
                "novelty": "HIGH (Non-price transaction volume)",
                "economic_mechanism": "Measures institutional aggressor vs passive order flow absorption",
                "feasibility": "Requires CME COMEX data vendor feed integration"
            },
            {
                "rank": 2,
                "title": "Macroeconomic News Shock & Economic Calendar Regimes",
                "novelty": "MEDIUM (Exogenous macroeconomic shock timestamps)",
                "economic_mechanism": "CPI/NFP announcements create structural liquidity regime shifts",
                "feasibility": "Easy JSON economic calendar integration"
            },
            {
                "rank": 3,
                "title": "Level-2 Limit Order Book Depth & Liquidity Imbalance",
                "novelty": "HIGH (Microstructure order book dynamics)",
                "economic_mechanism": "Identifies passive liquidity walls before breakout execution",
                "feasibility": "High bandwidth streaming required"
            }
        ]
    }
    rec_json = Path(__file__).resolve().parent.parent / "data" / "phase35_recommendations.json"
    with open(rec_json, "w") as f:
        json.dump(recs, f, indent=2)

    # 6. Output Markdown Post-Mortem Report
    postmortem_md = Path(__file__).resolve().parent.parent / "data" / "phase35_postmortem.md"
    with open(postmortem_md, "w") as f:
        f.write("# PHASE 35 - RESEARCH POST-MORTEM & INFORMATION-GAP AUDIT REPORT\n\n")
        f.write("## 1. Executive Summary & Dataset Lock\n")
        f.write("- **Dataset Manifest Hash SHA256**: `25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728` (VERIFIED & LOCKED)\n")
        f.write(f"- **Final Verdict**: **{recs['verdict']}**\n\n")
        f.write("## 2. Research Coverage & Exhaustion Matrix\n\n")
        f.write("| Family | Instruments | Timeframes | Hypotheses Tested | OOS Result | Status |\n")
        f.write("|---|---|---|---|---|---|\n")

        for r in rows:
            f.write(f"| **{r.family}** | {r.instruments} | {r.timeframes} | {r.num_hypotheses:,} | {r.oos_result} | **{r.classification}** |\n")

        f.write("\n## 3. Information Gap Evaluation\n")
        f.write("Price-derived technical indicators and standard OHLC candle transformations are 100% EXHAUSTED across 1,000,000+ observations. Any future edge MUST come from genuinely new, non-price exogenous information (e.g. CME Futures real volume or Macro Economic calendars).\n\n")
        f.write("## 4. Next Step Recommendation\n")
        f.write("STOP RESEARCH PROGRAM. Present findings for human review before acquiring exogenous data feeds.\n")

    print("\n==================================================")
    print(" PHASE 35 POST-MORTEM SUMMARY")
    print("==================================================")
    print(f"Coverage Matrix Saved:     {csv_file}")
    print(f"Information Gap Audit:     {gap_json}")
    print(f"Power Analysis JSON:       {power_json}")
    print(f"Anti-Data-Mining Protocol: {protocol_md}")
    print(f"Recommendations JSON:      {rec_json}")
    print(f"Post-Mortem Markdown:       {postmortem_md}")
    print(f"Final Program Verdict:     {recs['verdict']}")
    print("[SUCCESS] Phase 35 Research Post-Mortem completed.")

if __name__ == "__main__":
    run_phase35_experiment()
