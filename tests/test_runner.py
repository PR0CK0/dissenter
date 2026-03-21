from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dissent.config import DissentConfig, ModelConfig, RoundConfig
from dissent.runner import ModelResult, RoundResult, run_round, _build_prior_context


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

    with patch("dissent.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = _mock_response("some response text")
        result = await run_round(round_cfg, 0, "Test question?", [], role_prompts)

    assert len(result.results) == 2
    assert all(r.success for r in result.results)
    assert result.round_name == "debate"


@pytest.mark.asyncio
async def test_run_round_error_captured(role_prompts):
    models = [ModelConfig(id="bad/model", role="skeptic", timeout=10)]
    round_cfg = RoundConfig(name="test", models=models)

    with patch("dissent.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
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

    with patch("dissent.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
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
