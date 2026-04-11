from __future__ import annotations

import asyncio
import sys
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

from .update import get_update_notice, start_update_check

# Start update check in background immediately — result cached for 24h
_update_thread = start_update_check()

# Print the version rule before typer renders --help output
if "--help" in sys.argv or "-h" in sys.argv:
    _help_cmd = next((a for a in sys.argv[1:] if not a.startswith("-")), "help")
    Console(stderr=True).print(Rule(f"[bold]dissenter[/bold] [dim]v{_VERSION} — {_help_cmd}[/dim]"))
    # Print hint after Typer's help output (top-level only)
    if _help_cmd == "help":
        import atexit
        atexit.register(
            lambda: Console(stderr=True).print(
                "\n [bold green]Run 'dissenter COMMAND --help' for full details and flags on any command.[/bold green]\n"
            )
        )

from .detect import (
    KNOWN_PROVIDERS, detect_api_keys, detect_clis, detect_ollama_models,
    estimate_ollama_memory, infer_auth,
)
# runner and synthesis import litellm (~1s cold start) — lazy-loaded inside ask() only
# so that models / history / config / init are instant

app = typer.Typer(
    help=(
        "Run multiple LLMs through a structured debate for complex questions. "
        "Surface where they disagree. Synthesize a decision."
    ),
    add_completion=False,
)

out = Console()
err = Console(stderr=True)

_DEFAULT_DEBATE_ROLES = ["skeptic", "contrarian", "pragmatist", "devil's advocate", "analyst"]


def _header(cmd: str) -> None:
    err.print()
    err.print(Rule(f"[bold]dissenter[/bold] [dim]v{_VERSION} — {cmd}[/dim]"))
    notice = get_update_notice(_VERSION)
    if notice:
        err.print(f"  [yellow]↑ {notice}[/yellow]")


def _version_callback(value: bool) -> None:
    if value:
        out.print(f"dissenter v{_VERSION}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _app_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", is_eager=True, callback=_version_callback, help="Show version and exit"),
) -> None:
    if ctx.invoked_subcommand is None:
        from .tui import launch_tui
        launch_tui()


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
    context: Optional[List[Path]] = typer.Option(
        None, "--context", "-x",
        help="File(s) to inject as reference material — repeatable",
    ),
    prior: Optional[int] = typer.Option(
        None, "--prior", "-p",
        help="Decision ID from history to inject as context (see `dissenter history`)",
    ),
    ghost: bool = typer.Option(
        False, "--ghost",
        help="Run the debate but don't save anything — no files, no database entry",
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
      dissenter ask "..." --context planning-doc.md       # inject a reference file
      dissenter ask "..." --prior 3                       # inject past decision #3 as context
      dissenter ask "..." --ghost                         # run without saving anything
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

    # Pre-flight: verify credentials/availability for every model before starting
    from .validate import validate_toml
    _, preflight_errors = validate_toml(
        config_to_toml(cfg),
        detect_ollama_models(), detect_clis(), detect_api_keys(),
    )
    # Only show preflight errors (schema/sanity already passed since cfg loaded fine)
    preflight_errors = [e for e in preflight_errors if e.stage == "preflight"]
    if preflight_errors:
        err.print()
        err.print("[red]Error:[/red] Cannot start — credential issues with the following models:\n")
        for e in preflight_errors:
            err.print(f"  [red]✗[/red]  [dim]{e.message}[/dim]")
        err.print()
        err.print("  Run [bold]dissenter models[/bold] to see what's available.")
        err.print()
        raise typer.Exit(1)

    # Build user context from --context files and/or --prior decision
    user_context_parts: list[str] = []
    if context:
        for ctx_path in context:
            if not ctx_path.exists():
                err.print(f"\n[red]Error:[/red] Context file not found: {ctx_path}\n")
                raise typer.Exit(1)
            user_context_parts.append(
                f"--- {ctx_path.name} ---\n{ctx_path.read_text(encoding='utf-8').strip()}"
            )
    if prior is not None:
        from .db import get_run
        run = get_run(prior)
        if not run:
            err.print(f"\n[red]Error:[/red] No decision with ID {prior}. Run `dissenter history` to see available IDs.\n")
            raise typer.Exit(1)
        user_context_parts.append(
            f"--- Prior decision #{prior} ---\n{run['decision_md'].strip()}"
        )
    user_context = "\n\n".join(user_context_parts)

    total_models = sum(len(r.active_models) for r in cfg.rounds)
    _header("ask")
    err.print(f"  [dim]Question:[/dim] {question}")
    err.print(f"  [dim]Rounds  :[/dim] {len(cfg.rounds)}{' + critique' if deep else ''}")
    err.print(f"  [dim]Models  :[/dim] {total_models} across all rounds")
    if user_context:
        n_files = len(context or [])
        n_prior = 1 if prior is not None else 0
        parts_desc = []
        if n_files:
            parts_desc.append(f"{n_files} file{'s' if n_files != 1 else ''}")
        if n_prior:
            parts_desc.append(f"decision #{prior}")
        err.print(f"  [dim]Context :[/dim] {' + '.join(parts_desc)}")

    mem = estimate_ollama_memory(cfg)
    if mem["peak_bytes"] > 0:
        peak_gb = mem["peak_bytes"] / 1024 ** 3
        err.print(f"  [dim]Ollama RAM:[/dim] ~{peak_gb:.1f} GB peak (models run in parallel per round)")
    if mem["warning"]:
        err.print(f"  [yellow]⚠  {mem['warning']}[/yellow]")
    err.print()

    from .wizard import loading_message
    from rich.spinner import Spinner
    from rich.live import Live
    from rich.text import Text

    with Live(
        Spinner("dots", text=Text(f" {loading_message()}", style="dim")),
        console=err, refresh_per_second=10, transient=True,
    ):
        from .runner import run_all_rounds
        from .synthesis import synthesize

    try:
        all_rounds, final_text, synthesis_results, decision_name = asyncio.run(_main(question, cfg, deep, user_context))
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

    if ghost:
        # Ghost mode — print the decision but save nothing
        err.print()
        err.print(Rule("[bold green]Done[/bold green] [dim](ghost mode — nothing saved)[/dim]"))
        err.print()
        out.print(final_text)
        return

    # Save outputs — everything lives under decisions/<timestamp>_<name>/
    from .paths import ensure_dirs
    ensure_dirs()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{ts}_{decision_name}" if decision_name else ts
    run_dir = cfg.output_dir / folder_name
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
def generate(
    prompt: str = typer.Argument(..., help="Natural-language description of the config you want"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model ID for the generator (auto-picked if omitted)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Config name — saved as dissenter_<name>.toml (timestamp if omitted)"),
    retries: int = typer.Option(3, "--retries", "-r", help="Max generation attempts (default: 3)"),
) -> None:
    """Generate a config file from a natural-language prompt using an LLM.

    An available model reads your intent plus the full detected environment
    (Ollama models, CLI tools, API keys, role catalog, TOML schema) and writes
    a valid dissenter config. Validates the output through the full pipeline and
    retries with injected error context on failure.

    Examples:
      dissenter generate "fast 2-round debate with local ollama models"
      dissenter generate "claude vs gemini, skeptic and pragmatist roles"
      dissenter generate "..." --model ollama/mistral:latest
      dissenter generate "..." --output kafka-debate
    """
    _header("generate")

    ollama_models = detect_ollama_models()
    clis = detect_clis()
    api_keys = detect_api_keys()

    # Pick generator model
    from .generate import pick_generator_model, generate_config

    if model:
        extra = {"api_base": "http://localhost:11434"} if model.startswith("ollama/") else {}
        gen_model = ModelConfig(
            id=model, role="generator", timeout=120,
            auth=infer_auth(model, clis), extra=extra,
        )
    else:
        try:
            gen_model = pick_generator_model(clis, api_keys, ollama_models)
        except RuntimeError as e:
            err.print(f"\n[red]Error:[/red] {e}\n")
            raise typer.Exit(1)

    err.print(f"  [dim]Generator:[/dim] {gen_model.id} ({gen_model.auth})")
    err.print(f"  [dim]Retries  :[/dim] {retries}")
    err.print()

    from rich.spinner import Spinner
    from rich.live import Live
    from rich.text import Text
    from .wizard import loading_message

    def on_attempt(attempt: int, prev_errors):
        if attempt == 1:
            err.print(f"  [dim]Attempt {attempt}/{retries} — generating config...[/dim]")
        else:
            n_errors = len(prev_errors) if prev_errors else 0
            err.print(f"  [yellow]Attempt {attempt}/{retries} — retrying ({n_errors} error{'s' if n_errors != 1 else ''} from last attempt)[/yellow]")

    try:
        async def _run():
            return await generate_config(
                intent=prompt,
                generator_model=gen_model,
                ollama_models=ollama_models,
                clis=clis,
                api_keys=api_keys,
                max_retries=retries,
                on_attempt=on_attempt,
            )

        with Live(
            Spinner("dots", text=Text(f" {loading_message()}", style="dim")),
            console=err, refresh_per_second=10, transient=True,
        ):
            result = asyncio.run(_run())

    except RuntimeError as e:
        err.print(f"\n[red]Error:[/red] {e}\n")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        from .wizard import exit_message
        err.print(f"\n  [dim]{exit_message()}[/dim]\n")
        raise typer.Exit(130)

    # Determine output path
    if output:
        filename = f"dissenter_{output}.toml"
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dissenter_{ts}.toml"
    out_path = Path(filename)

    out_path.write_text(result.toml_str, encoding="utf-8")

    err.print()
    err.print(f"  [green]✓[/green] Config generated in {result.attempts} attempt{'s' if result.attempts != 1 else ''}")
    err.print(f"  [green]✓[/green] Saved to [bold]{out_path}[/bold]")
    err.print()

    # Show the config tree inline
    from .config import load_config as _lc
    cfg = _lc(out_path)
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

    err.print()
    err.print(f"  [dim]Run it:[/dim]  dissenter ask \"...\" --config {out_path}")
    err.print()


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
    from .paths import dissenter_home

    home = dissenter_home()

    out.print("\nThis will permanently delete:")
    out.print(f"  [bold]{home}[/bold]")
    out.print("\nTo also remove the package:")
    out.print("  [dim]uv tool uninstall dissenter[/dim]  or  [dim]pip uninstall dissenter[/dim]\n")

    if not yes:
        typer.confirm("Proceed?", abort=True)

    if home.exists():
        shutil.rmtree(home)
        out.print(f"[green]✓[/green] Removed: {home}")
    else:
        out.print("[dim]Nothing to remove.[/dim]")


@app.command()
def upgrade(
    local: bool = typer.Option(
        False, "--local", "-l",
        help="Install from current directory instead of PyPI (for development)",
    ),
) -> None:
    """Upgrade dissenter to the latest version.

    By default pulls from PyPI. Use --local to rebuild from your local source tree.

    Examples:
      dissenter upgrade              # latest from PyPI
      dissenter upgrade --local      # rebuild from cwd (dev workflow)
    """
    import subprocess
    _header("upgrade")
    err.print(f"  [dim]Current:[/dim] v{_VERSION}")
    err.print()

    if local:
        source = "."
        err.print("  [dim]Source:[/dim]  local (current directory)")
    else:
        source = "dissenter"
        err.print("  [dim]Source:[/dim]  PyPI")
    err.print()

    try:
        subprocess.run(
            ["uv", "tool", "install", source, "--force", "--no-cache"],
            check=True,
        )
    except FileNotFoundError:
        err.print("[red]Error:[/red] `uv` not found on PATH. Install it first: https://docs.astral.sh/uv/")
        raise typer.Exit(1)
    except subprocess.CalledProcessError:
        err.print(f"[red]Error:[/red] Upgrade failed. Try manually: uv tool install {source} --force --no-cache")
        raise typer.Exit(1)
    err.print()
    err.print("  [green]✓[/green] Upgraded. Run [bold]dissenter --version[/bold] to confirm.")
    err.print()


@app.command()
def benchmark(
    dataset: Path = typer.Argument(
        ..., help="Path to a JSONL dataset file (see datasets/test-mini.jsonl)"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Debate config (TOML or named preset)"
    ),
    output: Path = typer.Option(
        Path("results.json"), "--output", "-o", help="Where to write the results JSON"
    ),
    limit: int = typer.Option(
        0, "--limit", "-n", help="Run only the first N questions (0 = all)"
    ),
    deep: bool = typer.Option(
        False, "--deep", help="Inject a mutual critique round before synthesis"
    ),
    baseline: Optional[str] = typer.Option(
        None, "--baseline",
        help="Skip the debate: 'single' (one model) or 'majority' (one model × N)",
    ),
    majority_n: int = typer.Option(
        3, "--majority-n",
        help="Number of samples for --baseline majority",
    ),
) -> None:
    """Run a benchmark dataset through the debate pipeline and report accuracy.

    Dataset format: JSONL, one question per line, with keys
    id / type (mcq|numeric|code) / question / answer / choices (mcq only) / metadata.

    Examples:
      dissenter benchmark datasets/test-mini.jsonl
      dissenter benchmark datasets/gpqa_diamond.jsonl -c bench.toml -n 10 --deep
      dissenter benchmark datasets/test-mini.jsonl -o results/mini.json
    """
    import asyncio
    from dissenter.benchmark import run_benchmark

    _header("benchmark")

    if not dataset.exists():
        err.print(f"[red]Error:[/red] dataset not found: {dataset}")
        raise typer.Exit(1)

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        err.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    mode = baseline or "dissenter"
    if mode not in ("dissenter", "single", "majority"):
        err.print(f"[red]Error:[/red] --baseline must be 'single' or 'majority', got '{baseline}'")
        raise typer.Exit(1)

    err.print(f"  [dim]Dataset:[/dim] {dataset}")
    err.print(f"  [dim]Config:[/dim]  {config or 'dissenter.toml'}")
    err.print(f"  [dim]Output:[/dim]  {output}")
    err.print(f"  [dim]Mode:[/dim]    {mode}" + (f" (n={majority_n})" if mode == "majority" else ""))
    if limit:
        err.print(f"  [dim]Limit:[/dim]   {limit} questions")
    if deep and mode == "dissenter":
        err.print(f"  [dim]Deep:[/dim]    + critique round")
    err.print()

    def _progress(i: int, total: int, qr) -> None:
        if qr.error:
            status = "[yellow]![/yellow]"
            detail = qr.error[:60]
        elif qr.correct:
            status = "[green]✓[/green]"
            detail = f"pred={qr.predicted} truth={qr.ground_truth}"
        else:
            status = "[red]✗[/red]"
            detail = f"pred={qr.predicted} truth={qr.ground_truth}"
        err.print(f"  [{i}/{total}] {status} {qr.id}: {detail}  [dim]({qr.latency_s:.1f}s)[/dim]")

    config_label = config.stem if config else (cfg.rounds[-1].models[0].id if cfg.rounds else "default")

    result = asyncio.run(
        run_benchmark(
            dataset_path=dataset,
            cfg=cfg,
            output_path=output,
            limit=limit,
            deep=deep,
            mode=mode,
            majority_n=majority_n,
            config_label=str(config_label),
            progress=_progress,
        )
    )

    err.print()
    err.print(Rule())
    err.print(f"  [bold]Accuracy:[/bold] {result.correct}/{result.total} ({result.accuracy:.1%})")
    err.print(f"  [bold]Errors:[/bold]   {result.errors}")
    err.print(f"  [bold]Time:[/bold]     {result.total_latency_s:.1f}s ({result.total_latency_s / max(1, result.total):.1f}s/question)")
    err.print()
    err.print(f"  [dim]Results:[/dim] {output}")
    err.print()


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


async def _main(question: str, cfg: DissentConfig, deep: bool = False, user_context: str = ""):
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.text import Text
    from .runner import run_all_rounds
    from .synthesis import synthesize

    err.print(Rule("[dim]beginning debate[/dim]", style="dim"))
    all_rounds = await run_all_rounds(cfg, question, deep=deep, user_context=user_context)

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

    # Generate a single-word name for the decision folder
    from .synthesis import name_decision
    import random
    final_round = cfg.rounds[-1]
    active = final_round.active_models
    naming_model = random.choice(active)
    decision_name = await name_decision(question, final_text, naming_model)

    return all_rounds, final_text, synthesis_results, decision_name
