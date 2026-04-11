"""Dataset loading — normalized JSONL format.

Every benchmark (GPQA, HumanEval, MMLU-PRO, MATH, test-mini) lands in
the same shape so the runner doesn't need to care about the source.

JSONL schema — one question per line:
    {
      "id": "q001",
      "type": "mcq" | "numeric" | "code",
      "question": "<question text>",
      "answer": "<ground truth>",
      "choices": {"A": "...", "B": "..."},  // mcq only
      "metadata": {"domain": "physics", ...}  // optional
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


QuestionType = Literal["mcq", "numeric", "code"]


@dataclass
class Question:
    id: str
    type: QuestionType
    question: str
    answer: str
    choices: dict[str, str] | None = None
    metadata: dict = field(default_factory=dict)


def load_dataset(path: Path, limit: int = 0) -> list[Question]:
    """Read a JSONL dataset and return a list of Question objects.

    If limit > 0, only the first `limit` questions are returned.
    """
    questions: list[Question] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {e}")

            required = ("id", "type", "question", "answer")
            missing = [k for k in required if k not in data]
            if missing:
                raise ValueError(
                    f"{path}:{line_no}: missing required keys: {missing}"
                )

            questions.append(
                Question(
                    id=str(data["id"]),
                    type=data["type"],
                    question=data["question"],
                    answer=str(data["answer"]),
                    choices=data.get("choices"),
                    metadata=data.get("metadata", {}) or {},
                )
            )

            if limit and len(questions) >= limit:
                break

    return questions
