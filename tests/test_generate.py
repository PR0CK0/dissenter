"""Tests for dissenter.generate — prompt builders, TOML extraction, model picker, and generate_config()."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dissenter.config import ModelConfig
from dissenter.generate import (
    GenerateResult,
    _extract_toml,
    build_prompt,
    build_retry_prompt,
    generate_config,
    pick_generator_model,
)
from dissenter.validate import ConfigError

# A minimal valid TOML that validate_toml will accept.
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

INVALID_TOML = 'output_dir = "decisions"\n'  # missing rounds → schema error


# ── _extract_toml ────────────────────────────────────────────────────────────


def test_extract_toml_from_fenced_block():
    text = '```toml\nfoo = "bar"\n```'
    assert _extract_toml(text) == 'foo = "bar"'


def test_extract_toml_no_fence():
    text = 'foo = "bar"'
    assert _extract_toml(text) == 'foo = "bar"'


def test_extract_toml_fence_no_lang():
    text = '```\nfoo = "bar"\n```'
    assert _extract_toml(text) == 'foo = "bar"'


# ── build_prompt ─────────────────────────────────────────────────────────────


def _env():
    return dict(
        ollama_models=["mistral", "llama3"],
        clis={"claude": "/usr/bin/claude", "gemini": None},
        api_keys={"anthropic": True},
    )


def test_build_prompt_contains_all_sections():
    prompt = build_prompt(**_env(), intent="Help me decide on a database")
    # Intro section
    assert "config-file generator" in prompt
    # Schema section
    assert "Config schema" in prompt
    # Roles catalog
    assert "Built-in roles" in prompt
    # Environment
    assert "Environment" in prompt
    # Intent
    assert "Help me decide on a database" in prompt


def test_build_prompt_includes_ollama_models():
    prompt = build_prompt(**_env(), intent="test")
    assert "ollama/mistral" in prompt
    assert "ollama/llama3" in prompt


# ── build_retry_prompt ───────────────────────────────────────────────────────


def test_build_retry_prompt_includes_errors():
    errors = [ConfigError("schema", "missing rounds")]
    prompt = build_retry_prompt(
        **_env(),
        intent="test",
        previous_toml="bad toml",
        errors=errors,
    )
    assert "missing rounds" in prompt
    assert "FAILED validation" in prompt


def test_build_retry_prompt_includes_previous_toml():
    prompt = build_retry_prompt(
        **_env(),
        intent="test",
        previous_toml='output_dir = "x"',
        errors=[ConfigError("parse", "oops")],
    )
    assert 'output_dir = "x"' in prompt


# ── pick_generator_model ────────────────────────────────────────────────────


def test_pick_generator_claude_cli_first():
    m = pick_generator_model(
        clis={"claude": "/usr/bin/claude", "gemini": "/usr/bin/gemini"},
        api_keys={"anthropic": True},
        ollama_models=["mistral"],
    )
    assert "anthropic" in m.id
    assert m.auth == "cli"


def test_pick_generator_gemini_cli_second():
    m = pick_generator_model(
        clis={"claude": None, "gemini": "/usr/bin/gemini"},
        api_keys={},
        ollama_models=["mistral"],
    )
    assert "gemini" in m.id
    assert m.auth == "cli"


def test_pick_generator_api_key_third():
    m = pick_generator_model(
        clis={"claude": None, "gemini": None},
        api_keys={"anthropic": True},
        ollama_models=["mistral"],
    )
    assert "anthropic" in m.id
    assert m.auth == "api"


def test_pick_generator_ollama_fallback():
    m = pick_generator_model(
        clis={"claude": None, "gemini": None},
        api_keys={},
        ollama_models=["mistral"],
    )
    assert m.id == "ollama/mistral"


def test_pick_generator_nothing_raises():
    with pytest.raises(RuntimeError, match="No models available"):
        pick_generator_model(
            clis={"claude": None, "gemini": None},
            api_keys={},
            ollama_models=[],
        )


# ── generate_config (async, mocked LLM) ─────────────────────────────────────

_GEN_MODEL = ModelConfig(id="ollama/mistral", role="generator", auth="api", timeout=60,
                         extra={"api_base": "http://localhost:11434"})


@pytest.mark.asyncio
async def test_generate_config_valid_first_attempt():
    mock_llm = AsyncMock(return_value=VALID_TOML)
    with patch("dissenter.generate._call_llm", mock_llm):
        result = await generate_config(
            intent="test intent",
            generator_model=_GEN_MODEL,
            ollama_models=["mistral"],
            clis={"claude": None, "gemini": None},
            api_keys={},
        )
    assert isinstance(result, GenerateResult)
    assert result.attempts == 1
    mock_llm.assert_called_once()


@pytest.mark.asyncio
async def test_generate_config_retries_on_invalid():
    mock_llm = AsyncMock(side_effect=[INVALID_TOML, VALID_TOML])
    with patch("dissenter.generate._call_llm", mock_llm):
        result = await generate_config(
            intent="test intent",
            generator_model=_GEN_MODEL,
            ollama_models=["mistral"],
            clis={"claude": None, "gemini": None},
            api_keys={},
        )
    assert result.attempts == 2
    assert mock_llm.call_count == 2


@pytest.mark.asyncio
async def test_generate_config_all_retries_fail():
    mock_llm = AsyncMock(return_value=INVALID_TOML)
    with patch("dissenter.generate._call_llm", mock_llm):
        with pytest.raises(RuntimeError, match="Failed to generate"):
            await generate_config(
                intent="test intent",
                generator_model=_GEN_MODEL,
                ollama_models=["mistral"],
                clis={"claude": None, "gemini": None},
                api_keys={},
                max_retries=2,
            )
    assert mock_llm.call_count == 2
