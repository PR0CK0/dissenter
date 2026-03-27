from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dissenter.config import DissentConfig, ModelConfig, RoundConfig
from dissenter.runner import ModelResult, RoundResult, run_round, _build_prior_context, _parse_confidence


def _mock_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def role_prompts():
    return {"skeptic": "Be skeptical.", "analyst": "Be analytical.", "chairman": "Make the call."}


@pytest.mark.asyncio
async def test_run_round_all_succeed(role_prompts):
    models = [
        ModelConfig(id="ollama/mistral", role="skeptic", timeout=10),
        ModelConfig(id="ollama/mistral", role="analyst", timeout=10),
    ]
    round_cfg = RoundConfig(name="debate", models=models)

    with patch("dissenter.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = _mock_response("some response text")
        result = await run_round(round_cfg, 0, "Test question?", [], role_prompts)

    assert len(result.results) == 2
    assert all(r.success for r in result.results)
    assert result.round_name == "debate"


@pytest.mark.asyncio
async def test_run_round_error_captured(role_prompts):
    models = [ModelConfig(id="bad/model", role="skeptic", timeout=10)]
    round_cfg = RoundConfig(name="test", models=models)

    with patch("dissenter.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("API error: 401")
        result = await run_round(round_cfg, 0, "Test?", [], role_prompts)

    assert len(result.results) == 1
    assert not result.results[0].success
    assert "API error" in result.results[0].error


@pytest.mark.asyncio
async def test_run_round_includes_prior_context(role_prompts):
    prior = RoundResult(
        round_name="debate",
        round_index=0,
        results=[
            ModelResult(model_id="ollama/mistral", role="skeptic", round_name="debate", content="prior output")
        ],
    )
    models = [ModelConfig(id="ollama/mistral", role="chairman", timeout=10)]
    round_cfg = RoundConfig(name="final", models=models)

    captured_prompts = []

    async def fake_completion(**kwargs):
        captured_prompts.append(kwargs["messages"][0]["content"])
        return _mock_response("final answer")

    with patch("dissenter.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = fake_completion
        await run_round(round_cfg, 1, "Test?", [prior], role_prompts)

    assert len(captured_prompts) == 1
    assert "prior output" in captured_prompts[0]
    assert "debate" in captured_prompts[0]


def test_build_prior_context_empty():
    result = _build_prior_context([])
    assert result == ""


def test_build_prior_context_with_data():
    rr = RoundResult(
        round_name="debate",
        round_index=0,
        results=[
            ModelResult(model_id="a/b", role="skeptic", round_name="debate", content="hello world")
        ],
    )
    ctx = _build_prior_context([rr])
    assert "hello world" in ctx
    assert "debate" in ctx


# ---------------------------------------------------------------------------
# _parse_confidence tests
# ---------------------------------------------------------------------------

_VALID_CONFIDENCE_BLOCK = (
    "Some model output here.\n\n"
    "---CONFIDENCE---\n"
    "Score: 7/10\n"
    "Would change if: New benchmark data shows latency exceeds 100 ms."
)


def test_parse_confidence_valid_block():
    clean, score, change = _parse_confidence(_VALID_CONFIDENCE_BLOCK)
    assert score == 7
    assert change == "New benchmark data shows latency exceeds 100 ms."
    assert "---CONFIDENCE---" not in clean
    assert "Score:" not in clean
    assert "Some model output here." in clean


def test_parse_confidence_strips_block_from_content():
    clean, _, _ = _parse_confidence(_VALID_CONFIDENCE_BLOCK)
    # The confidence block (and trailing whitespace) must be gone
    assert clean.strip() == "Some model output here."


def test_parse_confidence_score_clamped_high():
    content = "Output.\n---CONFIDENCE---\nScore: 15/10\nWould change if: Anything."
    _, score, _ = _parse_confidence(content)
    assert score == 10


def test_parse_confidence_score_clamped_low():
    content = "Output.\n---CONFIDENCE---\nScore: 0/10\nWould change if: Nothing."
    _, score, _ = _parse_confidence(content)
    assert score == 1


def test_parse_confidence_no_block_returns_none():
    content = "This response has no confidence block."
    clean, score, change = _parse_confidence(content)
    assert clean == content
    assert score is None
    assert change == ""


def test_parse_confidence_empty_string():
    clean, score, change = _parse_confidence("")
    assert clean == ""
    assert score is None
    assert change == ""


def test_parse_confidence_malformed_missing_would_change():
    # Only the header and score line — no "Would change if" line
    content = "Output.\n---CONFIDENCE---\nScore: 5/10\n"
    clean, score, change = _parse_confidence(content)
    # The regex won't match, so we get content back unchanged and no score
    assert score is None
    assert clean == content


def test_parse_confidence_malformed_score_non_numeric():
    content = "Output.\n---CONFIDENCE---\nScore: high/10\nWould change if: Something."
    clean, score, change = _parse_confidence(content)
    assert score is None
    assert clean == content


def test_parse_confidence_case_insensitive_header():
    content = (
        "Output.\n"
        "---confidence---\n"
        "Score: 6/10\n"
        "Would change if: Context changes."
    )
    _, score, change = _parse_confidence(content)
    assert score == 6
    assert change == "Context changes."


# ---------------------------------------------------------------------------
# ModelResult new fields
# ---------------------------------------------------------------------------


def test_model_result_default_confidence_fields():
    r = ModelResult(model_id="a/b", role="skeptic", round_name="debate", content="hello")
    assert r.confidence_score is None
    assert r.confidence_change == ""


def test_model_result_confidence_fields_set():
    r = ModelResult(
        model_id="a/b",
        role="skeptic",
        round_name="debate",
        content="hello",
        confidence_score=8,
        confidence_change="If benchmark data arrives.",
    )
    assert r.confidence_score == 8
    assert r.confidence_change == "If benchmark data arrives."


# ---------------------------------------------------------------------------
# run_round with confidence block in response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_round_confidence_block_populated(role_prompts):
    """A response containing a valid confidence block must populate the fields."""
    response_with_confidence = (
        "My recommendation is X.\n\n"
        "---CONFIDENCE---\n"
        "Score: 9/10\n"
        "Would change if: We discover the vendor is dropping support."
    )
    models = [ModelConfig(id="ollama/mistral", role="skeptic", timeout=10)]
    round_cfg = RoundConfig(name="debate", models=models)

    with patch("dissenter.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = _mock_response(response_with_confidence)
        result = await run_round(round_cfg, 0, "Which DB?", [], role_prompts)

    mr = result.results[0]
    assert mr.success
    assert mr.confidence_score == 9
    assert "vendor is dropping support" in mr.confidence_change
    assert "---CONFIDENCE---" not in mr.content


@pytest.mark.asyncio
async def test_run_round_no_confidence_block_leaves_fields_none(role_prompts):
    """A response without a confidence block must leave fields at defaults."""
    models = [ModelConfig(id="ollama/mistral", role="skeptic", timeout=10)]
    round_cfg = RoundConfig(name="debate", models=models)

    with patch("dissenter.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = _mock_response("Plain response without confidence.")
        result = await run_round(round_cfg, 0, "Which DB?", [], role_prompts)

    mr = result.results[0]
    assert mr.success
    assert mr.confidence_score is None
    assert mr.confidence_change == ""
