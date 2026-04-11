"""Benchmark result tracking and JSON output.

BenchmarkResult is built incrementally as the runner processes questions.
After every question we write the full JSON to disk so a crash halfway
through a long run doesn't lose the partial results.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class QuestionResult:
    id: str
    question: str
    ground_truth: str
    predicted: str | None
    correct: bool
    raw_output: str
    latency_s: float
    tokens: int = 0
    metadata: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class BenchmarkResult:
    dataset: str
    config: str
    timestamp: str
    total: int = 0
    correct: int = 0
    errors: int = 0
    total_latency_s: float = 0.0
    total_tokens: int = 0
    questions: list[QuestionResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return (self.correct / self.total) if self.total else 0.0

    def add_question(self, qr: QuestionResult) -> None:
        self.questions.append(qr)
        self.total += 1
        if qr.correct:
            self.correct += 1
        if qr.error:
            self.errors += 1
        self.total_latency_s += qr.latency_s
        self.total_tokens += qr.tokens

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "config": self.config,
            "timestamp": self.timestamp,
            "total": self.total,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "errors": self.errors,
            "total_latency_s": self.total_latency_s,
            "total_tokens": self.total_tokens,
            "questions": [asdict(q) for q in self.questions],
        }


def write_results(result: BenchmarkResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2),
        encoding="utf-8",
    )
