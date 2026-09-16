"""Shared chronological split helpers (P-08/C-04).

Reference implementation of the 60/20/20 chronological split convention used
across the research program (data_pipeline/dataset_splitter.py,
walk_forward_split.py, and several phase engines).

Note (deferred): consolidating the >=6 distinct split implementations into
one configurable function is follow-up material; this module is the shared
home and is already used by WalkForwardCalibrator. Engine rewires beyond
that are intentionally not in this tranche.
"""
from typing import Tuple


def chronological_split_indices(
    n: int, train_ratio: float = 0.60, val_ratio: float = 0.20
) -> Tuple[int, int]:
    """Returns (train_end, val_end) indices for a chronological split of n rows."""
    split1 = int(n * train_ratio)
    split2 = int(n * (train_ratio + val_ratio))
    return split1, split2
