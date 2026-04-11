"""Common interface for competitor LLM ensemble tools.

A Competitor takes a formatted question and returns the raw text output
of running that question through the tool. The benchmark runner will
then use dissenter.benchmark.parser to extract the final answer.

We keep this simple — just strings in, strings out. Tool-specific model
selection and config happen in each subclass's constructor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class CompetitorError(Exception):
    """Raised when a competitor tool fails to run or is misconfigured."""


@dataclass
class CompetitorResult:
    raw_output: str
    latency_s: float
    error: str | None = None


class Competitor(ABC):
    """Abstract base — subclass one per competing tool."""

    #: Human-readable name for result labels
    name: str = "unnamed"

    @abstractmethod
    def validate(self) -> None:
        """Raise CompetitorError if the tool is not installed or is misconfigured.

        Called once before a benchmark run starts so we fail fast.
        """

    @abstractmethod
    async def run(self, question: str, timeout: int = 600) -> CompetitorResult:
        """Run one question through the tool and return the raw output."""
