"""Benchmark execution loop.

Drives each question through the existing debate engine unchanged:
    question → run_all_rounds → synthesize → parse_answer → compare

Writes incremental results to disk after each question so crashes don't
lose work on long runs.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from dissenter.config import DissentConfig
from dissenter.runner import run_all_rounds
from dissenter.synthesis import synthesize_benchmark

from .datasets import Question, load_dataset
from .parser import parse_answer
from .prompts import format_benchmark_question
from .results import BenchmarkResult, QuestionResult, write_results


ProgressCallback = Callable[[int, int, QuestionResult], None]


async def run_benchmark(
    dataset_path: Path,
    cfg: DissentConfig,
    output_path: Path,
    limit: int = 0,
    deep: bool = False,
    config_label: str = "",
    progress: Optional[ProgressCallback] = None,
) -> BenchmarkResult:
    """Run dissenter over a benchmark dataset and return aggregated results."""
    questions = load_dataset(dataset_path, limit=limit)

    result = BenchmarkResult(
        dataset=dataset_path.name,
        config=config_label or dataset_path.stem,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )

    for idx, q in enumerate(questions, 1):
        qr = await _run_one(q, cfg, deep)
        result.add_question(qr)
        if progress:
            try:
                progress(idx, len(questions), qr)
            except Exception:
                pass
        # Incremental save — crash-resilient for long runs
        write_results(result, output_path)

    return result


async def _run_one(
    q: Question,
    cfg: DissentConfig,
    deep: bool,
) -> QuestionResult:
    """Run a single question and return a QuestionResult."""
    t0 = time.time()
    question_text = format_benchmark_question(q)

    try:
        all_rounds = await run_all_rounds(cfg, question_text, deep=deep)
        final_text, _results = await synthesize_benchmark(question_text, all_rounds, cfg)
        predicted = parse_answer(final_text, q.type)
        is_correct = (
            predicted is not None and _compare(predicted, q.answer, q.type)
        )
        return QuestionResult(
            id=q.id,
            question=q.question,
            ground_truth=q.answer,
            predicted=predicted,
            correct=is_correct,
            raw_output=final_text,
            latency_s=time.time() - t0,
            metadata=q.metadata,
        )
    except Exception as exc:
        return QuestionResult(
            id=q.id,
            question=q.question,
            ground_truth=q.answer,
            predicted=None,
            correct=False,
            raw_output="",
            latency_s=time.time() - t0,
            metadata=q.metadata,
            error=str(exc),
        )


def _compare(predicted: str, truth: str, question_type: str) -> bool:
    if question_type == "mcq":
        return predicted.strip().upper() == truth.strip().upper()
    if question_type == "numeric":
        try:
            return abs(float(predicted) - float(truth)) < 1e-6
        except ValueError:
            return predicted.strip() == truth.strip()
    if question_type == "code":
        # Stage 1: just check that we extracted non-empty code.
        # Stage 2+ will execute against test cases.
        return bool(predicted and predicted.strip())
    return False
