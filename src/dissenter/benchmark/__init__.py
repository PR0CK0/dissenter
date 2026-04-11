"""Benchmark mode — evaluate dissenter on standardized datasets.

Reuses the existing debate engine (run_all_rounds + synthesize) and adds:
  - Dataset loading from normalized JSONL
  - Answer parsing (MCQ letter, numeric, code block)
  - Results tracking with per-question detail
  - An async runner that writes incremental JSON output

Public API:
  - Question, load_dataset
  - parse_answer
  - format_benchmark_question
  - BenchmarkResult, QuestionResult, write_results
  - run_benchmark
"""
from .datasets import Question, load_dataset
from .parser import parse_answer
from .prompts import format_benchmark_question
from .results import BenchmarkResult, QuestionResult, write_results
from .runner import run_benchmark

__all__ = [
    "Question",
    "load_dataset",
    "parse_answer",
    "format_benchmark_question",
    "BenchmarkResult",
    "QuestionResult",
    "write_results",
    "run_benchmark",
]
