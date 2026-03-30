"""Config generator — LLM writes a dissenter.toml from a natural-language prompt.

Prompt is assembled from constant building blocks with pluggable context:
environment detection, role catalog, schema spec, user intent, and (on retry)
previous errors.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Optional

import litellm

from .config import DissentConfig, ModelConfig
from .detect import KNOWN_PROVIDERS, detect_api_keys, detect_clis, detect_ollama_models
from .validate import ConfigError, validate_toml

litellm.suppress_debug_info = True


# ── Prompt building blocks ────────────────────────────────────────────────────
# Each is a standalone string constant. `build_prompt()` assembles them with
# pluggable context slotted in.

_INTRO = """\
You are a config-file generator for **dissenter**, a multi-LLM debate engine.

Your job: given the user's intent and the environment available to them, produce
a valid dissenter TOML config file. Return ONLY the raw TOML — no explanation,
no code fences, no markdown. Just valid TOML that can be written directly to a
.toml file.
"""

_SCHEMA_SPEC = """\
## Config schema

```
output_dir = "decisions"          # where run outputs are saved

[[rounds]]                        # at least 2 rounds: 1+ debate + 1 final
name = "debate"                   # round label (must be unique across rounds)

[[rounds.models]]                 # 1+ models per debate round (run in parallel)
id      = "provider/model-name"   # litellm model ID (see environment below)
role    = "skeptic"               # one of the built-in roles (see role catalog)
auth    = "api"                   # "api" (default) or "cli"
timeout = 180                     # seconds per model call

# For Ollama models, always include:
# extra = { api_base = "http://localhost:11434" }

# Final round — MUST be the last [[rounds]] block.
# Exactly 1 model (chairman) OR exactly 2 models (dual arbiter).
[[rounds]]
name = "final"

[[rounds.models]]
id      = "provider/model-name"
role    = "chairman"              # for single arbiter
timeout = 300

# Dual arbiter alternative (2 models + combine_model):
# [[rounds]]
# name            = "final"
# combine_model   = "provider/model-name"
# combine_timeout = 60
# [[rounds.models]]
# id   = "..."
# role = "conservative"
# [[rounds.models]]
# id   = "..."
# role = "liberal"
```

Rules:
- At least 2 [[rounds]] blocks (debate rounds + final round).
- Final round: exactly 1 model with role "chairman", OR 2 models with
  combine_model set.
- Ollama model IDs use prefix "ollama/" (e.g. "ollama/mistral:latest").
- Ollama models MUST include extra = { api_base = "http://localhost:11434" }.
- Cloud models use their provider prefix (e.g. "anthropic/claude-sonnet-4-6").
- Each round name must be unique.
- Do NOT include api_key values — auth comes from env vars or CLI tools.
"""

_ROLES_CATALOG = """\
## Built-in roles (use these exact strings for the `role` field)

| Role               | Use in round | Description                                      |
|--------------------|--------------|--------------------------------------------------|
| devil's advocate   | debate       | Argue against the obvious or popular choice       |
| pragmatist         | debate       | Focus on what actually works in production        |
| skeptic            | debate       | Find hidden failure modes and long-term risks     |
| contrarian         | debate       | Surface the minority expert view                  |
| analyst            | debate/refine| Rigorous balanced analysis with concrete numbers  |
| researcher         | debate       | Find the most current information                 |
| second opinion     | refine       | Fresh-eyes independent review                     |
| chairman           | final (1)    | Decisive synthesis after all debate               |
| conservative       | final (2)    | Pragmatic executor — safest proven path           |
| liberal            | final (2)    | Ambitious visionary — boldest high-upside path    |

Assign diverse roles to debate models — diversity of framing matters more than
diversity of model. The same model can appear multiple times with different roles.
"""

_ENV_TEMPLATE = """\
## Environment — models available to this user RIGHT NOW

### Ollama (local)
{ollama_block}

### CLI tools
{cli_block}

### API providers (env var set)
{api_block}

IMPORTANT: Only use models from the lists above. Do NOT invent model IDs.
For Ollama, use exactly the names shown (prefixed with "ollama/").
For CLI-authenticated models, set auth = "cli".
For API-authenticated models, set auth = "api" (the default).
"""

_INTENT_TEMPLATE = """\
## User intent

{prompt}

Generate a dissenter TOML config that fulfils this intent using ONLY the models
available in the environment above. Return raw TOML only — no explanation.
"""

_RETRY_TEMPLATE = """\
## Previous attempt FAILED validation

Your previous config had the following errors:

{errors}

Your previous output:
```
{previous_toml}
```

Fix EXACTLY those errors. Keep everything else the same. Return corrected raw TOML only.
"""


# ── Environment formatting ────────────────────────────────────────────────────

def _format_env(
    ollama_models: list[str],
    clis: dict[str, str | None],
    api_keys: dict[str, bool],
) -> str:
    if ollama_models:
        ollama_block = "\n".join(f"- ollama/{m}" for m in ollama_models)
    else:
        ollama_block = "(none detected — ollama not running or no models pulled)"

    cli_lines = []
    for name, path in clis.items():
        if path:
            cli_lines.append(f"- {name} CLI: available ({path})")
    if not cli_lines:
        cli_lines.append("(no CLI tools detected)")
    cli_block = "\n".join(cli_lines)

    api_lines = []
    for provider, has_key in api_keys.items():
        if has_key:
            api_lines.append(f"- {provider} (key set)")
    if not api_lines:
        api_lines.append("(no API keys set)")
    api_block = "\n".join(api_lines)

    return _ENV_TEMPLATE.format(
        ollama_block=ollama_block,
        cli_block=cli_block,
        api_block=api_block,
    )


# ── Prompt assembly ──────────────────────────────────────────────────────────

def build_prompt(
    ollama_models: list[str],
    clis: dict[str, str | None],
    api_keys: dict[str, bool],
    intent: str,
) -> str:
    parts = [
        _INTRO,
        _SCHEMA_SPEC,
        _ROLES_CATALOG,
        _format_env(ollama_models, clis, api_keys),
        _INTENT_TEMPLATE.format(prompt=intent),
    ]
    return "\n---\n\n".join(parts)


def build_retry_prompt(
    ollama_models: list[str],
    clis: dict[str, str | None],
    api_keys: dict[str, bool],
    intent: str,
    previous_toml: str,
    errors: list[ConfigError],
) -> str:
    error_block = "\n".join(f"- {e}" for e in errors)
    parts = [
        _INTRO,
        _SCHEMA_SPEC,
        _ROLES_CATALOG,
        _format_env(ollama_models, clis, api_keys),
        _INTENT_TEMPLATE.format(prompt=intent),
        _RETRY_TEMPLATE.format(errors=error_block, previous_toml=previous_toml),
    ]
    return "\n---\n\n".join(parts)


# ── TOML extraction ──────────────────────────────────────────────────────────

_TOML_FENCE_RE = re.compile(r"```(?:toml)?\s*\n(.*?)```", re.DOTALL)


def _extract_toml(text: str) -> str:
    """Strip code fences if the model wrapped the output."""
    m = _TOML_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


# ── Model auto-picker ────────────────────────────────────────────────────────

def pick_generator_model(
    clis: dict[str, str | None],
    api_keys: dict[str, bool],
    ollama_models: list[str],
) -> ModelConfig:
    """Pick the best available model to run the generator.

    Priority: Claude CLI > Gemini CLI > Anthropic API > Gemini API > largest Ollama.
    """
    if clis.get("claude"):
        return ModelConfig(id="anthropic/claude-sonnet-4-6", role="generator", auth="cli", timeout=60)
    if clis.get("gemini"):
        return ModelConfig(id="gemini/gemini-2.0-flash", role="generator", auth="cli", timeout=60)
    if api_keys.get("anthropic"):
        return ModelConfig(id="anthropic/claude-sonnet-4-6", role="generator", auth="api", timeout=60)
    if api_keys.get("gemini"):
        return ModelConfig(id="gemini/gemini-2.0-flash", role="generator", auth="api", timeout=60)
    if api_keys.get("openai"):
        return ModelConfig(id="openai/gpt-4o", role="generator", auth="api", timeout=60)
    if ollama_models:
        return ModelConfig(
            id=f"ollama/{ollama_models[0]}",
            role="generator", auth="api", timeout=120,
            extra={"api_base": "http://localhost:11434"},
        )
    raise RuntimeError(
        "No models available to generate config. "
        "Run `dissenter models` to check your setup."
    )


# ── LLM call ─────────────────────────────────────────────────────────────────

async def _call_llm(model: ModelConfig, prompt: str) -> str:
    from .runner import _query_model_cli

    if model.auth == "cli":
        return await asyncio.wait_for(
            _query_model_cli(model, prompt),
            timeout=float(model.timeout),
        )
    kwargs: dict = {
        "model": model.id,
        "messages": [{"role": "user", "content": prompt}],
        **(model.extra or {}),
    }
    if model.api_key:
        kwargs["api_key"] = model.api_key
    response = await asyncio.wait_for(
        litellm.acompletion(**kwargs),
        timeout=float(model.timeout),
    )
    return response.choices[0].message.content or ""


# ── Generate with retry ──────────────────────────────────────────────────────

@dataclass
class GenerateResult:
    toml_str: str
    config: DissentConfig
    attempts: int
    model_used: str


async def generate_config(
    intent: str,
    generator_model: ModelConfig,
    ollama_models: list[str],
    clis: dict[str, str | None],
    api_keys: dict[str, bool],
    max_retries: int = 3,
    on_attempt: Optional[callable] = None,
) -> GenerateResult:
    """Generate a valid dissenter config via LLM, retrying on validation errors.

    Args:
        intent: User's natural-language description of the desired config.
        generator_model: Model to use for generation.
        ollama_models: Installed Ollama model names.
        clis: Detected CLI tools.
        api_keys: API key availability.
        max_retries: Max generation attempts.
        on_attempt: Optional callback(attempt_num, errors_or_None) for progress.

    Returns:
        GenerateResult with the valid TOML and parsed config.

    Raises:
        RuntimeError if all attempts fail.
    """
    previous_toml: Optional[str] = None
    previous_errors: Optional[list[ConfigError]] = None

    for attempt in range(1, max_retries + 1):
        if on_attempt:
            on_attempt(attempt, previous_errors)

        if previous_toml and previous_errors:
            prompt = build_retry_prompt(
                ollama_models, clis, api_keys, intent,
                previous_toml, previous_errors,
            )
        else:
            prompt = build_prompt(ollama_models, clis, api_keys, intent)

        raw = await _call_llm(generator_model, prompt)
        toml_str = _extract_toml(raw)

        cfg, errors = validate_toml(toml_str, ollama_models, clis, api_keys)

        if not errors and cfg is not None:
            return GenerateResult(
                toml_str=toml_str,
                config=cfg,
                attempts=attempt,
                model_used=generator_model.id,
            )

        previous_toml = toml_str
        previous_errors = errors

    # All attempts failed — raise with last errors
    error_summary = "\n".join(f"  - {e}" for e in (previous_errors or []))
    raise RuntimeError(
        f"Failed to generate a valid config after {max_retries} attempts.\n"
        f"Last errors:\n{error_summary}"
    )
