#!/usr/bin/env python3
"""Fetch benchmark datasets from Hugging Face and convert to dissenter JSONL.

Usage:
    python scripts/fetch_datasets.py --dataset gpqa
    python scripts/fetch_datasets.py --dataset humaneval
    python scripts/fetch_datasets.py --dataset all

Datasets fetched here are gitignored. Only the normalized JSONL files land
under datasets/. The raw HF cache is managed by the `datasets` library.

Requires:
    uv pip install -e .[benchmark]
    (or: pip install datasets huggingface-hub)

GPQA-Diamond is a gated dataset — you must first accept the license at
https://huggingface.co/datasets/Idavidrein/gpqa and run `huggingface-cli login`.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS_DIR = REPO_ROOT / "datasets"


# ── GPQA-Diamond ────────────────────────────────────────────────────────
# Gated — https://huggingface.co/datasets/Idavidrein/gpqa
# 198 PhD-level science MCQ questions. Each question has 1 correct and
# 3 incorrect answers in separate fields. We shuffle them into A/B/C/D
# with a deterministic seed so ground truth is reproducible.
def fetch_gpqa_diamond(out_path: Path, seed: int = 42) -> None:
    from datasets import load_dataset

    print("Fetching Idavidrein/gpqa (gpqa_diamond split) ...", file=sys.stderr)
    ds = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")

    rng = random.Random(seed)
    records = []
    for i, row in enumerate(ds):
        correct = _clean(row["Correct Answer"])
        incorrects = [
            _clean(row["Incorrect Answer 1"]),
            _clean(row["Incorrect Answer 2"]),
            _clean(row["Incorrect Answer 3"]),
        ]
        letters = ["A", "B", "C", "D"]
        shuffled = [correct] + incorrects
        rng.shuffle(shuffled)
        correct_letter = letters[shuffled.index(correct)]
        choices = {letters[j]: shuffled[j] for j in range(4)}

        records.append({
            "id": f"gpqa_d_{i:03d}",
            "type": "mcq",
            "question": _clean(row["Question"]),
            "choices": choices,
            "answer": correct_letter,
            "metadata": {
                "domain": row.get("High-level domain", ""),
                "subdomain": row.get("Subdomain", ""),
                "source": "gpqa_diamond",
            },
        })

    _write_jsonl(out_path, records)
    print(f"  → {out_path} ({len(records)} questions)", file=sys.stderr)


# ── HumanEval ───────────────────────────────────────────────────────────
# Open — https://huggingface.co/datasets/openai_humaneval
# 164 Python code generation problems. For benchmark mode, "answer" is
# the canonical solution (used for diff-style comparison); the real
# evaluation will need to execute each candidate against the provided
# test cases (Stage 2+).
def fetch_humaneval(out_path: Path) -> None:
    from datasets import load_dataset

    print("Fetching openai_humaneval ...", file=sys.stderr)
    ds = load_dataset("openai_humaneval", split="test")

    records = []
    for row in ds:
        records.append({
            "id": row["task_id"].replace("/", "_"),
            "type": "code",
            "question": row["prompt"],
            "answer": row["canonical_solution"],
            "metadata": {
                "task_id": row["task_id"],
                "entry_point": row["entry_point"],
                "test": row["test"],
                "source": "humaneval",
            },
        })

    _write_jsonl(out_path, records)
    print(f"  → {out_path} ({len(records)} questions)", file=sys.stderr)


# ── Helpers ─────────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    """Normalize whitespace in question/answer text from HF datasets."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── Dispatch ────────────────────────────────────────────────────────────
FETCHERS = {
    "gpqa": ("gpqa_diamond.jsonl", fetch_gpqa_diamond),
    "humaneval": ("humaneval.jsonl", fetch_humaneval),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        choices=list(FETCHERS.keys()) + ["all"],
        required=True,
        help="Which dataset to fetch",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DATASETS_DIR,
        help="Where to write the JSONL files (default: ./datasets/)",
    )
    args = parser.parse_args()

    try:
        import datasets  # noqa: F401
    except ImportError:
        print(
            "error: `datasets` library not installed.\n"
            "run: uv pip install -e '.[benchmark]'",
            file=sys.stderr,
        )
        return 1

    targets = list(FETCHERS.keys()) if args.dataset == "all" else [args.dataset]
    for name in targets:
        filename, fetcher = FETCHERS[name]
        out_path = args.out_dir / filename
        try:
            fetcher(out_path)
        except Exception as e:
            print(f"error fetching {name}: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
