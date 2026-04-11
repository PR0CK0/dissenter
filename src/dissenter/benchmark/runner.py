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

from .baselines import run_majority, run_single
from .code_eval import eval_humaneval
from .competitors.base import Competitor
from .datasets import Question, load_dataset
from .parser import parse_answer
from .prompts import format_benchmark_question
from .results import BenchmarkResult, QuestionResult, write_results


ProgressCallback = Callable[[int, int, QuestionResult], None]


# Supported benchmark modes:
#   "dissenter" — full multi-round debate (the whole point)
#   "single"    — ask one model once, no debate
#   "majority"  — ask one model N times, majority-vote the answer
Mode = str  # for typing clarity


async def run_benchmark(
    dataset_path: Path,
    cfg: DissentConfig,
    output_path: Path,
    limit: int = 0,
    deep: bool = False,
    mode: Mode = "dissenter",
    majority_n: int = 3,
    competitor: Optional[Competitor] = None,
    config_label: str = "",
    progress: Optional[ProgressCallback] = None,
) -> BenchmarkResult:
    """Run a benchmark and return aggregated results.

    mode:
      "dissenter"  — full debate pipeline (default)
      "single"     — one model, no debate
      "majority"   — one model × majority_n, majority vote
      "competitor" — delegate to a Competitor instance (llm-council, etc.)
    """
    questions = load_dataset(dataset_path, limit=limit)

    if mode == "competitor":
        if competitor is None:
            raise ValueError("mode=competitor requires a Competitor instance")
        competitor.validate()
        label = f"{competitor.name}"
    else:
        label = config_label or dataset_path.stem

    result = BenchmarkResult(
        dataset=dataset_path.name,
        config=f"{label} [{mode}]",
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )

    for idx, q in enumerate(questions, 1):
        qr = await _run_one(q, cfg, deep, mode, majority_n, competitor)
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
    mode: Mode,
    majority_n: int,
    competitor: Optional[Competitor] = None,
) -> QuestionResult:
    """Run a single question through the selected mode."""
    t0 = time.time()
    question_text = format_benchmark_question(q)

    try:
        if mode == "single":
            final_text = await run_single(q, cfg)
        elif mode == "majority":
            final_text = await run_majority(q, cfg, n=majority_n)
        elif mode == "competitor":
            cr = await competitor.run(question_text)  # type: ignore[union-attr]
            if cr.error:
                raise RuntimeError(cr.error)
            final_text = cr.raw_output
        else:  # "dissenter"
            all_rounds = await run_all_rounds(cfg, question_text, deep=deep)
            final_text, _results = await synthesize_benchmark(
                question_text, all_rounds, cfg
            )

        predicted = parse_answer(final_text, q.type)
        is_correct = (
            predicted is not None and _compare(predicted, q.answer, q.type, q.metadata)
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


def _compare(predicted: str, truth: str, question_type: str, metadata: dict) -> bool:
    if question_type == "mcq":
        return predicted.strip().upper() == truth.strip().upper()
    if question_type == "numeric":
        try:
            return abs(float(predicted) - float(truth)) < 1e-6
        except ValueError:
            return predicted.strip() == truth.strip()
    if question_type == "code":
        # If we have HumanEval metadata, execute against its test cases.
        test_code = metadata.get("test")
        entry_point = metadata.get("entry_point")
        if test_code and entry_point:
            result = eval_humaneval(predicted, test_code, entry_point)
            return result.passed
        # Otherwise just check that code was extracted (weak fallback)
        return bool(predicted and predicted.strip())
    return False
