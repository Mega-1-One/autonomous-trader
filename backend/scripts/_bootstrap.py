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


def ensure_backend_on_path() -> Path:
    """Puts the backend root (and optional venv site-packages) on sys.path."""
    backend_dir = Path(__file__).resolve().parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    for venv_site in (
        backend_dir / "venv" / "Lib" / "site-packages",
        backend_dir.parent / "venv" / "Lib" / "site-packages",
        backend_dir / "venv" / "lib",
    ):
        if venv_site.exists() and str(venv_site) not in sys.path:
            sys.path.append(str(venv_site))
    return backend_dir


ensure_backend_on_path()
