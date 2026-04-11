from __future__ import annotations

import asyncio
from datetime import date

import litellm

from .config import DissentConfig, ModelConfig, RoundConfig
from .roles import get_prompt, load_roles
from .runner import ModelResult, RoundResult, _query_model_cli

_BENCHMARK_SYNTHESIS_PROMPT = """\
You are an expert evaluator picking the correct answer to a benchmark question
based on a multi-model debate.

Question:
{question}

The debate produced these arguments across {n_rounds} round(s):

{all_round_outputs}

Your job: weigh the debate, determine the single best answer, and respond
with a brief rationale (2-4 sentences) followed by EXACTLY one final line
in this format (no extra text after it):

FINAL ANSWER: <answer>

For multiple-choice questions, <answer> is a single uppercase letter (A, B, C, ...).
For numeric questions, <answer> is the number with no units.
For code questions, provide the complete solution as a single Python code block
  before the FINAL ANSWER line; the code block itself is the submission.

Do not deviate from this format. Be decisive — pick one answer.
"""


_SYNTHESIS_PROMPT = """\
You are a principal architect writing a formal Architectural Decision Record (ADR).

Multiple AI models debated across {n_rounds} round(s). Here are all their outputs:

{all_round_outputs}

---

Confidence signals from the debate models:

{confidence_table}

---

Synthesize into an ADR using this EXACT structure (do not deviate):

# ADR: [derive a concise title]

**Date:** {date}
**Status:** Proposed
**Debate rounds:** {n_rounds} | **Models consulted:** {n_models_total}

## Context
[2-3 sentences on the problem and why this decision matters]

## Consensus
[What most/all models agreed on — high-confidence signals]

## Disagreements
[Where models diverged. For each: what was the disagreement, why it matters, what context would resolve it]

## Confidence Signals

| Model | Role | Score | Would change if |
|-------|------|-------|-----------------|
{confidence_rows}

## Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|

## Decision
**[The recommendation in one clear sentence.]**

[2-3 paragraphs of rationale: draw on consensus, resolve disagreements, be explicit about what assumptions this decision rests on. Weight high-confidence model outputs more heavily; flag where low confidence signals genuine uncertainty.]

## Consequences

### Positive
- [bullet]

### Risks
- [bullet]

### Mitigations
- [bullet]

## Open Questions
[Points that require your specific context — team size, existing stack, constraints — that no model could know]

---
*Synthesized by dissenter from {n_models_total} model responses across {n_rounds} round(s)*

Be ruthlessly clear, technically precise, and opinionated. No filler.
"""

_DUAL_ARBITER_PROMPT = """\
You are a senior architect. Your role: {role_instruction}

All preceding debate is below. Read it carefully, then write your recommendation.

{all_round_outputs}

---

Question: {question}

Write a terse, opinionated recommendation. Your output will be shown side-by-side with another architect's view.

## Your Recommendation
[1 clear sentence]

## Why
[2-3 bullet points max]

## Risks
[1-2 bullet points max]

## What would change your answer
[1 sentence]
"""

_COMBINE_PROMPT = """\
Two senior architects reviewed the same debate and provided their recommendations.
Format them side by side for the human to compare and decide.

CONSERVATIVE view (pragmatic executor — safest proven path):
{conservative_output}

LIBERAL view (ambitious visionary — boldest high-upside path):
{liberal_output}

Format as this EXACT structure:

# Dual Recommendation: {title}

**Date:** {date}
**Question:** {question}

---

## Conservative View — Ship It
{conservative_output}

---

## Liberal View — Go Bold
{liberal_output}

---

## Key Divergence
[2-3 sentences: what is the core difference between these two views, and what specific context (team size, risk tolerance, timeline, existing stack) would make one more appropriate than the other]
"""


def _format_all_rounds(all_rounds: list[RoundResult]) -> str:
    parts = []
    for rr in all_rounds:
        header = f"### Round {rr.round_index + 1}: {rr.round_name}"
        parts.append(header)
        for r in rr.successful:
            conf = f" · confidence {r.confidence_score}/10" if r.confidence_score is not None else ""
            parts.append(f"\n**{r.short_id}** (role: *{r.role}*{conf})\n\n{r.content}")
            parts.append("\n---")
    return "\n".join(parts)


def _build_confidence_table(all_rounds: list[RoundResult]) -> tuple[str, str]:
    """Return (prose_summary, markdown_rows) for confidence signals across all debate rounds."""
    rows: list[tuple[str, str, str, str]] = []
    for rr in all_rounds:
        for r in rr.successful:
            if r.confidence_score is not None:
                rows.append((r.short_id, r.role, f"{r.confidence_score}/10", r.confidence_change))

    if not rows:
        prose = "No confidence scores available."
        md_rows = "| _(none)_ | | | |"
    else:
        prose_parts = [f"{row[0]} ({row[1]}): {row[2]}" for row in rows]
        prose = "Self-reported confidence — " + "; ".join(prose_parts) + "."
        md_rows = "\n".join(f"| {m} | {rl} | {s} | {w} |" for m, rl, s, w in rows)

    return prose, md_rows


_NAMING_PROMPT = """\
Given this question and decision, respond with exactly ONE lowercase word \
(no punctuation, no spaces, no explanation) that best describes the core topic. \
Examples: kafka, kubernetes, caching, postgres, auth, microservices, redis.

Question: {question}

Decision summary: {summary}

One word:"""


async def name_decision(question: str, decision_text: str, arbiter: ModelConfig) -> str:
    """Ask the arbiter for a single-word name for this decision."""
    import re
    summary = decision_text[:500]  # first 500 chars is enough context
    prompt = _NAMING_PROMPT.format(question=question, summary=summary)
    try:
        raw = await _call_model(arbiter, prompt)
        # Extract first word, lowercase, strip punctuation
        word = re.sub(r"[^a-z0-9]", "", raw.strip().split()[0].lower())
        return word[:20] if word else "decision"
    except Exception:
        return "decision"


async def _call_model(cfg: ModelConfig, prompt: str) -> str:
    if cfg.auth == "cli":
        return await asyncio.wait_for(
            _query_model_cli(cfg, prompt),
            timeout=float(cfg.timeout),
        )
    kwargs: dict = {
        "model": cfg.id,
        "messages": [{"role": "user", "content": prompt}],
        **(cfg.extra or {}),
    }
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    response = await asyncio.wait_for(
        litellm.acompletion(**kwargs),
        timeout=float(cfg.timeout),
    )
    return response.choices[0].message.content or ""


async def synthesize(
    question: str,
    all_rounds: list[RoundResult],
    cfg: DissentConfig,
) -> tuple[str, list[ModelResult]]:
    """
    Returns (final_text, final_model_results).
    final_model_results contains the synthesis model outputs for saving to debug dir.
    """
    role_prompts = load_roles()
    final_round = cfg.rounds[-1]
    active = final_round.active_models
    # Always exclude the final round's regular run — re-run below with synthesis prompt.
    # Correct with and without --deep (critique round, if injected, is all_rounds[-2]).
    debate_outputs = _format_all_rounds(all_rounds[:-1])
    n_models_total = sum(len(rr.successful) for rr in all_rounds)

    confidence_prose, confidence_rows = _build_confidence_table(all_rounds[:-1])

    if len(active) == 1:
        # Single chairman/arbiter
        arbiter = active[0]
        prompt = _SYNTHESIS_PROMPT.format(
            question=question,
            all_round_outputs=debate_outputs,
            confidence_table=confidence_prose,
            confidence_rows=confidence_rows,
            date=date.today().isoformat(),
            n_rounds=len(all_rounds),
            n_models_total=n_models_total,
        )
        content = await _call_model(arbiter, prompt)
        result = ModelResult(
            model_id=arbiter.id, role=arbiter.role, round_name=final_round.name or "final",
            content=content, elapsed=0.0,
        )
        return content, [result]

    else:
        # Dual arbiter: conservative + liberal
        debate_context = debate_outputs

        async def call_arbiter(m) -> ModelResult:
            role_instruction = get_prompt(m.role, role_prompts)
            prompt = _DUAL_ARBITER_PROMPT.format(
                role_instruction=role_instruction,
                all_round_outputs=debate_context,
                question=question,
            )
            content = await _call_model(m, prompt)
            return ModelResult(
                model_id=m.id, role=m.role, round_name=final_round.name or "final",
                content=content, elapsed=0.0,
            )

        results = await asyncio.gather(*[call_arbiter(m) for m in active])

        # Identify conservative vs liberal
        conservative_result = next((r for r in results if r.role == "conservative"), results[0])
        liberal_result = next((r for r in results if r.role == "liberal"), results[1])

        # Combine side-by-side
        title = question[:60] + ("..." if len(question) > 60 else "")
        combine_prompt = _COMBINE_PROMPT.format(
            conservative_output=conservative_result.content,
            liberal_output=liberal_result.content,
            title=title,
            date=date.today().isoformat(),
            question=question,
        )
        combine_cfg = ModelConfig(
            id=final_round.combine_model,
            role="combiner",
            timeout=final_round.combine_timeout,
        )
        combined = await _call_model(combine_cfg, combine_prompt)
        return combined, list(results)


async def synthesize_benchmark(
    question: str,
    all_rounds: list[RoundResult],
    cfg: DissentConfig,
) -> tuple[str, list[ModelResult]]:
    """Synthesis path for benchmark mode.

    Uses a lean answer-focused prompt instead of the ADR template. The
    final-round chairman produces a brief rationale ending with a
    FINAL ANSWER: line that the benchmark parser can extract.

    Dual-arbiter configs collapse to the first model for benchmark runs —
    we need a single decisive answer, not side-by-side recommendations.
    """
    final_round = cfg.rounds[-1]
    active = final_round.active_models
    if not active:
        raise ValueError("Final round has no active models")

    debate_outputs = _format_all_rounds(all_rounds[:-1])

    arbiter = active[0]
    prompt = _BENCHMARK_SYNTHESIS_PROMPT.format(
        question=question,
        all_round_outputs=debate_outputs,
        n_rounds=len(all_rounds),
    )
    content = await _call_model(arbiter, prompt)
    result = ModelResult(
        model_id=arbiter.id,
        role=arbiter.role,
        round_name=final_round.name or "final",
        content=content,
        elapsed=0.0,
    )
    return content, [result]
