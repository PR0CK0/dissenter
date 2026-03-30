"""Central path resolution for all dissenter storage.

Everything lives under one base directory (DISSENTER_HOME):

    ~/Documents/dissenter/
      decisions/         — debate output folders
      configs/           — named presets
      dissenter.db       — SQLite history

Resolution order:
  1. DISSENTER_HOME env var
  2. ~/.config/dissenter/home.txt (one line — the path)
  3. Default: ~/Documents/dissenter/
"""
from __future__ import annotations

import os
from pathlib import Path

_BOOTSTRAP_FILE = Path.home() / ".config" / "dissenter" / "home.txt"
_DEFAULT_HOME = Path.home() / "Documents" / "dissenter"


def dissenter_home() -> Path:
    """Return the base directory for all dissenter data."""
    # 1. Env var
    env = os.environ.get("DISSENTER_HOME")
    if env:
        return Path(env)

    # 2. Persisted setting
    if _BOOTSTRAP_FILE.exists():
        try:
            text = _BOOTSTRAP_FILE.read_text(encoding="utf-8").strip()
            if text:
                return Path(text)
        except Exception:
            pass

    # 3. Default
    return _DEFAULT_HOME


def decisions_dir() -> Path:
    return dissenter_home() / "decisions"


def configs_dir() -> Path:
    return dissenter_home() / "configs"


def db_path() -> Path:
    return dissenter_home() / "dissenter.db"


def set_home(path: str | Path) -> None:
    """Persist a custom DISSENTER_HOME to ~/.config/dissenter/home.txt."""
    p = Path(path).expanduser().resolve()
    _BOOTSTRAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BOOTSTRAP_FILE.write_text(str(p) + "\n", encoding="utf-8")


def ensure_dirs() -> None:
    """Create the base directory structure and migrate old data if needed."""
    _migrate_old_data()  # migrate BEFORE creating dirs so empty files don't block copy
    decisions_dir().mkdir(parents=True, exist_ok=True)
    configs_dir().mkdir(parents=True, exist_ok=True)


def _migrate_old_data() -> None:
    """Move DB and configs from old platformdirs locations to the new home."""
    import shutil
    try:
        from platformdirs import user_data_dir, user_config_dir
    except ImportError:
        return

    # Migrate DB — copy if old exists and new is missing or empty
    old_db = Path(user_data_dir("dissenter")) / "dissenter.db"
    new_db = db_path()
    if old_db.exists() and old_db.stat().st_size > 0:
        new_db.parent.mkdir(parents=True, exist_ok=True)
        if not new_db.exists() or new_db.stat().st_size < old_db.stat().st_size:
            shutil.copy2(old_db, new_db)

    # Migrate config presets
    old_cfg_dir = Path(user_config_dir("dissenter"))
    new_cfg_dir = configs_dir()
    if old_cfg_dir.exists():
        for f in old_cfg_dir.glob("*.toml"):
            dest = new_cfg_dir / f.name
            if not dest.exists():
                shutil.copy2(f, dest)


def open_in_finder(path: Path) -> None:
    """Open a file or directory in the OS file manager."""
    import subprocess
    import sys

    target = path if path.is_dir() else path.parent
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
