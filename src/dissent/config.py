from __future__ import annotations

import random
import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir
from pydantic import BaseModel, Field, model_validator


class ModelConfig(BaseModel):
    id: str
    role: str = "analyst"
    enabled: bool = True
    timeout: int = 180
    # API auth (default): litellm reads key from env var, or use api_key to override
    api_key: str | None = None
    # CLI auth: shell out to the provider's CLI tool instead of the API
    # auth = "cli" uses the CLI's stored session (e.g. a logged-in `claude` install)
    auth: str = "api"           # "api" | "cli"
    cli_command: str | None = None  # e.g. "claude", "gemini"; inferred from provider if None
    extra: dict[str, Any] = Field(default_factory=dict)


class RoundConfig(BaseModel):
    name: str = ""
    models: list[ModelConfig] = Field(default_factory=list)
    combine_model: str | None = None
    combine_timeout: int = 60

    @property
    def active_models(self) -> list[ModelConfig]:
        return [m for m in self.models if m.enabled]


class DissentConfig(BaseModel):
    output_dir: Path = Path("decisions")
    default_model: str | None = None
    rounds: list[RoundConfig] = Field(default_factory=list)
    role_distribution: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_rounds(self) -> "DissentConfig":
        if not self.rounds:
            raise ValueError("At least one [[rounds]] block must be configured")
        last = self.rounds[-1]
        n = len(last.active_models)
        if n not in (1, 2):
            raise ValueError(
                f"Final round must have exactly 1 or 2 enabled models, got {n}. "
                "Use 1 model with role 'chairman', or 2 models with a combine_model."
            )
        if n == 2 and last.combine_model is None:
            raise ValueError(
                "Final round with 2 models requires combine_model to be set "
                "(the model that merges their dual recommendations side-by-side)."
            )
        return self

    @property
    def is_dual_final(self) -> bool:
        return len(self.rounds[-1].active_models) == 2


def load_config(path: Path | None = None) -> DissentConfig:
    candidates: list[Path] = []
    if path:
        candidates.append(path)
    candidates.append(Path("dissent.toml"))
    candidates.append(Path(user_config_dir("dissent")) / "config.toml")

    for candidate in candidates:
        if candidate.exists():
            data = tomllib.loads(candidate.read_text())
            return DissentConfig.model_validate(data)

    raise FileNotFoundError(
        "No dissent.toml found. Create one or pass --config <path>."
    )


def assign_random_roles(
    model_ids: list[str],
    distribution: dict[str, float],
) -> list[tuple[str, str]]:
    """Randomly assign roles from a weighted distribution to a list of model IDs.

    Returns list of (model_id, role) pairs.
    """
    if not distribution:
        raise ValueError("role_distribution must be non-empty for random assignment")
    roles = list(distribution.keys())
    weights = list(distribution.values())
    assigned = random.choices(roles, weights=weights, k=len(model_ids))
    return list(zip(model_ids, assigned))
