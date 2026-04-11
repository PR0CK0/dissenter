"""Wrapper for terry-li-hm/consilium.

Source: https://github.com/terry-li-hm/consilium

consilium is a Rust binary (cargo install consilium) that runs a debate
between 5 frontier LLMs with Claude Opus as judge. It has modes like
`discuss`, `socratic`, and `debate`.

TODO(verify): confirm the exact invocation syntax. The GitHub README is
the canonical source. We assume a shell-callable `consilium` entry
point that accepts the question as the final positional argument.
"""
from __future__ import annotations

import asyncio
import shutil
import time

from .base import Competitor, CompetitorError, CompetitorResult


class Consilium(Competitor):
    name = "consilium"

    def __init__(
        self,
        cli_name: str = "consilium",
        mode: str = "debate",
        extra_args: list[str] | None = None,
    ) -> None:
        self._cli = cli_name
        self._mode = mode
        self._extra_args = extra_args or []

    def validate(self) -> None:
        if shutil.which(self._cli) is None:
            raise CompetitorError(
                f"{self.name}: `{self._cli}` not found on PATH. "
                "Install: cargo install consilium (requires Rust toolchain). "
                "See https://github.com/terry-li-hm/consilium"
            )

    def _build_args(self, question: str) -> list[str]:
        args = [self._cli, self._mode]
        args.extend(self._extra_args)
        args.append(question)
        return args

    async def run(self, question: str, timeout: int = 900) -> CompetitorResult:
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
