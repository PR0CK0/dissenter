from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dissenter.config import DissentConfig, ModelConfig, RoundConfig
from dissenter.runner import ModelResult, RoundResult
from dissenter.synthesis import _build_confidence_table, _format_all_rounds, synthesize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    model_id: str,
    role: str,
    content: str,
    confidence_score: int | None = None,
    confidence_change: str = "",
) -> ModelResult:
    return ModelResult(
        model_id=model_id,
        role=role,
        round_name="debate",
        content=content,
        confidence_score=confidence_score,
        confidence_change=confidence_change,
    )


def _make_round(name: str, index: int, results: list[ModelResult]) -> RoundResult:
    return RoundResult(round_name=name, round_index=index, results=results)


def _mock_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# _build_confidence_table
# ---------------------------------------------------------------------------


def test_build_confidence_table_no_data():
    """With no confidence scores, prose says none available and rows show _(none)_."""
    rr = _make_round(
        "debate",
        0,
        [_make_result("ollama/mistral", "skeptic", "some output", confidence_score=None)],
    )
    prose, md_rows = _build_confidence_table([rr])
    assert "No confidence scores available" in prose
    assert "_(none)_" in md_rows


def test_build_confidence_table_empty_rounds():
    """Empty round list returns the 'none available' result."""
    prose, md_rows = _build_confidence_table([])
    assert "No confidence scores available" in prose
    assert "_(none)_" in md_rows


def test_build_confidence_table_with_single_result():
    rr = _make_round(
        "debate",
        0,
        [
            _make_result(
                "ollama/mistral",
                "skeptic",
                "my output",
                confidence_score=7,
                confidence_change="Better benchmarks arrive.",
            )
        ],
    )
    prose, md_rows = _build_confidence_table([rr])

    assert "7/10" in prose
    assert "mistral" in prose
    assert "skeptic" in prose

    assert "| mistral | skeptic | 7/10 | Better benchmarks arrive. |" in md_rows


def test_build_confidence_table_multiple_results():
    rr = _make_round(
        "debate",
        0,
        [
            _make_result("ollama/mistral", "skeptic", "out1", confidence_score=6, confidence_change="If latency drops."),
            _make_result("ollama/llama3", "analyst", "out2", confidence_score=9, confidence_change="If vendor support ends."),
        ],
    )
    prose, md_rows = _build_confidence_table([rr])

    assert "mistral" in prose
    assert "llama3" in prose
    assert "6/10" in prose
    assert "9/10" in prose

    lines = md_rows.splitlines()
    assert len(lines) == 2
    assert any("mistral" in l and "6/10" in l for l in lines)
    assert any("llama3" in l and "9/10" in l for l in lines)


def test_build_confidence_table_skips_failed_results():
    """Failed results (no content) should not appear in the table."""
    failed = ModelResult(model_id="ollama/bad", role="skeptic", round_name="debate", error="API error")
    rr = _make_round("debate", 0, [failed])
    prose, md_rows = _build_confidence_table([rr])
    assert "No confidence scores available" in prose


def test_build_confidence_table_skips_none_scores_among_successful():
    """Successful results without a confidence score are silently skipped."""
    rr = _make_round(
        "debate",
        0,
        [
            _make_result("ollama/mistral", "skeptic", "output with no score", confidence_score=None),
            _make_result("ollama/llama3", "analyst", "output with score", confidence_score=8, confidence_change="New data."),
        ],
    )
    prose, md_rows = _build_confidence_table([rr])
    assert "8/10" in prose
    assert "mistral" not in prose  # no score, so not included
    assert "llama3" in prose


def test_build_confidence_table_prose_format():
    """Prose should start with 'Self-reported confidence —' when data is present."""
    rr = _make_round(
        "debate",
        0,
        [_make_result("ollama/mistral", "skeptic", "output", confidence_score=5, confidence_change="X.")],
    )
    prose, _ = _build_confidence_table([rr])
    assert prose.startswith("Self-reported confidence —")
    assert prose.endswith(".")


# ---------------------------------------------------------------------------
# _format_all_rounds
# ---------------------------------------------------------------------------


def test_format_all_rounds_includes_confidence_when_present():
    rr = _make_round(
        "debate",
        0,
        [_make_result("ollama/mistral", "skeptic", "my content", confidence_score=8)],
    )
    output = _format_all_rounds([rr])
    assert "confidence 8/10" in output
    assert "my content" in output


def test_format_all_rounds_omits_confidence_when_absent():
    rr = _make_round(
        "debate",
        0,
        [_make_result("ollama/mistral", "skeptic", "my content", confidence_score=None)],
    )
    output = _format_all_rounds([rr])
    assert "confidence" not in output
    assert "my content" in output


def test_format_all_rounds_round_header():
    rr = _make_round("debate", 0, [_make_result("ollama/mistral", "skeptic", "content")])
    output = _format_all_rounds([rr])
    assert "### Round 1: debate" in output


def test_format_all_rounds_multiple_rounds():
    r1 = _make_round(
        "debate",
        0,
        [_make_result("ollama/mistral", "skeptic", "round one content", confidence_score=7)],
    )
    r2 = _make_round(
        "critique",
        1,
        [_make_result("ollama/llama3", "analyst", "round two content", confidence_score=None)],
    )
    output = _format_all_rounds([r1, r2])

    assert "### Round 1: debate" in output
    assert "### Round 2: critique" in output
    assert "confidence 7/10" in output
    assert "round one content" in output
    assert "round two content" in output


def test_format_all_rounds_excludes_failed_results():
    """Failed ModelResult entries (no content / error set) must not appear."""
    failed = ModelResult(model_id="ollama/bad", role="skeptic", round_name="debate", error="oops")
    good = _make_result("ollama/good", "analyst", "good content")
    rr = _make_round("debate", 0, [failed, good])
    output = _format_all_rounds([rr])
    assert "good content" in output
    assert "oops" not in output


# ---------------------------------------------------------------------------
# synthesize() — confidence_table and confidence_rows wired into the prompt
# ---------------------------------------------------------------------------


@pytest.fixture
def single_arbiter_cfg() -> DissentConfig:
    return DissentConfig(
        rounds=[
            RoundConfig(
                name="debate",
                models=[ModelConfig(id="ollama/mistral", role="skeptic", timeout=10)],
            ),
            RoundConfig(
                name="final",
                models=[ModelConfig(id="ollama/mistral", role="chairman", timeout=10)],
            ),
        ]
    )


@pytest.mark.asyncio
async def test_synthesize_passes_confidence_into_prompt(single_arbiter_cfg):
    """synthesize() must inject confidence_table prose and rows into the prompt."""
    debate_result = _make_result(
        "ollama/mistral",
        "skeptic",
        "The answer is X.",
        confidence_score=8,
        confidence_change="If new data arrives.",
    )
    debate_rr = _make_round("debate", 0, [debate_result])
    # Provide two rounds: debate + a dummy final round result (synthesis re-runs the final model)
    final_rr = _make_round(
        "final",
        1,
        [_make_result("ollama/mistral", "chairman", "Final synthesis.")],
    )

    captured_prompts: list[str] = []

    async def fake_completion(**kwargs):
        captured_prompts.append(kwargs["messages"][0]["content"])
        return _mock_response("ADR content here.")

    with patch("dissenter.synthesis.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = fake_completion
        await synthesize("Which database?", [debate_rr, final_rr], single_arbiter_cfg)

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]

    # confidence prose must appear
    assert "Self-reported confidence" in prompt
    assert "8/10" in prompt

    # confidence rows must appear as a markdown table row
    assert "| mistral | skeptic | 8/10 |" in prompt


@pytest.mark.asyncio
async def test_synthesize_no_confidence_data_fallback(single_arbiter_cfg):
    """When no models provide confidence data, the fallback prose appears in the prompt."""
    debate_result = _make_result(
        "ollama/mistral",
        "skeptic",
        "The answer is X.",
        confidence_score=None,
    )
    debate_rr = _make_round("debate", 0, [debate_result])
    final_rr = _make_round(
        "final",
        1,
        [_make_result("ollama/mistral", "chairman", "Final synthesis.")],
    )

    captured_prompts: list[str] = []

    async def fake_completion(**kwargs):
        captured_prompts.append(kwargs["messages"][0]["content"])
        return _mock_response("ADR content here.")

    with patch("dissenter.synthesis.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = fake_completion
        await synthesize("Which database?", [debate_rr, final_rr], single_arbiter_cfg)

    prompt = captured_prompts[0]
    assert "No confidence scores available" in prompt
    assert "_(none)_" in prompt
