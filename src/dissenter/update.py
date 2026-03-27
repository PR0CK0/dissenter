from __future__ import annotations

import json
import threading
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from platformdirs import user_cache_dir

_CACHE_FILE = Path(user_cache_dir("dissenter")) / "update_check.json"
_CHECK_INTERVAL = timedelta(hours=24)
_PYPI_URL = "https://pypi.org/pypi/dissenter/json"

_latest_version: Optional[str] = None
_update_thread: Optional[threading.Thread] = None


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a version string to a comparable tuple, ignoring dev/local suffixes."""
    clean = v.split(".dev")[0].split("+")[0]
    try:
        return tuple(int(x) for x in clean.split("."))
    except ValueError:
        return (0,)


def _load_cache() -> dict:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(latest: str) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps({"latest": latest, "checked_at": datetime.now().isoformat()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _fetch_latest() -> Optional[str]:
    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=3) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception:
        return None


def _check_worker() -> None:
    global _latest_version
    cache = _load_cache()

    # Use cached value if still fresh
    if cache.get("latest") and cache.get("checked_at"):
        try:
            age = datetime.now() - datetime.fromisoformat(cache["checked_at"])
            if age < _CHECK_INTERVAL:
                _latest_version = cache["latest"]
                return
        except Exception:
            pass

    latest = _fetch_latest()
    if latest:
        _latest_version = latest
        _save_cache(latest)


def start_update_check() -> threading.Thread:
    """Kick off a background thread to check PyPI for a newer version."""
    global _update_thread
    _update_thread = threading.Thread(target=_check_worker, daemon=True)
    _update_thread.start()
    return _update_thread


def get_update_notice(current: str) -> Optional[str]:
    """Return an update notice if a newer version is available, else None.

    Joins the background thread with a short timeout so cached results
    are always available; first-run fetches that take longer are silently skipped.
    """
    if _update_thread:
        _update_thread.join(timeout=0.5)

    if not _latest_version:
        return None

    # Don't nag users running dev/local builds
    if ".dev" in current or "+" in current:
        return None

    if _version_tuple(_latest_version) > _version_tuple(current):
        return (
            f"v{_latest_version} available  "
            f"[dim](uv tool upgrade dissenter)[/dim]"
        )
    return None
