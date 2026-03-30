"""Tests for dissenter.validate — ConfigError and validate_toml()."""
from __future__ import annotations

from dissenter.validate import ConfigError, validate_toml
from dissenter.config import DissentConfig

# A minimal valid TOML with two rounds: one debate + one final (single chairman).
VALID_TOML = """\
output_dir = "decisions"

[[rounds]]
name = "debate"

[[rounds.models]]
id   = "ollama/mistral"
role = "skeptic"
extra = { api_base = "http://localhost:11434" }

[[rounds]]
name = "final"

[[rounds.models]]
id   = "ollama/mistral"
role = "chairman"
extra = { api_base = "http://localhost:11434" }
"""


def _defaults():
    """Common kwargs for validate_toml in most tests."""
    return dict(
        ollama_installed=["mistral"],
        clis={"claude": None, "gemini": None},
        api_keys={},
    )


# ── happy path ───────────────────────────────────────────────────────────────


def test_validate_valid_toml():
    cfg, errors = validate_toml(VALID_TOML, **_defaults())
    assert errors == []
    assert cfg is not None


def test_validate_returns_config_on_success():
    cfg, errors = validate_toml(VALID_TOML, **_defaults())
    assert isinstance(cfg, DissentConfig)
    assert len(cfg.rounds) == 2


# ── parse errors ─────────────────────────────────────────────────────────────


def test_validate_invalid_toml_syntax():
    cfg, errors = validate_toml("{{not valid toml!!", **_defaults())
    assert len(errors) == 1
    assert errors[0].stage == "parse"


def test_validate_returns_none_on_parse_error():
    cfg, errors = validate_toml("{{bad", **_defaults())
    assert cfg is None


# ── schema errors ────────────────────────────────────────────────────────────


def test_validate_missing_rounds():
    toml_str = 'output_dir = "decisions"\n'
    cfg, errors = validate_toml(toml_str, **_defaults())
    assert any(e.stage == "schema" for e in errors)


def test_validate_final_round_wrong_model_count():
    """Final round with 3 models should trigger a schema error."""
    toml_str = """\
output_dir = "decisions"

[[rounds]]
name = "debate"

[[rounds.models]]
id   = "ollama/mistral"
role = "skeptic"
extra = { api_base = "http://localhost:11434" }

[[rounds]]
name = "final"

[[rounds.models]]
id   = "ollama/mistral"
role = "chairman"
extra = { api_base = "http://localhost:11434" }

[[rounds.models]]
id   = "ollama/mistral"
role = "conservative"
extra = { api_base = "http://localhost:11434" }

[[rounds.models]]
id   = "ollama/mistral"
role = "liberal"
extra = { api_base = "http://localhost:11434" }
"""
    cfg, errors = validate_toml(toml_str, **_defaults())
    assert any(e.stage == "schema" for e in errors)


# ── preflight errors ─────────────────────────────────────────────────────────


def test_validate_missing_ollama_model():
    """Ollama model not in the installed list should produce a preflight error."""
    cfg, errors = validate_toml(
        VALID_TOML,
        ollama_installed=[],  # mistral NOT installed
        clis={"claude": None, "gemini": None},
        api_keys={},
    )
    assert any(e.stage == "preflight" for e in errors)
    assert any("not installed" in e.message for e in errors)


def test_validate_missing_api_key():
    """API-auth model whose provider key is missing should produce a preflight error."""
    toml_str = """\
output_dir = "decisions"

[[rounds]]
name = "debate"

[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "skeptic"

[[rounds]]
name = "final"

[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "chairman"
"""
    cfg, errors = validate_toml(
        toml_str,
        ollama_installed=[],
        clis={"claude": None, "gemini": None},
        api_keys={"anthropic": False},
    )
    assert any(e.stage == "preflight" for e in errors)
    assert any("API key" in e.message for e in errors)


def test_validate_missing_cli():
    """CLI-auth model with no CLI on PATH should produce a preflight error."""
    toml_str = """\
output_dir = "decisions"

[[rounds]]
name = "debate"

[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "skeptic"
auth = "cli"

[[rounds]]
name = "final"

[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "chairman"
auth = "cli"
"""
    cfg, errors = validate_toml(
        toml_str,
        ollama_installed=[],
        clis={"claude": None, "gemini": None},
        api_keys={},
    )
    assert any(e.stage == "preflight" for e in errors)
    assert any("CLI auth" in e.message for e in errors)


def test_validate_explicit_api_key_skips_env_check():
    """When api_key is set on the model itself, env-var check is skipped."""
    toml_str = """\
output_dir = "decisions"

[[rounds]]
name = "debate"

[[rounds.models]]
id      = "anthropic/claude-sonnet-4-6"
role    = "skeptic"
api_key = "sk-test-1234"

[[rounds]]
name = "final"

[[rounds.models]]
id      = "anthropic/claude-sonnet-4-6"
role    = "chairman"
api_key = "sk-test-5678"
"""
    cfg, errors = validate_toml(
        toml_str,
        ollama_installed=[],
        clis={"claude": None, "gemini": None},
        api_keys={"anthropic": False},
    )
    # No preflight errors because api_key is provided inline
    assert not any(e.stage == "preflight" for e in errors)
