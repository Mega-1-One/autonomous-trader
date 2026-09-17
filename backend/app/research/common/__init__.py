"""Shared research utilities (P-08/C-04).

Single implementations of the most-duplicated research helpers. Behavior is
preserved exactly (lenient hash default, identical BH math, identical tick
windows); each engine rewire is verified by that phase's existing test.
"""
from app.research.common.dataset_hash import verify_dataset_hash, load_manifest
from app.research.common.statistical_tests import compute_fdr_correction
from app.research.common.mt5_ticks import fetch_real_ticks
from app.research.common.splits import chronological_split_indices
from app.research.common.metrics import profit_factor, expectancy, win_rate

__all__ = [
    "verify_dataset_hash",
    "load_manifest",
    "compute_fdr_correction",
    "fetch_real_ticks",
    "chronological_split_indices",
    "profit_factor",
    "expectancy",
    "win_rate",
]
