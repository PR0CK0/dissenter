from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dissenter.cli import app

runner = CliRunner()

_NO_CLIS = {"claude": None, "gemini": None}
_NO_API_KEYS = {
    "anthropic": False, "openai": False, "gemini": False,
    "mistral": False, "groq": False, "cohere": False,
    "together_ai": False, "openrouter": False,
}
_ALL_API_KEYS = {k: True for k in _NO_API_KEYS}


def _write_cfg(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.toml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _invoke(cfg: Path, question: str = "test?", extra=()) -> any:
    """Invoke ask with mocked detect functions that block network/subprocess calls."""
    with patch("dissenter.cli.estimate_ollama_memory", return_value={"peak_bytes": 0, "warning": None}):
        return runner.invoke(app, ["ask", question, "--config", str(cfg)] + list(extra))


# ── Ollama ────────────────────────────────────────────────────────────────────

def test_preflight_missing_ollama_model(tmp_path):
    cfg = _write_cfg(tmp_path, """
        output_dir = "decisions"
        [[rounds]]
        name = "debate"
        [[rounds.models]]
        id = "ollama/not-pulled"
        role = "skeptic"
        [[rounds]]
        name = "final"
        [[rounds.models]]
        id = "ollama/mistral"
        role = "chairman"
    """)
    with patch("dissenter.cli.detect_ollama_models", return_value=["mistral"]), \
         patch("dissenter.cli.detect_clis", return_value=_NO_CLIS), \
         patch("dissenter.cli.detect_api_keys", return_value=_NO_API_KEYS):
        result = _invoke(cfg)

    assert result.exit_code == 1
    assert "not-pulled" in result.output
    assert "ollama pull" in result.output


def test_preflight_all_ollama_installed_passes(tmp_path):
    cfg = _write_cfg(tmp_path, """
        output_dir = "decisions"
        [[rounds]]
        name = "debate"
        [[rounds.models]]
        id = "ollama/mistral"
        role = "skeptic"
        [[rounds]]
        name = "final"
        [[rounds.models]]
        id = "ollama/mistral"
        role = "chairman"
    """)
    # Passes pre-flight, then fails because there's no litellm server — that's fine,
    # we just need it to get past the pre-flight check (exit code != 1 from pre-flight)
    with patch("dissenter.cli.detect_ollama_models", return_value=["mistral"]), \
         patch("dissenter.cli.detect_clis", return_value=_NO_CLIS), \
         patch("dissenter.cli.detect_api_keys", return_value=_NO_API_KEYS), \
         patch("dissenter.runner.litellm.acompletion", side_effect=Exception("connection refused")):
        result = _invoke(cfg)

    assert "ollama pull" not in (result.output or "")
    assert "Credential" not in (result.output or "")


# ── API keys ──────────────────────────────────────────────────────────────────

def test_preflight_missing_api_key(tmp_path):
    cfg = _write_cfg(tmp_path, """
        output_dir = "decisions"
        [[rounds]]
        name = "debate"
        [[rounds.models]]
        id = "anthropic/claude-sonnet-4-6"
        role = "skeptic"
        auth = "api"
        [[rounds]]
        name = "final"
        [[rounds.models]]
        id = "anthropic/claude-opus-4-6"
        role = "chairman"
        auth = "api"
    """)
    with patch("dissenter.cli.detect_ollama_models", return_value=[]), \
         patch("dissenter.cli.detect_clis", return_value=_NO_CLIS), \
         patch("dissenter.cli.detect_api_keys", return_value=_NO_API_KEYS):
        result = _invoke(cfg)

    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_preflight_explicit_api_key_in_config_skips_env_check(tmp_path):
    cfg = _write_cfg(tmp_path, """
        output_dir = "decisions"
        [[rounds]]
        name = "debate"
        [[rounds.models]]
        id = "anthropic/claude-sonnet-4-6"
        role = "skeptic"
        auth = "api"
        api_key = "sk-ant-explicit"
        [[rounds]]
        name = "final"
        [[rounds.models]]
        id = "anthropic/claude-opus-4-6"
        role = "chairman"
        auth = "api"
        api_key = "sk-ant-explicit"
    """)
    with patch("dissenter.cli.detect_ollama_models", return_value=[]), \
         patch("dissenter.cli.detect_clis", return_value=_NO_CLIS), \
         patch("dissenter.cli.detect_api_keys", return_value=_NO_API_KEYS), \
         patch("dissenter.runner.litellm.acompletion", side_effect=Exception("auth error")):
        result = _invoke(cfg)

    # Should pass pre-flight (explicit key), fail later at litellm level
    assert "ANTHROPIC_API_KEY" not in (result.output or "")


# ── CLI auth ──────────────────────────────────────────────────────────────────

def test_preflight_missing_cli_tool(tmp_path):
    cfg = _write_cfg(tmp_path, """
        output_dir = "decisions"
        [[rounds]]
        name = "debate"
        [[rounds.models]]
        id = "anthropic/claude-sonnet-4-6"
        role = "skeptic"
        auth = "cli"
        [[rounds]]
        name = "final"
        [[rounds.models]]
        id = "anthropic/claude-opus-4-6"
        role = "chairman"
        auth = "cli"
    """)
    with patch("dissenter.cli.detect_ollama_models", return_value=[]), \
         patch("dissenter.cli.detect_clis", return_value=_NO_CLIS), \
         patch("dissenter.cli.detect_api_keys", return_value=_NO_API_KEYS):
        result = _invoke(cfg)

    assert result.exit_code == 1
    assert "claude" in result.output
    assert "not on PATH" in result.output


def test_preflight_cli_tool_present_passes(tmp_path):
    cfg = _write_cfg(tmp_path, """
        output_dir = "decisions"
        [[rounds]]
        name = "debate"
        [[rounds.models]]
        id = "anthropic/claude-sonnet-4-6"
        role = "skeptic"
        auth = "cli"
        [[rounds]]
        name = "final"
        [[rounds.models]]
        id = "anthropic/claude-opus-4-6"
        role = "chairman"
        auth = "cli"
    """)
    clis_with_claude = {"claude": "/usr/local/bin/claude", "gemini": None}
    with patch("dissenter.cli.detect_ollama_models", return_value=[]), \
         patch("dissenter.cli.detect_clis", return_value=clis_with_claude), \
         patch("dissenter.cli.detect_api_keys", return_value=_NO_API_KEYS), \
         patch("dissenter.runner._query_model_cli", side_effect=Exception("auth error")):
        result = _invoke(cfg)

    assert "not found" not in (result.output or "")


# ── Multiple problems reported together ───────────────────────────────────────

def test_preflight_reports_all_problems(tmp_path):
    cfg = _write_cfg(tmp_path, """
        output_dir = "decisions"
        [[rounds]]
        name = "debate"
        [[rounds.models]]
        id = "ollama/missing-model"
        role = "skeptic"
        [[rounds.models]]
        id = "anthropic/claude-sonnet-4-6"
        role = "contrarian"
        auth = "api"
        [[rounds]]
        name = "final"
        [[rounds.models]]
        id = "ollama/mistral"
        role = "chairman"
    """)
    with patch("dissenter.cli.detect_ollama_models", return_value=["mistral"]), \
         patch("dissenter.cli.detect_clis", return_value=_NO_CLIS), \
         patch("dissenter.cli.detect_api_keys", return_value=_NO_API_KEYS):
        result = _invoke(cfg)

    assert result.exit_code == 1
    assert "missing-model" in result.output
    assert "ANTHROPIC_API_KEY" in result.output
