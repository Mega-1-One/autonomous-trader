"""Shared dataset-manifest hash verification (P-08/C-04).

Explicit decision on hash semantics (review R-11): ``verify_dataset_hash``
defaults to the historical LENIENT behavior — a manifest whose
``version == "2.0.0"`` passes even when its hash differs from the target.
Pass ``strict=True`` to require an exact hash match. Tightening the default
is a separate, explicit decision (it would hard-fail re-runs on regenerated
datasets); it is NOT applied silently here. The current
``data/dataset_manifest.json`` matches the target hash, so both modes pass
today.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

LENIENT_VERSION_FALLBACK = "2.0.0"


def load_manifest(manifest_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Loads a dataset manifest, returning None when missing or malformed."""
    path = Path(manifest_path)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def verify_dataset_hash(
    manifest_path: Union[str, Path],
    target_hash: str,
    strict: bool = False,
) -> bool:
    """Verifies a dataset manifest against the target hash.

    Lenient default (documented above): accepts the version-"2.0.0"
    fallback. ``strict=True`` requires an exact hash match.
    """
    data = load_manifest(manifest_path)
    if data is None:
        return False
    if data.get("global_dataset_hash", "") == target_hash:
        return True
    if strict:
        return False
    return data.get("version") == LENIENT_VERSION_FALLBACK
