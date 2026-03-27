from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.tree import Tree

from importlib.metadata import version as _pkg_version

from .config import DissentConfig, ModelConfig, RoundConfig, config_to_toml, load_config

try:
    _VERSION = _pkg_version("dissenter")
except Exception:
    _VERSION = "?"
from .detect import (
    KNOWN_PROVIDERS, detect_api_keys, detect_clis, detect_ollama_models,
    estimate_ollama_memory, infer_auth,
)
from .runner import run_all_rounds
from .synthesis import synthesize

app = typer.Typer(
    help="dissenter — multi-LLM debate engine for architectural decisions.",
    add_completion=False,
)

out = Console()
err = Console(stderr=True)

_DEFAULT_DEBATE_ROLES = ["skeptic", "contrarian", "pragmatist", "devil's advocate", "analyst"]


def _header(cmd: str) -> None:
    err.print()
    err.print(Rule(f"[bold]dissenter[/bold] [dim]v{_VERSION} — {cmd}[/dim]"))


def _version_callback(value: bool) -> None:
    if value:
        out.print(f"dissenter v{_VERSION}")
        raise typer.Exit()


@app.callback()
def _app_callback(
    version: bool = typer.Option(False, "--version", "-v", is_eager=True, callback=_version_callback, help="Show version and exit"),
) -> None:
    pass


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
    deep: bool = typer.Option(
        False, "--deep", help="Inject a mutual critique round after debate, before synthesis (+accuracy)"
    ),
) -> None:
    """Run the full debate pipeline and synthesize a decision.

    Config priority: --quick > --model/--chairman > --config > dissenter.toml

    Examples:
      dissenter ask "Should we use Kafka or a Postgres outbox?"
      dissenter ask "..." --config fast                   # named preset
      dissenter ask "..." --quick                         # auto-detect Ollama models
      dissenter ask "..." --model ollama/mistral@skeptic --model ollama/phi3@pragmatist
      dissenter ask "..." --deep                          # add mutual critique round
      dissenter ask "..." --config decisions/20260321/config.toml  # exact re-run
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
    except FileNotFoundError:
        from pathlib import Path
        if Path("dissenter.example.toml").exists():
            err.print()
            err.print("[yellow]No dissenter.toml found.[/yellow] Looks like you haven't set up your config yet.\n")
            err.print("  Copy the example config and customise it:\n")
            err.print("    [bold]cp dissenter.example.toml dissenter.toml[/bold]   [dim](Mac/Linux)[/dim]")
            err.print("    [bold]copy dissenter.example.toml dissenter.toml[/bold] [dim](Windows)[/dim]\n")
            err.print("  Or let the wizard do it:  [bold]dissenter init[/bold]")
            err.print("  Or auto-generate from Ollama models:  [bold]dissenter init --auto[/bold]\n")
        else:
            err.print("\n[yellow]No config found.[/yellow] Run [bold]dissenter init[/bold] to get started.\n")
        raise typer.Exit(1)
    except RuntimeError as e:
        err.print(f"\n[red]Error:[/red] {e}\n")
        raise typer.Exit(1)

    total_models = sum(len(r.active_models) for r in cfg.rounds)
    _header("ask")
    err.print(f"  [dim]Question:[/dim] {question}")
    err.print(f"  [dim]Rounds  :[/dim] {len(cfg.rounds)}{' + critique' if deep else ''}")
    err.print(f"  [dim]Models  :[/dim] {total_models} across all rounds")

    mem = estimate_ollama_memory(cfg)
    if mem["peak_bytes"] > 0:
        peak_gb = mem["peak_bytes"] / 1024 ** 3
        err.print(f"  [dim]Ollama RAM:[/dim] ~{peak_gb:.1f} GB peak (models run in parallel per round)")
    if mem["warning"]:
        err.print(f"  [yellow]⚠  {mem['warning']}[/yellow]")
    err.print()

    try:
        all_rounds, final_text, synthesis_results = asyncio.run(_main(question, cfg, deep))
    except KeyboardInterrupt:
        from .wizard import exit_message
        err.print()
        err.print(f"[dim]  {exit_message()}[/dim]")
        err.print()
        raise typer.Exit(130)
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
            (round_dir / f"{fname}.md").write_text(r.content or "", encoding="utf-8")
            if r.error:
                (round_dir / f"{fname}.err").write_text(r.error, encoding="utf-8")

    final_round_dir = run_dir / f"round_{len(all_rounds)}_{cfg.rounds[-1].name or 'final'}"
    final_round_dir.mkdir(exist_ok=True)
    for r in synthesis_results:
        safe = r.model_id.replace("/", "_").replace(":", "_")
        role_safe = r.role.replace(" ", "_").replace("'", "")
        (final_round_dir / f"{safe}__{role_safe}.md").write_text(r.content or "", encoding="utf-8")

    output_file = run_dir / "decision.md"
    output_file.write_text(final_text, encoding="utf-8")

    # Snapshot the config alongside the run for exact re-runs
    cfg_toml = config_to_toml(cfg)
    (run_dir / "config.toml").write_text(cfg_toml, encoding="utf-8")

    # Persist to SQLite
    from .db import save_run as db_save_run
    db_rounds = []
    for rr in all_rounds:
        db_rounds.append({
            "round_index": rr.round_index,
            "name": rr.round_name,
            "outputs": [
                {
                    "model_id": r.model_id,
                    "role": r.role,
                    "auth": "api",
                    "content_md": r.content,
                    "error_msg": r.error,
                    "elapsed_ms": None,
                }
                for r in rr.results
            ],
        })
    try:
        db_save_run(
            question=question,
            config_toml=cfg_toml,
            decision_md=final_text,
            run_dir=str(run_dir.absolute()),
            rounds=db_rounds,
        )
    except Exception:
        pass  # DB failure never breaks a completed run

    abs_file = output_file.absolute()
    abs_dir = run_dir.absolute()

    err.print()
    err.print(Rule("[bold green]Done[/bold green]"))
    err.print(f"  [green]Decision :[/green] {abs_file}")
    err.print(f"  [dim]Run dir  : {abs_dir}[/dim]")
    err.print()


@app.command()
def init(
    output: Path = typer.Option(Path("dissenter.toml"), "--output", "-o", help="Config file to create"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite without prompting"),
    save: Optional[str] = typer.Option(None, "--save", "-s", help="Save as a named preset (~/.config/dissenter/<name>.toml)"),
    auto: bool = typer.Option(False, "--auto", help="Auto-generate config from local Ollama models (no wizard)"),
    rounds: int = typer.Option(1, "--rounds", "-r", help="Number of debate rounds (used with --auto)"),
    memory: Optional[float] = typer.Option(None, "--memory", "-m", help="RAM budget in GB per round (used with --auto)"),
) -> None:
    """Create a config file interactively, or auto-generate from local Ollama models.

    Examples:
      dissenter init                         # interactive wizard → dissenter.toml
      dissenter init --save fast             # wizard → ~/.config/dissenter/fast.toml
      dissenter init --auto                  # auto-detect all Ollama models
      dissenter init --auto --memory 8       # fit models within 8 GB per round
      dissenter init --auto --rounds 2 --memory 16 --save deep
    """
    _header("init")
    from .wizard import run_auto_wizard, run_wizard
    if auto:
        run_auto_wizard(output, save, rounds, memory, err)
    else:
        run_wizard(output, force, save, err)


@app.command()
def history(
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Filter by keyword in question or decision text"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows to show (default: 20)"),
    clear: bool = typer.Option(False, "--clear", help="Delete all run history from the database"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation when using --clear"),
) -> None:
    """Browse past decisions, or clear the history database.

    Every `dissenter ask` run is saved automatically. Use this command to
    browse, search, or open any past decision interactively.

    Examples:
      dissenter history                   # browse all past runs
      dissenter history --search kafka    # filter by keyword
      dissenter history --limit 5         # show only 5 most recent
      dissenter history --clear           # delete all history (prompts first)
      dissenter history --clear --yes     # delete without prompting
    """
    _header("history")

    if clear:
        from .db import get_db_path
        db_path = get_db_path()
        if not db_path.exists():
            out.print("[dim]No database found — nothing to clear.[/dim]")
            return
        if not yes:
            typer.confirm(f"Delete all run history from {db_path}?", abort=True)
        db_path.unlink()
        out.print(f"[green]✓[/green] Cleared: {db_path}")
        return

    from .db import get_run, list_runs

    runs = list_runs(limit=limit, search=search)
    if not runs:
        msg = f"No decisions found matching '{search}'." if search else "No decisions yet. Run `dissenter ask` to get started."
        out.print(f"[dim]{msg}[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", width=19)
    table.add_column("Question")
    for i, run in enumerate(runs, 1):
        table.add_row(str(i), run["timestamp"], run["question"])

    out.print()
    out.print(table)
    out.print()

    raw = typer.prompt("Enter number to view decision, or press Enter to quit", default="")
    if not raw.strip():
        return
    try:
        idx = int(raw.strip()) - 1
        selected = runs[idx]
    except (ValueError, IndexError):
        out.print("[red]Invalid selection.[/red]")
        return

    run = get_run(selected["id"])
    if run:
        out.print()
        out.print(Rule(f"[bold]Decision #{selected['id']}[/bold]  [dim]{selected['timestamp']}[/dim]"))
        out.print(run["decision_md"])
        if run.get("run_dir"):
            p = Path(run["run_dir"])
            out.print()
            out.print(f"[dim]Run dir: [link=file://{p}]{p}[/link][/dim]")
            cfg_file = p / "config.toml"
            if cfg_file.exists():
                out.print(f"[dim]Re-run:  dissenter ask \"...\" --config {cfg_file}[/dim]")
    out.print()


@app.command()
def uninstall(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Remove all dissenter app data (database + config presets) from this machine.

    Deletes the SQLite history database and any named config presets saved
    under ~/.config/dissenter/. Does not remove the package itself — for
    that, run: uv tool uninstall dissenter

    Examples:
      dissenter uninstall        # lists what will be deleted, then prompts
      dissenter uninstall --yes  # skip confirmation
    """
    _header("uninstall")
    import shutil
    from platformdirs import user_config_dir, user_data_dir

    # Deduplicate — on Mac/Windows data and config dirs are the same path
    paths = list(dict.fromkeys([
        Path(user_data_dir("dissenter")),
        Path(user_config_dir("dissenter")),
    ]))

    out.print("\nThis will permanently delete:")
    for p in paths:
        out.print(f"  [bold]{p}[/bold]")
    out.print("\nTo also remove the package:")
    out.print("  [dim]uv tool uninstall dissenter[/dim]  or  [dim]pip uninstall dissenter[/dim]\n")

    if not yes:
        typer.confirm("Proceed?", abort=True)

    removed = []
    for p in paths:
        if p.exists():
            shutil.rmtree(p)
            removed.append(str(p))

    if removed:
        for r in removed:
            out.print(f"[green]✓[/green] Removed: {r}")
    else:
        out.print("[dim]Nothing to remove.[/dim]")


@app.command()
def models() -> None:
    """Show detected local models, CLI tools, and API key env var status.

    Useful for verifying what dissenter can see before running `dissenter init`
    or `dissenter ask`.

    Examples:
      dissenter models
    """
    _header("models")
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
def config(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path or named preset to inspect (default: dissenter.toml)"),
) -> None:
    """Inspect the active config — rounds, models, roles, auth.

    Loads and pretty-prints the configuration that `dissenter ask` would use,
    as a tree. Useful for verifying a config before running a debate.

    Examples:
      dissenter config                        # inspect dissenter.toml in current dir
      dissenter config --config fast          # inspect named preset
      dissenter config --config path/to.toml  # inspect specific file
    """
    _header("config")
    try:
        cfg = load_config(config_path)
    except FileNotFoundError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    tree = Tree(f"[bold]dissenter[/bold]  [dim]{cfg.output_dir}[/dim]")
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


async def _main(question: str, cfg: DissentConfig, deep: bool = False):
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.text import Text

    err.print(Rule("[dim]beginning debate[/dim]", style="dim"))
    all_rounds = await run_all_rounds(cfg, question, deep=deep)

    err.print()
    err.print(Rule("[dim]synthesizing[/dim]", style="dim"))
    err.print()

    from .wizard import synthesis_message

    task = asyncio.create_task(synthesize(question, all_rounds, cfg))
    spinner = Spinner("dots", text=Text(f" {synthesis_message()}", style="dim"))
    with Live(spinner, console=err, refresh_per_second=10) as live:
        while not task.done():
            spinner.text = Text(f" {synthesis_message()}", style="dim")
            live.update(spinner)
            await asyncio.sleep(4)
    final_text, synthesis_results = task.result()

    return all_rounds, final_text, synthesis_results
