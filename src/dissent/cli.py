from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.rule import Rule
from rich.tree import Tree

from .config import DissentConfig, ModelConfig, RoundConfig, load_config
from .detect import KNOWN_PROVIDERS, detect_api_keys, detect_clis, detect_ollama_models, infer_auth
from .runner import run_all_rounds
from .synthesis import synthesize

app = typer.Typer(
    help="dissent — multi-LLM debate engine for architectural decisions.",
    add_completion=False,
)

out = Console()
err = Console(stderr=True)

_DEFAULT_DEBATE_ROLES = ["skeptic", "contrarian", "pragmatist", "devil's advocate", "analyst"]


# ── Config builders for inline flags ─────────────────────────────────────────

def _config_from_flags(
    models: list[str],
    chairman: str | None,
    output_dir: Path | None,
) -> DissentConfig:
    clis = detect_clis()
    debate_models: list[ModelConfig] = []
    for i, spec in enumerate(models):
        # Format: model_id or model_id@role
        if "@" in spec:
            model_id, role = spec.rsplit("@", 1)
        else:
            model_id = spec
            role = _DEFAULT_DEBATE_ROLES[i % len(_DEFAULT_DEBATE_ROLES)]
        extra = {"api_base": "http://localhost:11434"} if model_id.startswith("ollama/") else {}
        debate_models.append(
            ModelConfig(id=model_id, role=role, auth=infer_auth(model_id, clis), extra=extra)
        )

    chair_id = chairman or models[0].split("@")[0]
    chair_extra = {"api_base": "http://localhost:11434"} if chair_id.startswith("ollama/") else {}
    chairman_model = ModelConfig(
        id=chair_id, role="chairman",
        auth=infer_auth(chair_id, clis), extra=chair_extra,
    )
    return DissentConfig(
        output_dir=output_dir or Path("decisions"),
        rounds=[
            RoundConfig(name="debate", models=debate_models),
            RoundConfig(name="final", models=[chairman_model]),
        ],
    )


def _config_from_quick(output_dir: Path | None) -> DissentConfig:
    ollama_models = detect_ollama_models()
    if not ollama_models:
        raise RuntimeError(
            "--quick requires local Ollama models. "
            "Install Ollama and run 'ollama pull mistral' first."
        )
    debate_models = [
        ModelConfig(
            id=f"ollama/{m}",
            role=_DEFAULT_DEBATE_ROLES[i % len(_DEFAULT_DEBATE_ROLES)],
            extra={"api_base": "http://localhost:11434"},
        )
        for i, m in enumerate(ollama_models)
    ]
    chairman = ModelConfig(
        id=f"ollama/{ollama_models[0]}",
        role="chairman",
        extra={"api_base": "http://localhost:11434"},
    )
    return DissentConfig(
        output_dir=output_dir or Path("decisions"),
        rounds=[
            RoundConfig(name="debate", models=debate_models),
            RoundConfig(name="final", models=[chairman]),
        ],
    )


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def ask(
    question: str = typer.Argument(..., help="The question to debate"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    model: Optional[List[str]] = typer.Option(
        None, "--model", "-m",
        help="model_id[@role] for the debate round — repeat for multiple models",
    ),
    chairman: Optional[str] = typer.Option(
        None, "--chairman", help="Model ID for the final (synthesis) round"
    ),
    quick: bool = typer.Option(
        False, "--quick", help="Auto-detect installed Ollama models and run immediately"
    ),
) -> None:
    """Run the full debate pipeline and synthesize a decision.

    Config priority: --quick > --model/--chairman > --config / dissent.toml
    """
    try:
        if quick:
            cfg = _config_from_quick(output_dir)
        elif model:
            cfg = _config_from_flags(list(model), chairman, output_dir)
        else:
            cfg = load_config(config)
            if output_dir:
                cfg.output_dir = output_dir
    except (FileNotFoundError, RuntimeError) as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    total_models = sum(len(r.active_models) for r in cfg.rounds)
    err.print()
    err.print(Rule("[bold]dissent[/bold]"))
    err.print(f"  [dim]Question:[/dim] {question}")
    err.print(f"  [dim]Rounds  :[/dim] {len(cfg.rounds)}")
    err.print(f"  [dim]Models  :[/dim] {total_models} across all rounds")
    err.print()

    try:
        all_rounds, final_text, synthesis_results = asyncio.run(_main(question, cfg))
    except RuntimeError as e:
        err.print()
        err.print(f"[red]Error:[/red] {e}")
        err.print()
        raise typer.Exit(1)

    # Save outputs — everything lives under decisions/<timestamp>/
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = cfg.output_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    for rr in all_rounds:
        round_dir = run_dir / f"round_{rr.round_index + 1}_{rr.round_name}"
        round_dir.mkdir()
        for r in rr.results:
            safe = r.model_id.replace("/", "_").replace(":", "_")
            role_safe = r.role.replace(" ", "_").replace("'", "")
            fname = f"{safe}__{role_safe}"
            (round_dir / f"{fname}.md").write_text(r.content or "")
            if r.error:
                (round_dir / f"{fname}.err").write_text(r.error)

    final_round_dir = run_dir / f"round_{len(all_rounds)}_{cfg.rounds[-1].name or 'final'}"
    final_round_dir.mkdir(exist_ok=True)
    for r in synthesis_results:
        safe = r.model_id.replace("/", "_").replace(":", "_")
        role_safe = r.role.replace(" ", "_").replace("'", "")
        (final_round_dir / f"{safe}__{role_safe}.md").write_text(r.content or "")

    output_file = run_dir / "decision.md"
    output_file.write_text(final_text)

    abs_file = output_file.absolute()
    abs_dir = run_dir.absolute()

    err.print()
    err.print(Rule("[bold green]Done[/bold green]"))
    err.print(f"  [green]Decision :[/green] [link=file://{abs_file}]{abs_file}[/link]")
    err.print(f"  [dim]Run dir  : [link=file://{abs_dir}]{abs_dir}[/link][/dim]")
    err.print()


@app.command()
def init(
    output: Path = typer.Option(Path("dissent.toml"), "--output", "-o", help="Config file to create"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without prompting"),
) -> None:
    """Interactively create a dissent.toml config file."""
    from .wizard import run_wizard
    run_wizard(output, force, err)


@app.command()
def models() -> None:
    """Show detected local models, CLI tools, and API key status."""
    from rich.table import Table

    ollama = detect_ollama_models()
    clis = detect_clis()
    api_keys = detect_api_keys()

    out.print()

    # Ollama
    out.print("[bold]Ollama (local)[/bold]")
    if ollama:
        for m in ollama:
            out.print(f"  [green]✓[/green]  {m}")
    else:
        out.print("  [dim]no models — is ollama running? try: ollama pull mistral[/dim]")

    # CLI tools
    out.print()
    out.print("[bold]CLI tools[/bold]")
    for cli, path in clis.items():
        if path:
            out.print(f"  [green]✓[/green]  {cli:<10} [dim]{path}[/dim]")
        else:
            out.print(f"  [dim]✗  {cli}   not found[/dim]")

    # API providers
    out.print()
    out.print("[bold]API providers[/bold]")
    for provider, env_var in KNOWN_PROVIDERS.items():
        has_key = api_keys[provider]
        tick = "[green]✓[/green]" if has_key else "[dim]✗[/dim]"
        note = "[green]key set[/green]" if has_key else f"[dim]export {env_var}[/dim]"
        out.print(f"  {tick}  {provider:<18} {note}")

    out.print()


@app.command()
def show(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Show the current configuration — rounds, models, roles."""
    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    tree = Tree(f"[bold]dissent[/bold]  [dim]{cfg.output_dir}[/dim]")
    for i, round_cfg in enumerate(cfg.rounds):
        label = f"Round {i+1}: [cyan]{round_cfg.name or '(unnamed)'}[/cyan]"
        if i == len(cfg.rounds) - 1:
            label += "  [yellow][final][/yellow]"
        r_node = tree.add(label)
        for m in round_cfg.models:
            status = "[green]✓[/green]" if m.enabled else "[dim]—[/dim]"
            r_node.add(
                f"{status} [bold]{m.id}[/bold]  [dim]role:[/dim] {m.role}  "
                f"[dim]auth:[/dim] {m.auth}  [dim]timeout:[/dim] {m.timeout}s"
            )
        if round_cfg.combine_model:
            r_node.add(f"[dim]combine via:[/dim] {round_cfg.combine_model}")

    out.print(tree)

    if cfg.role_distribution:
        out.print()
        out.print("[dim]Role distribution:[/dim]")
        for role, weight in cfg.role_distribution.items():
            out.print(f"  {role}: {weight:.0%}")


async def _main(question: str, cfg: DissentConfig):
    err.print(Rule("[dim]beginning debate[/dim]", style="dim"))
    all_rounds = await run_all_rounds(cfg, question)

    err.print()
    err.print(Rule("[dim]synthesizing[/dim]", style="dim"))

    final_text, synthesis_results = await synthesize(question, all_rounds, cfg)
    return all_rounds, final_text, synthesis_results
