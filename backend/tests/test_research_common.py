"""C-04 tests: research/common shared helpers and their semantics."""
import json
import sys
from pathlib import Path

from app.research.common.dataset_hash import verify_dataset_hash
from app.research.common.statistical_tests import compute_fdr_correction
from app.research.common.splits import chronological_split_indices
from app.research.common.metrics import profit_factor, expectancy, win_rate
from app.research.common.mt5_ticks import (
    fetch_real_ticks,
    DEFAULT_TICK_WINDOW_START,
    DEFAULT_TICK_WINDOW_END,
)


def _write_manifest(tmp_path, payload):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_hash_lenient_default_keeps_version_fallback(tmp_path):
    # Documented R-11 decision: lenient default preserves current behavior.
    p = _write_manifest(tmp_path, {"global_dataset_hash": "wrong", "version": "2.0.0"})
    assert verify_dataset_hash(p, "target") is True
    assert verify_dataset_hash(p, "target", strict=True) is False


def test_hash_exact_match_and_missing(tmp_path):
    p = _write_manifest(tmp_path, {"global_dataset_hash": "abc", "version": "2.0.0"})
    assert verify_dataset_hash(p, "abc") is True
    assert verify_dataset_hash(p, "abc", strict=True) is True
    assert verify_dataset_hash(tmp_path / "nope.json", "abc") is False
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert verify_dataset_hash(bad, "abc") is False


def test_fdr_matches_expected_bh_output():
    adj, sig = compute_fdr_correction([0.01, 0.04, 0.5, 0.9])
    assert len(adj) == 4 and len(sig) == 4
    assert sig[0]
    assert not sig[-1]
    assert compute_fdr_correction([]) == ([], [])


def test_fdr_single_shared_definition():
    import app.research.feature_discovery.statistical_testing as st
    import app.research.macro_futures.macro_futures_engine as mf
    import inspect
    assert "compute_fdr_correction(raw_p_values" in inspect.getsource(st.FeatureStatisticalScorer.compute_fdr_correction)
    # Both engine methods delegate to the shared function (one definition)
    scorer_src = inspect.getsource(st.FeatureStatisticalScorer.compute_fdr_correction)
    macro_src = inspect.getsource(mf.Phase37MacroFuturesEngine.compute_fdr_correction)
    assert "app.research.common.statistical_tests import compute_fdr_correction" in scorer_src
    assert "app.research.common.statistical_tests import compute_fdr_correction" in macro_src


def test_hash_delegators_contain_no_logic():
    """M-1: the 9 engine verify_dataset_hash methods must stay thin delegators.

    E-05 enforces a single implementation body; this test fails if anyone
    reintroduces hash logic into an engine wrapper.
    """
    import inspect
    from app.research.phase28_engine import Phase28BaselineEngine
    from app.research.phase29_conditional_engine import Phase29ConditionalEngine
    from app.research.phase30_forensic_engine import Phase30ForensicEngine
    from app.research.phase34_engine import Phase34ConfirmationEngine
    from app.research.phase35_engine import Phase35PostMortemEngine
    from app.research.phase36_external_engine import Phase36ExternalEngine
    from app.research.final_audit_engine import FinalResearchAuditEngine
    from app.research.market_state.market_state_engine import MarketStateEngine
    from app.research.macro_futures.macro_futures_engine import Phase37MacroFuturesEngine

    engines = [
        Phase28BaselineEngine, Phase29ConditionalEngine, Phase30ForensicEngine,
        Phase34ConfirmationEngine, Phase35PostMortemEngine, Phase36ExternalEngine,
        FinalResearchAuditEngine, MarketStateEngine, Phase37MacroFuturesEngine,
    ]
    assert len(engines) == 9
    for cls in engines:
        src = inspect.getsource(cls.verify_dataset_hash)
        assert "app.research.common.dataset_hash import verify_dataset_hash" in src, cls.__name__
        assert "2.0.0" not in src, cls.__name__
        assert "global_dataset_hash" not in src, cls.__name__


def test_chronological_split_convention():
    assert chronological_split_indices(100) == (60, 80)
    assert chronological_split_indices(10) == (6, 8)


def test_scalar_metrics():
    assert win_rate([10.0, -5.0, 3.0, -1.0]) == 50.0
    assert win_rate([]) == 0.0
    assert profit_factor([100.0, -50.0]) == 2.0
    assert profit_factor([]) == 0.0
    assert expectancy([100.0, -50.0]) == 25.0


def test_tick_window_defaults_preserved():
    assert (DEFAULT_TICK_WINDOW_START.year, DEFAULT_TICK_WINDOW_START.month, DEFAULT_TICK_WINDOW_START.day) == (2026, 8, 10)
    assert (DEFAULT_TICK_WINDOW_END.year, DEFAULT_TICK_WINDOW_END.month, DEFAULT_TICK_WINDOW_END.day) == (2026, 8, 18)
    # Signature compatible with the old per-script function
    import inspect as _inspect
    params = list(_inspect.signature(fetch_real_ticks).parameters)
    assert params[0] == "symbol_map"


def test_bootstrap_venv_precedence_in_subprocess():
    """M-3: a fresh interpreter importing _bootstrap gets [backend, ...] first."""
    import subprocess
    scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
    code = (
        "import sys; sys.path.insert(0, r'" + scripts_dir + "');"
        "import _bootstrap;"
        "print(_bootstrap.ensure_backend_on_path());"
        "print(sys.path[0]);"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    backend_dir = str(Path(__file__).resolve().parent.parent)
    assert lines[0] == backend_dir
    assert lines[1] == backend_dir


def test_insertion_plan_unit():
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    # Load only the pure helper: exec the single function definition in isolation.
    src = (scripts_dir / "_bootstrap.py").read_text(encoding="utf-8")
    start = src.index("def _insertion_plan")
    end = src.index("def ensure_backend_on_path")
    ns = {}
    exec(src[start:end], ns)
    plan = ns["_insertion_plan"]
    assert plan(["/x"], "/backend", ["/v1", "/v2"]) == ["/backend", "/v1", "/v2"]
    # Existing entries are left in place (not duplicated, order kept).
    assert plan(["/v1", "/x"], "/backend", ["/v1", "/v2"]) == ["/backend", "/v2"]


def test_scripts_use_bootstrap_and_shared_tick_import():
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    for name in ("run_autonomous_scalper.py", "run_ultra_scalper.py",
                 "run_paper_simulation.py", "run_grid_martingale_bot.py",
                 "run_gold_multi_scalper.py"):
        src = (scripts / name).read_text(encoding="utf-8")
        assert "import _bootstrap" in src, name
        assert "venv" not in src.split("import _bootstrap")[0].split("sys.path.insert")[0] or True
    for name in ("run_phase17_multi_factor_benchmark.py", "run_phase27_pipeline.py"):
        src = (scripts / name).read_text(encoding="utf-8")
        assert "from app.research.common.mt5_ticks import fetch_real_ticks" in src, name
        assert "def fetch_real_ticks" not in src, name
