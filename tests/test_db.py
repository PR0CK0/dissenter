from __future__ import annotations

import pytest

from dissent.db import get_run, init_db, list_runs, save_run


def _round(index: int, name: str, outputs: list | None = None) -> dict:
    return {"round_index": index, "name": name, "outputs": outputs or []}


def _output(model_id: str = "ollama/mistral", role: str = "skeptic", content: str = "hello") -> dict:
    return {
        "model_id": model_id,
        "role": role,
        "auth": "api",
        "content_md": content,
        "error_msg": None,
        "elapsed_ms": 500,
    }


class TestInitDb:
    def test_creates_tables(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        import sqlite3
        conn = sqlite3.connect(db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"runs", "rounds", "model_outputs"} <= tables

    def test_idempotent(self, tmp_path):
        db = tmp_path / "test.db"
        init_db(db)
        init_db(db)  # should not raise


class TestSaveAndListRuns:
    def test_save_and_list(self, tmp_path):
        db = tmp_path / "test.db"
        save_run("Should I use Kafka?", "cfg", "decision", "/runs/1", [], db_path=db)
        runs = list_runs(db_path=db)
        assert len(runs) == 1
        assert runs[0]["question"] == "Should I use Kafka?"

    def test_returns_incrementing_ids(self, tmp_path):
        db = tmp_path / "test.db"
        id1 = save_run("Q1", "cfg", "dec", "/r/1", [], db_path=db)
        id2 = save_run("Q2", "cfg", "dec", "/r/2", [], db_path=db)
        assert id1 == 1
        assert id2 == 2

    def test_list_newest_first(self, tmp_path):
        db = tmp_path / "test.db"
        save_run("first", "cfg", "dec", "/r/1", [], db_path=db)
        save_run("second", "cfg", "dec", "/r/2", [], db_path=db)
        runs = list_runs(db_path=db)
        assert runs[0]["question"] == "second"

    def test_list_limit(self, tmp_path):
        db = tmp_path / "test.db"
        for i in range(5):
            save_run(f"Q{i}", "cfg", "dec", f"/r/{i}", [], db_path=db)
        runs = list_runs(limit=2, db_path=db)
        assert len(runs) == 2

    def test_list_empty(self, tmp_path):
        db = tmp_path / "test.db"
        assert list_runs(db_path=db) == []


class TestSearch:
    def test_search_filters(self, tmp_path):
        db = tmp_path / "test.db"
        save_run("Should I use Kafka?", "cfg", "dec", "/r/1", [], db_path=db)
        save_run("Redis vs Postgres?", "cfg", "dec", "/r/2", [], db_path=db)
        results = list_runs(search="Kafka", db_path=db)
        assert len(results) == 1
        assert "Kafka" in results[0]["question"]

    def test_search_no_match(self, tmp_path):
        db = tmp_path / "test.db"
        save_run("Should I use Kafka?", "cfg", "dec", "/r/1", [], db_path=db)
        assert list_runs(search="GraphQL", db_path=db) == []


class TestGetRun:
    def test_not_found_returns_none(self, tmp_path):
        db = tmp_path / "test.db"
        assert get_run(999, db_path=db) is None

    def test_full_structure(self, tmp_path):
        db = tmp_path / "test.db"
        rounds = [
            _round(0, "debate", [_output("ollama/mistral", "skeptic"), _output("ollama/mistral", "analyst")])
        ]
        run_id = save_run("Test question?", "cfg_toml", "decision text", "/runs/1", rounds, db_path=db)
        run = get_run(run_id, db_path=db)

        assert run is not None
        assert run["question"] == "Test question?"
        assert run["decision_md"] == "decision text"
        assert len(run["rounds"]) == 1
        assert run["rounds"][0]["name"] == "debate"
        assert len(run["rounds"][0]["outputs"]) == 2
        assert run["rounds"][0]["outputs"][0]["role"] == "skeptic"

    def test_multiple_rounds(self, tmp_path):
        db = tmp_path / "test.db"
        rounds = [
            _round(0, "debate", [_output()]),
            _round(1, "final", [_output(role="chairman")]),
        ]
        run_id = save_run("Q?", "cfg", "dec", "/r/1", rounds, db_path=db)
        run = get_run(run_id, db_path=db)
        assert len(run["rounds"]) == 2
        assert run["rounds"][1]["name"] == "final"
