"""Locate the cockpit bundle in a checkout and in an installed distribution."""

from __future__ import annotations

from pathlib import Path
import sysconfig


def frontend_dist_path() -> Path:
    """Return the first bundled frontend directory containing ``index.html``."""
    candidates = (
        Path(__file__).resolve().parents[1] / "web" / "dist",
        Path(sysconfig.get_path("data")) / "share" / "zasi" / "web",
    )
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    # Keep the source checkout path in the error/readiness response when a
    # package was built without frontend assets.
    return candidates[0]
