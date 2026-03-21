from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.rule import Rule
from rich.tree import Tree

from .config import load_config, DissentConfig
from .runner import run_all_rounds, RoundResult
from .synthesis import synthesize

app = typer.Typer(
    help="dissent — multi-LLM debate engine for architectural decisions.",
    add_completion=False,
)

out = Console()
err = Console(stderr=True)


@app.command()
def ask(
    question: str = typer.Argument(..., help="The question to debate"),
    config: Path = typer.Option(None, "--config", "-c", help="Config file path"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory"),
) -> None:
    """Run the full debate pipeline and synthesize a decision."""
    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if output_dir:
        cfg.output_dir = output_dir

    total_models = sum(len(r.active_models) for r in cfg.rounds)
    err.print()
    err.print(Rule("[bold]dissent[/bold]"))
    err.print(f"  [dim]Question:[/dim] {question}")
    err.print(f"  [dim]Rounds  :[/dim] {len(cfg.rounds)}")
    err.print(f"  [dim]Models  :[/dim] {total_models} across all rounds")
    err.print()

    try:
        all_rounds, final_text, synthesis_results = asyncio.run(
            _main(question, cfg)
        )
    except RuntimeError as e:
        err.print()
        err.print(f"[red]Error:[/red] {e}")
        err.print()
        raise typer.Exit(1)

    # Save outputs — everything lives under decisions/<timestamp>/
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = cfg.output_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save per-round debug files
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

    # Save synthesis model outputs
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
def show(
    config: Path = typer.Option(None, "--config", "-c", help="Config file path"),
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
                f"[dim]timeout:[/dim] {m.timeout}s"
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
