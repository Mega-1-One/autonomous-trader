"""Shared statistical-test helpers (P-08/C-04).

Single Benjamini-Hochberg FDR implementation (previously duplicated verbatim
in feature_discovery/statistical_testing.py and
macro_futures/macro_futures_engine.py).
"""
from typing import List, Tuple

import numpy as np


def compute_fdr_correction(
    raw_p_values: List[float], alpha: float = 0.05
) -> Tuple[List[float], List[bool]]:
    """Benjamini-Hochberg False Discovery Rate (FDR) procedure."""
    n = len(raw_p_values)
    if n == 0:
        return [], []

    sorted_indices = np.argsort(raw_p_values)
    sorted_p = np.array(raw_p_values)[sorted_indices]

    adjusted_p = np.zeros(n)
    cum_min = 1.0

    for i in range(n - 1, -1, -1):
        rank = i + 1
        adj = (sorted_p[i] * n) / rank
        cum_min = min(cum_min, adj)
        adjusted_p[sorted_indices[i]] = min(1.0, cum_min)

    is_sig = [adjusted_p[i] <= alpha for i in range(n)]
    return list(adjusted_p), is_sig
