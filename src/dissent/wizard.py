from __future__ import annotations

import random
import shutil
from pathlib import Path

import questionary
import typer
from platformdirs import user_config_dir
from rich.console import Console
from rich.panel import Panel

from .detect import detect_api_keys, detect_clis, detect_ollama_model_sizes, detect_ollama_models, infer_auth

_GB = 1024 ** 3

_ALL_ROLES = [
    "devil's advocate",
    "pragmatist",
    "skeptic",
    "contrarian",
    "analyst",
    "researcher",
    "second opinion",
    "chairman",
    "conservative",
    "liberal",
]

_DEBATE_ROLES = [
    "skeptic",
    "contrarian",
    "pragmatist",
    "devil's advocate",
    "analyst",
    "researcher",
]

# Curated cloud model suggestions shown in autocomplete
_EXIT_MESSAGES = [
    "The dissent stands unresolved.",
    "No consensus reached. The question endures.",
    "Deliberation interrupted — the verdict remains contested.",
    "The panel adjourned without a decision.",
    "Some questions resist resolution.",
    "The debate was cut short. The truth, as always, elusive.",
    "Silence fell over the chamber.",
    "The dissent was not defeated — merely paused.",
    "Not all debates reach their conclusion.",
    "Withdrawn before the chairman could speak.",
    "Agreement was not reached. Perhaps it never will be.",
    "The argument continues elsewhere.",
]


def exit_message() -> str:
    return random.choice(_EXIT_MESSAGES)


_CLOUD_MODELS_BY_PROVIDER: dict[str, list[str]] = {
    "anthropic": [
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-opus-4-6",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "gemini": [
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.0-pro",
    ],
    "openai": [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
    ],
    "groq": [
        "groq/llama-3.1-70b-versatile",
        "groq/mixtral-8x7b-32768",
    ],
    "mistral": [
        "mistral/mistral-large-latest",
    ],
}

# Map from provider prefix to the detect_api_keys() key and detect_clis() key
_PROVIDER_CLI: dict[str, str] = {
    "anthropic": "claude",
    "gemini": "gemini",
}


def _available_cloud_models(clis: dict[str, str | None], api_keys: dict[str, bool]) -> list[str]:
    """Return cloud model IDs for providers where a CLI or API key is detected."""
    available: list[str] = []
    for provider, models in _CLOUD_MODELS_BY_PROVIDER.items():
        cli_name = _PROVIDER_CLI.get(provider)
        has_cli = bool(cli_name and clis.get(cli_name))
        has_key = api_keys.get(provider, False)
        if has_cli or has_key:
            available.extend(models)
    return available


def _q(prompt) -> str:
    """Run a questionary prompt; exit cleanly on Ctrl+C."""
    try:
        result = prompt.ask()
    except KeyboardInterrupt:
        result = None
    if result is None:
        print(f"\n  {exit_message()}\n")
        raise typer.Exit(0)
    return result


def _collect_model(
    label: str,
    clis: dict[str, str | None],
    ollama_models: list[str],
    default_role: str,
    console: Console,
    api_keys: dict[str, bool] | None = None,
) -> dict:
    console.print(f"\n  [bold]{label}[/bold]")

    if api_keys is None:
        api_keys = detect_api_keys()

    ollama_choices = [f"ollama/{m}" for m in ollama_models]
    cloud_choices = _available_cloud_models(clis, api_keys)
    _CUSTOM = "[ type custom ID... ]"
    model_choices = ollama_choices + cloud_choices + [_CUSTOM]

    selected_model = _q(questionary.select(
        "    Model ID",
        choices=model_choices,
    ))
    if selected_model == _CUSTOM:
        selected_model = _q(questionary.text("    Enter model ID (e.g. anthropic/claude-sonnet-4-6)"))
    model_id = selected_model

    role_choices = _ALL_ROLES + ["[ custom... ]"]
    default_role_q = default_role if default_role in _ALL_ROLES else _ALL_ROLES[0]
    selected_role = _q(questionary.select(
        "    Role",
        choices=role_choices,
        default=default_role_q,
    ))
    if selected_role == "[ custom... ]":
        selected_role = _q(questionary.text("    Custom role name"))

    inferred = infer_auth(model_id, clis)
    auth_choices = [
        "api   — read key from env var (or set api_key in config)",
        "cli   — use installed claude / gemini session (no key needed)",
    ]
    auth_default = auth_choices[1] if inferred == "cli" else auth_choices[0]
    auth = _q(questionary.select("    Auth", choices=auth_choices, default=auth_default)).split()[0]

    timeout_str = _q(questionary.text("    Timeout (seconds)", default="180"))
    timeout = int(timeout_str) if timeout_str.strip().isdigit() else 180

    m: dict = {"id": model_id, "role": selected_role, "auth": auth, "timeout": timeout}
    if model_id.startswith("ollama/"):
        m["extra"] = {"api_base": "http://localhost:11434"}
    return m


def _render_toml(rounds_data: list[dict], output_dir: str) -> str:
    lines = [
        "# dissenter — multi-LLM debate engine",
        f'output_dir = "{output_dir}"',
        "",
    ]
    for i, rd in enumerate(rounds_data):
        is_final = i == len(rounds_data) - 1
        label = f"Final round: {rd['name']}" if is_final else f"Round {i + 1}: {rd['name']}"
        fill = "─" * max(4, 52 - len(label))
        lines.append(f"# ── {label} {fill}")
        lines.append("[[rounds]]")
        lines.append(f'name = "{rd["name"]}"')
        if rd.get("combine_model"):
            lines.append(f'combine_model   = "{rd["combine_model"]}"')
            lines.append(f'combine_timeout = {rd.get("combine_timeout", 60)}')
        lines.append("")
        for m in rd["models"]:
            lines.append("[[rounds.models]]")
            lines.append(f'id      = "{m["id"]}"')
            lines.append(f'role    = "{m["role"]}"')
            if m.get("auth") == "cli":
                lines.append(f'auth    = "cli"')
            lines.append(f'timeout = {m["timeout"]}')
            if m.get("extra"):
                kv = ", ".join(f'{k} = "{v}"' for k, v in m["extra"].items())
                lines.append(f'extra   = {{ {kv} }}')
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _models_fitting_budget(memory_bytes: int | None) -> tuple[list[str], int]:
    """Return (model_names_that_fit, total_bytes) sorted smallest-first to maximise count."""
    sizes = detect_ollama_model_sizes()
    if not sizes:
        return [], 0
    models_asc = sorted(sizes.items(), key=lambda x: x[1])
    selected, total = [], 0
    for name, size in models_asc:
        if memory_bytes is None or total + size <= memory_bytes:
            selected.append(name)
            total += size
    if not selected:
        selected = [models_asc[0][0]]
        total = models_asc[0][1]
    return selected, total


def run_auto_wizard(
    output_path: Path,
    save_name: str | None,
    n_debate_rounds: int,
    memory_gb: float | None,
    console: Console,
) -> None:
    """Non-interactive: auto-populate a config from local Ollama models."""
    memory_bytes = int(memory_gb * _GB) if memory_gb is not None else None
    all_sizes = detect_ollama_model_sizes()

    if not all_sizes:
        console.print("[red]No Ollama models found.[/red] Run [bold]ollama pull <model>[/bold] first.")
        raise typer.Exit(1)

    debate_models, total_bytes = _models_fitting_budget(memory_bytes)
    peak_gb = total_bytes / _GB

    console.print(f"\n  Found [bold]{len(all_sizes)}[/bold] Ollama model(s). "
                  f"Fitting [bold]{len(debate_models)}[/bold] per round "
                  f"(~{peak_gb:.1f} GB peak).")

    if memory_gb is not None and total_bytes > memory_bytes:
        console.print(f"  [yellow]⚠  Models exceed {memory_gb:.0f} GB budget — using smallest available.[/yellow]")

    models_desc = sorted(all_sizes.items(), key=lambda x: x[1], reverse=True)
    chairman_name = next(
        (name for name, size in models_desc if memory_bytes is None or size <= memory_bytes),
        list(all_sizes.keys())[0],
    )

    rounds_data: list[dict] = []
    for ri in range(n_debate_rounds):
        round_name = "debate" if ri == 0 else f"round_{ri + 1}"
        models = []
        for mi, name in enumerate(debate_models):
            models.append({
                "id": f"ollama/{name}",
                "role": _DEBATE_ROLES[mi % len(_DEBATE_ROLES)],
                "auth": "api",
                "timeout": 180,
                "extra": {"api_base": "http://localhost:11434"},
            })
        rounds_data.append({"name": round_name, "models": models})

    rounds_data.append({
        "name": "final",
        "models": [{
            "id": f"ollama/{chairman_name}",
            "role": "chairman",
            "auth": "api",
            "timeout": 300,
            "extra": {"api_base": "http://localhost:11434"},
        }],
    })

    toml_content = _render_toml(rounds_data, "decisions")
    console.print("\n[bold]── Preview ──[/bold]\n")
    console.print(toml_content)

    if save_name:
        preset_dir = Path(user_config_dir("dissenter"))
        preset_dir.mkdir(parents=True, exist_ok=True)
        output_path = preset_dir / f"{save_name}.toml"

    if _q(questionary.confirm(f"Save to {output_path}?", default=True)):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(toml_content, encoding="utf-8")
        console.print(f"\n[green]✓[/green] Saved [bold]{output_path}[/bold]")
        if save_name:
            console.print(f"  Run [bold]dissenter ask \"your question\" --config {save_name}[/bold]")
        else:
            console.print("  Run [bold]dissenter ask \"your question\"[/bold] to get started.")
    else:
        console.print("[dim]Cancelled.[/dim]")


def run_wizard(output_path: Path, force: bool, save_name: str | None, console: Console) -> None:
    """Interactive config wizard."""
    clis = detect_clis()
    ollama_models = detect_ollama_models()
    api_keys = detect_api_keys()

    env_lines: list[str] = []
    for cli, path in clis.items():
        if path:
            env_lines.append(f"  [green]✓[/green] {cli} CLI   [dim]{path}[/dim]")
        else:
            env_lines.append(f"  [dim]✗ {cli} CLI   not found[/dim]")
    if ollama_models:
        env_lines.append(f"  [green]✓[/green] Ollama   [dim]{', '.join(ollama_models)}[/dim]")
    else:
        env_lines.append("  [dim]✗ Ollama   not found or no models installed[/dim]")

    console.print(Panel("\n".join(env_lines), title="[bold]dissenter init[/bold]", expand=False))
    console.print()

    # If only the example exists, offer a quick copy instead of full wizard
    example = Path("dissenter.example.toml")
    if not save_name and not output_path.exists() and example.exists():
        console.print(
            f"  Found [bold]dissenter.example.toml[/bold] but no [bold]dissenter.toml[/bold].\n"
            "  Want to copy it as a starting point, or build a config step-by-step?"
        )
        if _q(questionary.confirm("  Copy dissenter.example.toml → dissenter.toml now?", default=True)):
            shutil.copy(example, output_path)
            console.print(f"\n[green]✓[/green] Copied to [bold]{output_path}[/bold]")
            console.print("  Edit it to match your models, then run [bold]dissenter ask \"your question\"[/bold].")
            raise typer.Exit(0)
        console.print("  Starting step-by-step wizard...\n")

    # Resolve save destination
    if save_name:
        preset_dir = Path(user_config_dir("dissenter"))
        preset_dir.mkdir(parents=True, exist_ok=True)
        output_path = preset_dir / f"{save_name}.toml"
        console.print(f"  Saving preset [bold]{save_name}[/bold] → {output_path}\n")
    elif output_path.exists() and not force:
        console.print(
            f"  [yellow]⚠[/yellow]  {output_path} already exists.\n"
            "  Use [bold]--force[/bold] to overwrite it, or "
            "[bold]--save <name>[/bold] to create a named preset instead.\n"
        )
        if not _q(questionary.confirm("Overwrite existing file?", default=False)):
            raise typer.Exit(0)

    n_debate = int(_q(questionary.text("Debate rounds (not counting final)", default="1")))

    rounds_data: list[dict] = []

    for ri in range(n_debate):
        console.print(f"\n[bold]── Round {ri + 1} ──[/bold]")
        name = _q(questionary.text("  Name", default="debate" if ri == 0 else f"round_{ri + 1}"))
        n_models = int(_q(questionary.text("  How many models?", default="2")))
        models = [
            _collect_model(f"Model {mi + 1}", clis, ollama_models, _DEBATE_ROLES[mi % len(_DEBATE_ROLES)], console, api_keys)
            for mi in range(n_models)
        ]
        rounds_data.append({"name": name, "models": models})

    console.print("\n[bold]── Final Round ──[/bold]")
    final_type_choices = [
        "chairman  — single model writes the final decision",
        "dual      — conservative vs liberal + a combiner model",
    ]
    final_type = _q(questionary.select("  Type", choices=final_type_choices)).split()[0]
    final_name = _q(questionary.text("  Name", default="final"))

    if final_type == "dual":
        con = _collect_model("Conservative model", clis, ollama_models, "conservative", console, api_keys)
        con["role"] = "conservative"
        lib = _collect_model("Liberal model", clis, ollama_models, "liberal", console, api_keys)
        lib["role"] = "liberal"

        _CUSTOM = "[ type custom ID... ]"
        cloud_choices = _available_cloud_models(clis, api_keys)
        combine_choices = [f"ollama/{m}" for m in ollama_models] + cloud_choices + [_CUSTOM]
        combine = _q(questionary.select("  Combine model ID", choices=combine_choices))
        if combine == _CUSTOM:
            combine = _q(questionary.text("  Enter combine model ID"))
        combine_timeout = int(_q(questionary.text("  Combine timeout (seconds)", default="60")))
        rounds_data.append({
            "name": final_name,
            "models": [con, lib],
            "combine_model": combine,
            "combine_timeout": combine_timeout,
        })
    else:
        chair = _collect_model("Chairman model", clis, ollama_models, "chairman", console, api_keys)
        chair["role"] = "chairman"
        rounds_data.append({"name": final_name, "models": [chair]})

    toml_content = _render_toml(rounds_data, "decisions")
    console.print("\n[bold]── Preview ──[/bold]\n")
    console.print(toml_content)

    if _q(questionary.confirm(f"Save to {output_path}?", default=True)):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(toml_content, encoding="utf-8")
        console.print(f"\n[green]✓[/green] Saved [bold]{output_path}[/bold]")
        if save_name:
            console.print(f"  Run [bold]dissenter ask \"your question\" --config {save_name}[/bold]")
        else:
            console.print("  Run [bold]dissenter ask \"your question\"[/bold] to get started.")
    else:
        console.print("[dim]Cancelled.[/dim]")
