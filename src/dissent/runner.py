from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import litellm
from rich.console import Console
from rich.live import Live
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .config import DissentConfig, ModelConfig, RoundConfig
from .roles import get_prompt, load_roles

litellm.suppress_debug_info = True

console = Console(stderr=True)

_SPECIALIST_PROMPT = """\
You are a senior software architect. {role_instruction}

{prior_context}Analyze this question:
{question}

Respond in this exact markdown structure:

## Recommendation
[Your clear, opinionated recommendation in 1-2 sentences]

## Pros
- [bullet]

## Cons / Risks
- [bullet]

## Critical Considerations
- [bullet]

## Recent Developments (2024-2026)
[Relevant ecosystem changes. Note if you have no web access.]

Be direct, technical, and opinionated. Engineers will act on this.
"""

_PRIOR_CONTEXT_TEMPLATE = """\
[Prior debate — Round {index}: "{name}"]

{responses}

[End prior debate]

"""


@dataclass
class ModelResult:
    model_id: str
    role: str
    round_name: str
    content: str = ""
    elapsed: float = 0.0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return bool(self.content) and self.error is None

    @property
    def word_count(self) -> int:
        return len(self.content.split())

    @property
    def short_id(self) -> str:
        return self.model_id.split("/")[-1]


@dataclass
class RoundResult:
    round_name: str
    round_index: int
    results: list[ModelResult] = field(default_factory=list)

    @property
    def successful(self) -> list[ModelResult]:
        return [r for r in self.results if r.success]


def _build_prior_context(prior_rounds: list[RoundResult]) -> str:
    if not prior_rounds:
        return ""
    parts = []
    for rr in prior_rounds:
        responses = "\n\n".join(
            f"**{r.short_id}** (role: {r.role}):\n{r.content}"
            for r in rr.successful
        )
        parts.append(
            _PRIOR_CONTEXT_TEMPLATE.format(
                index=rr.round_index + 1,
                name=rr.round_name,
                responses=responses,
            )
        )
    return "".join(parts)


# Known provider → CLI command mappings
_PROVIDER_CLI: dict[str, str] = {
    "anthropic": "claude",
    "gemini": "gemini",
    "google": "gemini",
}


def _infer_cli(model_id: str) -> str | None:
    provider = model_id.split("/")[0]
    return _PROVIDER_CLI.get(provider)


async def _query_model_cli(cfg: ModelConfig, prompt: str) -> str:
    """Query a model via its CLI tool, using the CLI's stored session auth."""
    cli = cfg.cli_command or _infer_cli(cfg.id)
    if not cli:
        raise ValueError(
            f"No CLI command known for provider '{cfg.id.split('/')[0]}'. "
            "Set cli_command in config (e.g. cli_command = \"claude\")."
        )

    # All CLIs: pass prompt via stdin with non-interactive/print flag
    # claude: `claude --print`   gemini: `gemini`  (add more as needed)
    cli_args: list[str] = [cli]
    if cli == "claude":
        cli_args += ["--print"]

    proc = await asyncio.create_subprocess_exec(
        *cli_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=prompt.encode())
    if proc.returncode != 0:
        err_text = stderr.decode().strip()
        raise RuntimeError(err_text or f"'{cli}' exited with code {proc.returncode}")
    return stdout.decode().strip()


def _classify_error(exc: Exception) -> str:
    msg = str(exc)
    t = type(exc).__name__
    if "AuthenticationError" in t or "authentication" in msg.lower() or "api key" in msg.lower() or "Missing API Key" in msg:
        provider = msg.split(":")[0].strip() if ":" in msg else "provider"
        return f"missing/invalid API key ({provider}) — set the env var or add api_key to config"
    if "NotFoundError" in t or "model not found" in msg.lower() or (
        "pull" in msg.lower() and "ollama" in msg.lower()
    ):
        return "model not installed — run 'ollama pull <model>' first"
    if "APIConnectionError" in t or "Connection refused" in msg or "OllamaError" in t:
        if "not found" in msg.lower() or "try pulling" in msg.lower():
            return "model not installed — run 'ollama pull <model>' first"
        if "ollama" in msg.lower() or "11434" in msg:
            return "cannot reach Ollama — is 'ollama serve' running?"
        return f"connection failed — is the server running? ({msg[:80]})"
    if "RateLimitError" in t:
        return "rate limited — wait and retry, or switch models"
    if "ContextWindowExceededError" in t or "context length" in msg.lower():
        return "context window exceeded — debate history too long for this model"
    return msg[:120]


async def _query_model(
    cfg: ModelConfig,
    round_name: str,
    question: str,
    prior_context: str,
    role_prompts: dict[str, str],
) -> ModelResult:
    role_instruction = get_prompt(cfg.role, role_prompts)
    prompt = _SPECIALIST_PROMPT.format(
        role_instruction=role_instruction,
        prior_context=prior_context,
        question=question,
    )
    start = time.monotonic()
    result = ModelResult(model_id=cfg.id, role=cfg.role, round_name=round_name)

    try:
        if cfg.auth == "cli":
            result.content = await asyncio.wait_for(
                _query_model_cli(cfg, prompt),
                timeout=cfg.timeout,
            )
        else:
            kwargs: dict = {
                "model": cfg.id,
                "messages": [{"role": "user", "content": prompt}],
                **cfg.extra,
            }
            if cfg.api_key:
                kwargs["api_key"] = cfg.api_key
            response = await asyncio.wait_for(
                litellm.acompletion(**kwargs),
                timeout=cfg.timeout,
            )
            result.content = response.choices[0].message.content or ""
        result.elapsed = time.monotonic() - start
    except asyncio.TimeoutError:
        result.error = f"timed out after {cfg.timeout}s"
        result.elapsed = float(cfg.timeout)
    except Exception as exc:
        result.error = _classify_error(exc)
        result.elapsed = time.monotonic() - start

    return result


def _status_table(
    round_name: str,
    round_index: int,
    results: dict[str, ModelResult],
    done: set[str],
    start_times: dict[str, float],
) -> Table:
    now = time.monotonic()
    table = Table(
        title=f"Round {round_index + 1}: {round_name}",
        show_header=True,
        header_style="bold",
        box=None,
        padding=(0, 1),
    )
    table.add_column("Model", min_width=26)
    table.add_column("Role", min_width=18)
    table.add_column("Time", justify="right", min_width=6)
    table.add_column("Status", min_width=22)

    for key, result in results.items():
        elapsed = result.elapsed if key in done else now - start_times[key]
        elapsed_str = f"{elapsed:.0f}s"

        if key not in done:
            status = Text("⠸ running", style="yellow")
        elif result.error:
            status = Text(f"✗ {result.error[:35]}", style="red")
        else:
            status = Text(f"✓  ~{result.word_count} words", style="green")

        table.add_row(result.short_id, result.role, elapsed_str, status)

    return table


async def run_round(
    round_cfg: RoundConfig,
    round_index: int,
    question: str,
    prior_rounds: list[RoundResult],
    role_prompts: dict[str, str],
) -> RoundResult:
    active = round_cfg.active_models
    prior_context = _build_prior_context(prior_rounds)
    round_name = round_cfg.name or f"round_{round_index + 1}"

    # Use (model_id, role, index) as unique key to support same model with different roles
    keys = [f"{m.id}::{m.role}::{i}" for i, m in enumerate(active)]
    results: dict[str, ModelResult] = {
        k: ModelResult(model_id=m.id, role=m.role, round_name=round_name)
        for k, m in zip(keys, active)
    }
    done: set[str] = set()
    start_times: dict[str, float] = {k: time.monotonic() for k in keys}

    async def run_and_track(key: str, cfg: ModelConfig) -> None:
        result = await _query_model(cfg, round_name, question, prior_context, role_prompts)
        results[key] = result
        done.add(key)

    tasks = [asyncio.create_task(run_and_track(k, m)) for k, m in zip(keys, active)]

    with Live(console=console, refresh_per_second=4, transient=False) as live:
        while not all(t.done() for t in tasks):
            live.update(_status_table(round_name, round_index, results, done, start_times))
            await asyncio.sleep(0.25)
        live.update(_status_table(round_name, round_index, results, done, start_times))

    round_result = RoundResult(round_name=round_name, round_index=round_index)
    round_result.results = list(results.values())
    return round_result


async def run_all_rounds(
    cfg: DissentConfig,
    question: str,
) -> list[RoundResult]:
    role_prompts = load_roles()
    all_results: list[RoundResult] = []

    for i, round_cfg in enumerate(cfg.rounds):
        active = round_cfg.active_models
        if not active:
            console.print(f"[yellow]Round {i+1} '{round_cfg.name}' has no enabled models, skipping.[/yellow]")
            continue

        console.print()
        console.print(Rule(f"[bold]Round {i+1} of {len(cfg.rounds)}: {round_cfg.name or ''}[/bold] ({len(active)} models)", style="dim"))

        rr = await run_round(round_cfg, i, question, all_results, role_prompts)
        all_results.append(rr)

        if not rr.successful:
            raise RuntimeError(
                f"All models failed in round {i+1} '{round_cfg.name}'. Cannot continue."
            )

    return all_results
