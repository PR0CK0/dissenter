from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from .detect import detect_clis, detect_ollama_models, infer_auth

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
        "# dissent — multi-LLM debate engine",
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


def run_wizard(output_path: Path, force: bool, console: Console) -> None:
    """Interactive config wizard. Writes a dissent.toml to output_path."""
    clis = detect_clis()
    ollama_models = detect_ollama_models()

    env_lines: list[str] = []
    for cli, path in clis.items():
        if path:
            env_lines.append(f"  [green]✓[/green] {cli} CLI   [dim]{path}[/dim]")
        else:
            env_lines.append(f"  [dim]✗ {cli} CLI   not found[/dim]")
    if ollama_models:
        env_lines.append(
            f"  [green]✓[/green] Ollama   [dim]{', '.join(ollama_models)}[/dim]"
        )
    else:
        env_lines.append("  [dim]✗ Ollama   not found or no models installed[/dim]")

    console.print(Panel("\n".join(env_lines), title="[bold]dissent init[/bold]", expand=False))
    console.print()

    if output_path.exists() and not force:
        if not typer.confirm(f"{output_path} already exists. Overwrite?", default=False):
            raise typer.Exit(0)

    output_dir = typer.prompt("Output directory", default="decisions")
    n_debate = int(typer.prompt("Debate rounds (not counting final)", default="1"))

    rounds_data: list[dict] = []

    for ri in range(n_debate):
        console.print(f"\n[bold]── Round {ri + 1} ──[/bold]")
        name = typer.prompt("  Name", default="debate" if ri == 0 else f"round_{ri + 1}")
        n_models = int(typer.prompt("  Models", default="2"))
        models = [
            _collect_model(
                f"Model {mi + 1}", clis, _DEBATE_ROLES[mi % len(_DEBATE_ROLES)], console
            )
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
        output_path.write_text(toml_content)
        console.print(f"\n[green]✓[/green] Saved [bold]{output_path}[/bold]")
        console.print(f"  Run [bold]dissent ask \"your question\"[/bold] to get started.")
    else:
        console.print("[dim]Cancelled.[/dim]")
