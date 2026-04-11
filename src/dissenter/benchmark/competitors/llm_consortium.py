"""Wrapper for irthomasthomas/llm-consortium.

Source: https://github.com/irthomasthomas/llm-consortium

llm-consortium is a plugin for Simon Willison's `llm` tool, invoked as:
    llm consortium "<question>" [options]

The plugin configures the model pool via its own command-line options.
We pass the question and capture stdout; answer parsing happens
downstream in dissenter.benchmark.parser.

TODO(verify): confirm the exact flags for setting the model pool and
arbiter to match our pinned benchmark config (for fairness). Different
model sets break the comparison.
"""
from __future__ import annotations

import asyncio
import shutil
import time

from .base import Competitor, CompetitorError, CompetitorResult


class LLMConsortium(Competitor):
    name = "llm-consortium"

    def __init__(
        self,
        llm_cli: str = "llm",
        models: list[str] | None = None,
        arbiter: str | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        self._llm_cli = llm_cli
        self._models = models or []
        self._arbiter = arbiter
        self._extra_args = extra_args or []

    def validate(self) -> None:
        if shutil.which(self._llm_cli) is None:
            raise CompetitorError(
                f"{self.name}: `{self._llm_cli}` not found on PATH. "
                "Install: pip install llm && llm install llm-consortium"
            )
        # TODO(verify): run `llm plugins` and check that llm-consortium is listed

    def _build_args(self, question: str) -> list[str]:
        args = [self._llm_cli, "consortium"]
        for m in self._models:
            args.extend(["--models", m])
        if self._arbiter:
            args.extend(["--arbiter", self._arbiter])
        args.extend(self._extra_args)
        args.append(question)
        return args

    async def run(self, question: str, timeout: int = 600) -> CompetitorResult:
        t0 = time.time()
        args = self._build_args(question)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
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
