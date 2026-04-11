"""Wrapper for karpathy/llm-council.

Source: https://github.com/karpathy/llm-council

llm-council is a Python package (self-described as "99% vibe coded") that
runs a question through multiple LLMs, has each anonymously review the
others, and a chairman synthesizes. The exact CLI invocation is not
standardized — this wrapper assumes a shell-callable `llmcouncil` entry
point. Verify by running `.validate()` before a benchmark run.

TODO(verify): confirm the CLI name, flags, and stdout format once the
tool is installed. If it's Python-only (no CLI), switch to importing
and calling the library directly.
"""
from __future__ import annotations

import asyncio
import shutil
import time

from .base import Competitor, CompetitorError, CompetitorResult


class LLMCouncil(Competitor):
    name = "llm-council"

    def __init__(self, cli_name: str = "llmcouncil") -> None:
        self._cli = cli_name

    def validate(self) -> None:
        if shutil.which(self._cli) is None:
            raise CompetitorError(
                f"{self.name}: `{self._cli}` not found on PATH. "
                "Install: pip install llm-council (or clone and install from source). "
                "If the CLI name differs, pass cli_name=... to the constructor."
            )

    async def run(self, question: str, timeout: int = 600) -> CompetitorResult:
        t0 = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli,
                question,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            return CompetitorResult(
                raw_output="",
                latency_s=time.time() - t0,
                error=f"timeout after {timeout}s",
            )
        except FileNotFoundError:
            return CompetitorResult(
                raw_output="",
                latency_s=time.time() - t0,
                error=f"{self._cli} not found",
            )

        if proc.returncode != 0:
            return CompetitorResult(
                raw_output=stdout.decode("utf-8", errors="replace"),
                latency_s=time.time() - t0,
                error=f"exit {proc.returncode}: {stderr.decode('utf-8', errors='replace')[:500]}",
            )

        return CompetitorResult(
            raw_output=stdout.decode("utf-8", errors="replace"),
            latency_s=time.time() - t0,
        )
