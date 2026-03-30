from __future__ import annotations

import random
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .paths import configs_dir, decisions_dir


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
    output_dir: Path = Field(default_factory=decisions_dir)
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
        p = Path(path)
        # bare name with no separators → treat as a named preset
        if not p.exists() and "/" not in str(path) and "\\" not in str(path):
            p = configs_dir() / f"{path}.toml"
        candidates.append(p)
    candidates.append(Path("dissenter.toml"))
    candidates.append(configs_dir() / "config.toml")

    for candidate in candidates:
        if candidate.exists():
            data = tomllib.loads(candidate.read_text(encoding="utf-8"))
            return DissentConfig.model_validate(data)

    raise FileNotFoundError("no config found")


def config_to_toml(cfg: DissentConfig) -> str:
    """Serialize a DissentConfig back to TOML text (no extra dependencies)."""
    lines: list[str] = [
        "# dissenter — config snapshot",
        f'output_dir = "{cfg.output_dir}"',
        "",
    ]
    if cfg.default_model:
        lines.append(f'default_model = "{cfg.default_model}"')
        lines.append("")
    if cfg.role_distribution:
        lines.append("[role_distribution]")
        for role, weight in cfg.role_distribution.items():
            lines.append(f'"{role}" = {weight}')
        lines.append("")

    for i, rnd in enumerate(cfg.rounds):
        is_final = i == len(cfg.rounds) - 1
        label = f"Final: {rnd.name}" if is_final else f"Round {i + 1}: {rnd.name}"
        fill = "─" * max(4, 52 - len(label))
        lines += [f"# ── {label} {fill}", "[[rounds]]", f'name = "{rnd.name}"']
        if rnd.combine_model:
            lines.append(f'combine_model   = "{rnd.combine_model}"')
            lines.append(f'combine_timeout = {rnd.combine_timeout}')
        lines.append("")
        for m in rnd.models:
            lines.append("[[rounds.models]]")
            lines.append(f'id      = "{m.id}"')
            lines.append(f'role    = "{m.role}"')
            if not m.enabled:
                lines.append("enabled = false")
            if m.auth != "api":
                lines.append(f'auth    = "{m.auth}"')
            lines.append(f'timeout = {m.timeout}')
            if m.api_key:
                lines.append(f'api_key = "{m.api_key}"')
            if m.cli_command:
                lines.append(f'cli_command = "{m.cli_command}"')
            if m.extra:
                kv = ", ".join(f'{k} = "{v}"' for k, v in m.extra.items())
                lines.append(f'extra   = {{ {kv} }}')
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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
