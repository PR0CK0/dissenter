from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dissent.config import DissentConfig, ModelConfig, RoundConfig
from dissent.runner import run_all_rounds
from dissent.synthesis import synthesize


def _mock_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def two_round_cfg(tmp_path) -> DissentConfig:
    return DissentConfig(
        output_dir=tmp_path / "decisions",
        rounds=[
            RoundConfig(
                name="debate",
                models=[
                    ModelConfig(id="ollama/mistral", role="skeptic", timeout=10),
                    ModelConfig(id="ollama/mistral", role="pragmatist", timeout=10),
                ],
            ),
            RoundConfig(
                name="final",
                models=[ModelConfig(id="ollama/mistral", role="chairman", timeout=10)],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_full_pipeline_single_arbiter(two_round_cfg, tmp_path):
    call_count = 0

    async def fake_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        return _mock_response(f"Response {call_count}: some thoughtful answer about the topic")

    with patch("dissent.runner.litellm.acompletion", new_callable=AsyncMock) as mock_runner, \
         patch("dissent.synthesis.litellm.acompletion", new_callable=AsyncMock) as mock_synth:
        mock_runner.side_effect = fake_completion
        mock_synth.return_value = _mock_response("# ADR: Final Decision\n\nThe answer is clear.")

        all_rounds = await run_all_rounds(two_round_cfg, "Should we use Kafka or Postgres?")
        final_text, synthesis_results = await synthesize(
            "Should we use Kafka or Postgres?", all_rounds, two_round_cfg
        )

    assert len(all_rounds) == 2
    assert all_rounds[0].round_name == "debate"
    assert all_rounds[1].round_name == "final"
    assert "ADR" in final_text
    assert len(synthesis_results) == 1


@pytest.mark.asyncio
async def test_full_pipeline_output_files(two_round_cfg, tmp_path):
    async def fake_completion(**kwargs):
        return _mock_response("Some model output text here")

    with patch("dissent.runner.litellm.acompletion", new_callable=AsyncMock) as mock_runner, \
         patch("dissent.synthesis.litellm.acompletion", new_callable=AsyncMock) as mock_synth:
        mock_runner.side_effect = fake_completion
        mock_synth.return_value = _mock_response("# ADR: Test\n\nDecision made.")

        all_rounds = await run_all_rounds(two_round_cfg, "Test question?")
        final_text, _ = await synthesize("Test question?", all_rounds, two_round_cfg)

    assert "# ADR" in final_text


@pytest.mark.asyncio
async def test_all_models_fail_raises(two_round_cfg):
    with patch("dissent.runner.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError, match="All models failed"):
            await run_all_rounds(two_round_cfg, "Test question?")
