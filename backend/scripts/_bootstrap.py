"""Import-order-safe path setup for backend scripts (P-08/C-04, review R-10).

A helper *inside* the ``app`` package cannot provide the ``sys.path`` setup
that makes the package importable (chicken-and-egg). This thin module lives
at ``scripts/`` level so scripts import it first, before any ``app.*``
import::

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _bootstrap  # noqa: E402  (adds backend root + venv site-packages)
    _bootstrap.ensure_backend_on_path()

    from app.scripts...  # now importable
"""
import sys
from pathlib import Path


def _insertion_plan(existing, backend_dir: str, venv_sites: list) -> list:
    """Ordered sys.path prefix: backend root first, then venv site-packages.

    M-3: venv entries keep insert-0 precedence (behind the backend root) so a
    venv-installed package (e.g. MetaTrader5) shadows any globally installed
    copy — exactly the pre-C-04 runner headers' order ([backend, venv, ...]).
    Entries already present are left where they are.
    """
    present = set(existing)
    prefix = []
    if backend_dir not in present:
        prefix.append(backend_dir)
    for site in venv_sites:
        if site not in present and site not in prefix:
            prefix.append(site)
    return prefix


def ensure_backend_on_path() -> Path:
    """Puts the backend root (and optional venv site-packages) on sys.path."""
    backend_dir = Path(__file__).resolve().parent.parent
    venv_sites = [
        str(p) for p in (
            backend_dir / "venv" / "Lib" / "site-packages",
            backend_dir.parent / "venv" / "Lib" / "site-packages",
            backend_dir / "venv" / "lib",
        )
        if p.exists()
    ]
    for entry in reversed(_insertion_plan(sys.path, str(backend_dir), venv_sites)):
        sys.path.insert(0, entry)
    return backend_dir


ensure_backend_on_path()
