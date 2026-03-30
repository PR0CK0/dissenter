"""Config tree — tree view of the active dissenter configuration."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Tree


class ConfigTree(Tree):
    """Tree view of the active dissenter config."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("dissenter", *args, **kwargs)

    def load_config(self, path: Path | None = None) -> None:
        from dissenter.config import load_config

        self.clear()

        try:
            cfg = load_config(path)
        except FileNotFoundError:
            self.root.set_label("[dim]No config found[/dim]")
            return

        self.root.set_label(f"[bold]dissenter[/bold]  [dim]{cfg.output_dir}[/dim]")

        for i, round_cfg in enumerate(cfg.rounds):
            label = f"Round {i + 1}: [cyan]{round_cfg.name or '(unnamed)'}[/cyan]"
            if i == len(cfg.rounds) - 1:
                label += "  [yellow][final][/yellow]"
            r_node = self.root.add(label)
            for m in round_cfg.models:
                status = "[green]✓[/green]" if m.enabled else "[dim]—[/dim]"
                r_node.add_leaf(
                    f"{status} [bold]{m.id}[/bold]  [dim]role:[/dim] {m.role}  "
                    f"[dim]auth:[/dim] {m.auth}  [dim]timeout:[/dim] {m.timeout}s"
                )
            if round_cfg.combine_model:
                r_node.add_leaf(f"[dim]combine via:[/dim] {round_cfg.combine_model}")

        if cfg.role_distribution:
            dist_node = self.root.add("[dim]Role distribution[/dim]")
            for role, weight in cfg.role_distribution.items():
                dist_node.add_leaf(f"{role}: {weight:.0%}")

        self.root.expand_all()
