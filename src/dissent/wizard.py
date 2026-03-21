from __future__ import annotations

from pathlib import Path

import typer
from platformdirs import user_config_dir
from rich.console import Console
from rich.panel import Panel

from .detect import detect_clis, detect_ollama_model_sizes, detect_ollama_models, infer_auth

_GB = 1024 ** 3

_DEBATE_ROLES = [
    "skeptic",
    "contrarian",
    "pragmatist",
    "devil's advocate",
    "analyst",
    "researcher",
]


def _collect_model(
    label: str,
    clis: dict[str, str | None],
    default_role: str,
    console: Console,
) -> dict:
    console.print(f"\n  [bold]{label}[/bold]")
    model_id = typer.prompt("    ID (e.g. ollama/mistral, anthropic/claude-sonnet-4-6)")
    role = typer.prompt("    Role", default=default_role)
    auth = typer.prompt("    Auth (api/cli)", default=infer_auth(model_id, clis))
    timeout = int(typer.prompt("    Timeout (s)", default="180"))
    m: dict = {"id": model_id, "role": role, "auth": auth, "timeout": timeout}
    if model_id.startswith("ollama/"):
        api_base = typer.prompt("    Ollama API base", default="http://localhost:11434")
        m["extra"] = {"api_base": api_base}
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
        # Even the smallest model exceeds budget — use it anyway
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
    """Non-interactive wizard: auto-populate a config from local Ollama models."""
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

    # Chairman: largest single model that fits in budget (most capable for synthesis)
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

    # Resolve save path
    if save_name:
        preset_dir = Path(user_config_dir("dissenter"))
        preset_dir.mkdir(parents=True, exist_ok=True)
        output_path = preset_dir / f"{save_name}.toml"

    if typer.confirm(f"Save to {output_path}?", default=True):
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
            f"\n  Found [bold]dissenter.example.toml[/bold] but no [bold]dissenter.toml[/bold].\n"
            "  Have you copied and customised it yet?"
        )
        if typer.confirm("  Copy dissenter.example.toml → dissenter.toml now?", default=True):
            import shutil
            shutil.copy(example, output_path)
            console.print(f"\n[green]✓[/green] Copied to [bold]{output_path}[/bold]")
            console.print("  Edit it to match your models, then run [bold]dissenter ask \"your question\"[/bold].")
            raise typer.Exit(0)
        console.print()

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
        if not typer.confirm("Overwrite existing file?", default=False):
            raise typer.Exit(0)

    output_dir = typer.prompt("Output directory", default="decisions")
    n_debate = int(typer.prompt("Debate rounds (not counting final)", default="1"))

    rounds_data: list[dict] = []

    for ri in range(n_debate):
        console.print(f"\n[bold]── Round {ri + 1} ──[/bold]")
        name = typer.prompt("  Name", default="debate" if ri == 0 else f"round_{ri + 1}")
        n_models = int(typer.prompt("  Models", default="2"))
        models = [
            _collect_model(f"Model {mi + 1}", clis, _DEBATE_ROLES[mi % len(_DEBATE_ROLES)], console)
            for mi in range(n_models)
        ]
        rounds_data.append({"name": name, "models": models})

    console.print("\n[bold]── Final Round ──[/bold]")
    final_type = typer.prompt("  Type (chairman/dual)", default="chairman")
    final_name = typer.prompt("  Name", default="final")

    if final_type == "dual":
        con = _collect_model("Conservative model", clis, "conservative", console)
        con["role"] = "conservative"
        lib = _collect_model("Liberal model", clis, "liberal", console)
        lib["role"] = "liberal"
        combine = typer.prompt("  Combine model ID")
        combine_timeout = int(typer.prompt("  Combine timeout (s)", default="60"))
        rounds_data.append({
            "name": final_name,
            "models": [con, lib],
            "combine_model": combine,
            "combine_timeout": combine_timeout,
        })
    else:
        chair = _collect_model("Chairman model", clis, "chairman", console)
        chair["role"] = "chairman"
        rounds_data.append({"name": final_name, "models": [chair]})

    toml_content = _render_toml(rounds_data, output_dir)
    console.print("\n[bold]── Preview ──[/bold]\n")
    console.print(toml_content)

    if typer.confirm(f"Save to {output_path}?", default=True):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(toml_content, encoding="utf-8")
        console.print(f"\n[green]✓[/green] Saved [bold]{output_path}[/bold]")
        if save_name:
            console.print(f"  Run [bold]dissenter ask \"your question\" --config {save_name}[/bold]")
        else:
            console.print("  Run [bold]dissenter ask \"your question\"[/bold] to get started.")
    else:
        console.print("[dim]Cancelled.[/dim]")
