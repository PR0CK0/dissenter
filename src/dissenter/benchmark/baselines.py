"""Baseline runners — single model and majority vote.

These bypass the multi-round debate entirely so you can compare
dissenter against trivial baselines on the same dataset and model.

  - single: ask the first model in the config once, return its answer
  - majority: ask the first model N times, majority-vote the answers

Both use the same benchmark prompt + parser as the debate path so
results are directly comparable.
"""
from __future__ import annotations

import asyncio
from collections import Counter

from dissenter.config import DissentConfig, ModelConfig
from dissenter.synthesis import _call_model

from .datasets import Question
from .parser import parse_answer
from .prompts import format_benchmark_question


def _first_debate_model(cfg: DissentConfig) -> ModelConfig:
    """Pick the first active model from the first round.

    Baselines ignore roles and use a single model — we just need *a*
    model to ask. The first one in the first round is the obvious pick.
    """
    for r in cfg.rounds:
        for m in r.active_models:
            return m
    raise ValueError("config has no models")


async def run_single(q: Question, cfg: DissentConfig) -> str:
    """Ask one model once and return its raw output."""
    model = _first_debate_model(cfg)
    prompt = format_benchmark_question(q)
    return await _call_model(model, prompt)


async def run_majority(q: Question, cfg: DissentConfig, n: int = 3) -> str:
    """Ask one model N times and return the majority-vote answer.

    Returns a synthetic output that the existing parser can read:
    just the winning answer on a FINAL ANSWER line.
    """
    model = _first_debate_model(cfg)
    prompt = format_benchmark_question(q)

    outputs = await asyncio.gather(*[_call_model(model, prompt) for _ in range(n)])
    votes: list[str] = []
    for out in outputs:
        parsed = parse_answer(out, q.type)
        if parsed is not None:
            votes.append(parsed)

    if not votes:
        return "\n\nFINAL ANSWER: NONE\n"

    counter = Counter(votes)
    winner, _ = counter.most_common(1)[0]
    # Return a synthetic response that the parser will read as the winner,
    # plus the individual votes appended for debug visibility.
    debug = "\n".join(f"  vote {i + 1}: {v}" for i, v in enumerate(votes))
    return (
        f"Majority vote across {n} runs:\n{debug}\n\nFINAL ANSWER: {winner}\n"
    )
