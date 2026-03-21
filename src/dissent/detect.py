from __future__ import annotations

import os
import shutil
import subprocess

# Known providers and the env var that holds their API key
KNOWN_PROVIDERS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "cohere": "CO_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def detect_ollama_models() -> list[str]:
    """Return list of locally installed Ollama model names."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().splitlines()
        models: list[str] = []
        for line in lines[1:]:  # skip NAME header
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except Exception:
        return []


def detect_clis() -> dict[str, str | None]:
    """Return mapping of CLI name -> absolute path (None if not found)."""
    return {
        "claude": shutil.which("claude"),
        "gemini": shutil.which("gemini"),
    }


def detect_api_keys() -> dict[str, bool]:
    """Return mapping of provider name -> whether its env var is set."""
    return {
        provider: bool(os.environ.get(env_var))
        for provider, env_var in KNOWN_PROVIDERS.items()
    }


def infer_auth(model_id: str, clis: dict[str, str | None]) -> str:
    """Return 'cli' if a CLI tool is available for this model's provider, else 'api'."""
    provider = model_id.split("/")[0]
    if provider == "anthropic" and clis.get("claude"):
        return "cli"
    if provider in ("gemini", "google") and clis.get("gemini"):
        return "cli"
    return "api"
