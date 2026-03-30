from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import Literal

from .config import DissentConfig
from .detect import KNOWN_PROVIDERS

_PROVIDER_CLI: dict[str, str] = {
    "anthropic": "claude",
    "gemini": "gemini",
    "google": "gemini",
}


@dataclass
class ConfigError:
    stage: Literal["parse", "schema", "preflight", "sanity"]
    message: str

    def __str__(self) -> str:
        return f"[{self.stage}] {self.message}"


def validate_toml(
    toml_str: str,
    ollama_installed: set[str] | list[str],
    clis: dict[str, str | None],
    api_keys: dict[str, bool],
) -> tuple[DissentConfig | None, list[ConfigError]]:
    """Validate a TOML string through the full pipeline.

    Returns (parsed_config_or_None, list_of_errors).
    """
    errors: list[ConfigError] = []
    ollama_set = set(ollama_installed)

    # ── Stage 1: TOML parse ───────────────────────────────────────────────
    try:
        data = tomllib.loads(toml_str)
    except Exception as e:
        errors.append(ConfigError("parse", f"Invalid TOML: {e}"))
        return None, errors

    # ── Stage 2: Pydantic schema ──────────────────────────────────────────
    try:
        cfg = DissentConfig.model_validate(data)
    except Exception as e:
        errors.append(ConfigError("schema", str(e)))
        return None, errors

    # ── Stage 3: Pre-flight credentials ───────────────────────────────────
    for r in cfg.rounds:
        for m in r.active_models:
            provider = m.id.split("/")[0]
            if provider == "ollama":
                name = m.id.split("/", 1)[1]
                if name not in ollama_set:
                    errors.append(ConfigError(
                        "preflight",
                        f"Ollama model '{m.id}' not installed — run: ollama pull {name}",
                    ))
            elif m.auth == "cli":
                cli = m.cli_command or _PROVIDER_CLI.get(provider)
                if cli and not clis.get(cli):
                    errors.append(ConfigError(
                        "preflight",
                        f"Model '{m.id}' uses CLI auth but '{cli}' is not on PATH",
                    ))
                elif not cli:
                    errors.append(ConfigError(
                        "preflight",
                        f"Model '{m.id}' uses CLI auth but no CLI is known for provider '{provider}'",
                    ))
            else:  # api auth
                if m.api_key:
                    continue
                if provider in api_keys and not api_keys[provider]:
                    env = KNOWN_PROVIDERS.get(provider, f"{provider.upper()}_API_KEY")
                    errors.append(ConfigError(
                        "preflight",
                        f"Model '{m.id}' requires API key — export {env}",
                    ))

    # ── Stage 4: Sanity ───────────────────────────────────────────────────
    if len(cfg.rounds) < 2:
        errors.append(ConfigError(
            "sanity",
            "Config needs at least 2 rounds (1+ debate rounds + a final round)",
        ))

    return cfg, errors
