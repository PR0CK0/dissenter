from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import DissentConfig

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

_GB = 1024 ** 3
_MB = 1024 ** 2


def detect_ollama_models() -> list[str]:
    """Return list of locally installed Ollama model names."""
    return list(_ollama_list_raw().keys())


def detect_ollama_model_sizes() -> dict[str, int]:
    """Return mapping of model name -> size in bytes from `ollama list`."""
    return _ollama_list_raw()


def _ollama_list_raw() -> dict[str, int]:
    """Parse `ollama list` output into {name: size_bytes}."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {}
        lines = result.stdout.strip().splitlines()
        out: dict[str, int] = {}
        for line in lines[1:]:  # skip NAME header
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            # columns: NAME  ID  SIZE_VAL  SIZE_UNIT  ...MODIFIED
            try:
                size_val = float(parts[2])
                unit = parts[3].upper() if len(parts) > 3 else "B"
                multiplier = {"GB": _GB, "MB": _MB, "KB": 1024, "B": 1}.get(unit, 1)
                out[name] = int(size_val * multiplier)
            except (ValueError, IndexError):
                out[name] = 0
        return out
    except Exception:
        return {}


def estimate_ollama_memory(cfg: "DissentConfig") -> dict:
    """Estimate peak concurrent RAM needed for Ollama models in the config.

    Models within a round run in parallel, so the peak is the heaviest round.
    Returns:
        rounds:     list of {name, models: [{id, size_bytes}], total_bytes}
        peak_bytes: max total_bytes across rounds
        warning:    human-readable warning string, or None
    """
    sizes = detect_ollama_model_sizes()
    result_rounds = []

    for rnd in cfg.rounds:
        ollama_models = [m for m in rnd.active_models if m.id.startswith("ollama/")]
        if not ollama_models:
            continue
        round_models = []
        round_total = 0
        for m in ollama_models:
            model_name = m.id.split("/", 1)[1]
            size = sizes.get(model_name, 0)
            round_models.append({"id": m.id, "name": model_name, "size_bytes": size})
            round_total += size
        result_rounds.append({"name": rnd.name, "models": round_models, "total_bytes": round_total})

    peak = max((r["total_bytes"] for r in result_rounds), default=0)

    warning: str | None = None
    if peak >= 16 * _GB:
        warning = f"~{peak / _GB:.1f} GB peak RAM for Ollama — this may exhaust system memory"
    elif peak >= 8 * _GB:
        warning = f"~{peak / _GB:.1f} GB peak RAM for Ollama — ensure you have enough free memory"

    return {"rounds": result_rounds, "peak_bytes": peak, "warning": warning}


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
