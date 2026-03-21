from __future__ import annotations

import pytest
from pydantic import ValidationError

from dissent.config import DissentConfig, ModelConfig, RoundConfig, assign_random_roles


def _make_model(**kwargs) -> dict:
    return {"id": "ollama/mistral", "role": "skeptic", **kwargs}


def _make_single_final() -> dict:
    return {
        "name": "final",
        "models": [{"id": "anthropic/claude-opus-4-6", "role": "chairman"}],
    }


def _make_dual_final() -> dict:
    return {
        "name": "final",
        "combine_model": "ollama/mistral",
        "models": [
            {"id": "anthropic/claude-opus-4-6", "role": "conservative"},
            {"id": "gemini/gemini-2.0-flash", "role": "liberal"},
        ],
    }


class TestRoundValidation:
    def test_valid_single_final(self):
        cfg = DissentConfig(rounds=[RoundConfig(**_make_single_final())])
        assert len(cfg.rounds) == 1

    def test_valid_dual_final(self):
        cfg = DissentConfig(rounds=[RoundConfig(**_make_dual_final())])
        assert cfg.is_dual_final

    def test_no_rounds_raises(self):
        with pytest.raises(ValidationError, match="At least one"):
            DissentConfig(rounds=[])

    def test_zero_enabled_models_in_final_raises(self):
        with pytest.raises(ValidationError):
            DissentConfig(
                rounds=[
                    RoundConfig(
                        name="final",
                        models=[ModelConfig(id="x", role="a", enabled=False)],
                    )
                ]
            )

    def test_three_models_in_final_raises(self):
        with pytest.raises(ValidationError, match="1 or 2"):
            DissentConfig(
                rounds=[
                    RoundConfig(
                        name="final",
                        models=[
                            ModelConfig(id="a", role="r"),
                            ModelConfig(id="b", role="r"),
                            ModelConfig(id="c", role="r"),
                        ],
                    )
                ]
            )

    def test_dual_without_combine_model_raises(self):
        with pytest.raises(ValidationError, match="combine_model"):
            DissentConfig(
                rounds=[
                    RoundConfig(
                        name="final",
                        models=[
                            ModelConfig(id="a", role="conservative"),
                            ModelConfig(id="b", role="liberal"),
                        ],
                    )
                ]
            )

    def test_same_model_different_roles_valid(self):
        cfg = DissentConfig(
            rounds=[
                RoundConfig(
                    name="debate",
                    models=[
                        ModelConfig(id="ollama/mistral", role="skeptic"),
                        ModelConfig(id="ollama/mistral", role="pragmatist"),
                        ModelConfig(id="ollama/mistral", role="contrarian"),
                    ],
                ),
                RoundConfig(**_make_single_final()),
            ]
        )
        assert len(cfg.rounds[0].active_models) == 3

    def test_multi_round_valid(self):
        cfg = DissentConfig(
            rounds=[
                RoundConfig(
                    name="debate",
                    models=[ModelConfig(id="ollama/mistral", role="skeptic")],
                ),
                RoundConfig(
                    name="refine",
                    models=[ModelConfig(id="ollama/mistral", role="analyst")],
                ),
                RoundConfig(**_make_single_final()),
            ]
        )
        assert len(cfg.rounds) == 3


class TestRandomRoles:
    def test_assign_roles_same_length(self):
        dist = {"skeptic": 0.5, "pragmatist": 0.5}
        pairs = assign_random_roles(["a", "b", "c"], dist)
        assert len(pairs) == 3
        for model_id, role in pairs:
            assert role in dist

    def test_empty_distribution_raises(self):
        with pytest.raises(ValueError):
            assign_random_roles(["a"], {})
