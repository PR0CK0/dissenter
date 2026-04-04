from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .paths import db_path as _paths_db_path, dissenter_home


def get_db_path() -> Path:
    from .paths import ensure_dirs
    ensure_dirs()
    return _paths_db_path()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    if db_path is None:
        db_path = get_db_path()
    with _connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id          INTEGER PRIMARY KEY,
                timestamp   TEXT NOT NULL,
                question    TEXT NOT NULL,
                config_toml TEXT NOT NULL,
                decision_md TEXT NOT NULL,
                run_dir     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rounds (
                id          INTEGER PRIMARY KEY,
                run_id      INTEGER NOT NULL REFERENCES runs(id),
                round_index INTEGER NOT NULL,
                name        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS model_outputs (
                id          INTEGER PRIMARY KEY,
                round_id    INTEGER NOT NULL REFERENCES rounds(id),
                model_id    TEXT NOT NULL,
                role        TEXT NOT NULL,
                auth        TEXT NOT NULL DEFAULT 'api',
                content_md  TEXT,
                error_msg   TEXT,
                elapsed_ms  INTEGER
            );
        """)


def save_run(
    question: str,
    config_toml: str,
    decision_md: str,
    run_dir: str,
    rounds: list[dict],
    db_path: Path | None = None,
) -> int:
    """Persist a completed run and return its run ID.

    rounds: list of dicts with keys:
        round_index (int), name (str),
        outputs (list of dicts: model_id, role, auth, content_md, error_msg, elapsed_ms)
    """
    if db_path is None:
        db_path = get_db_path()
    init_db(db_path)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO runs (timestamp, question, config_toml, decision_md, run_dir) "
            "VALUES (?, ?, ?, ?, ?)",
            (ts, question, config_toml, decision_md, run_dir),
        )
        run_id = cur.lastrowid

        for rd in rounds:
            cur2 = conn.execute(
                "INSERT INTO rounds (run_id, round_index, name) VALUES (?, ?, ?)",
                (run_id, rd["round_index"], rd["name"]),
            )
            round_id = cur2.lastrowid
            for out in rd.get("outputs", []):
                conn.execute(
                    "INSERT INTO model_outputs "
                    "(round_id, model_id, role, auth, content_md, error_msg, elapsed_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        round_id,
                        out["model_id"],
                        out["role"],
                        out.get("auth", "api"),
                        out.get("content_md"),
                        out.get("error_msg"),
                        out.get("elapsed_ms"),
                    ),
                )

    return run_id


def list_runs(
    limit: int = 20,
    search: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """Return recent runs, newest first. Optionally filter by question keyword."""
    if db_path is None:
        db_path = get_db_path()
    init_db(db_path)

    with _connect(db_path) as conn:
        if search is not None:
            rows = conn.execute(
                "SELECT id, timestamp, question, run_dir FROM runs "
                "WHERE question LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{search}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, timestamp, question, run_dir FROM runs "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    return [dict(row) for row in rows]


def delete_run(run_id: int, db_path: Path | None = None) -> None:
    """Delete a run and its associated rounds and model outputs."""
    if db_path is None:
        db_path = get_db_path()
    init_db(db_path)

    with _connect(db_path) as conn:
        # Foreign keys are ON, but delete children explicitly for clarity
        round_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM rounds WHERE run_id = ?", (run_id,)
            ).fetchall()
        ]
        for rid in round_ids:
            conn.execute("DELETE FROM model_outputs WHERE round_id = ?", (rid,))
        conn.execute("DELETE FROM rounds WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))


def get_run(run_id: int, db_path: Path | None = None) -> dict | None:
    """Return a full run with nested rounds and model outputs, or None."""
    if db_path is None:
        db_path = get_db_path()
    init_db(db_path)

    with _connect(db_path) as conn:
        run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run_row is None:
            return None

        run = dict(run_row)
        round_rows = conn.execute(
            "SELECT * FROM rounds WHERE run_id = ? ORDER BY round_index", (run_id,)
        ).fetchall()

        rounds = []
        for rnd in round_rows:
            rnd_dict = dict(rnd)
            outputs = conn.execute(
                "SELECT * FROM model_outputs WHERE round_id = ?", (rnd_dict["id"],)
            ).fetchall()
            rnd_dict["outputs"] = [dict(o) for o in outputs]
            rounds.append(rnd_dict)

        run["rounds"] = rounds

    return run
