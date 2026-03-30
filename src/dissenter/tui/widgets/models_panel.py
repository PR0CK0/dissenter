"""Models panel — displays detected Ollama models, CLI tools, and API key status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


class ModelsPanel(Static):
    """Displays detected Ollama models, CLI tools, and API key status."""

    def on_mount(self) -> None:
        from dissenter.detect import (
            KNOWN_PROVIDERS,
            detect_api_keys,
            detect_clis,
            detect_ollama_models,
        )

        ollama = detect_ollama_models()
        clis = detect_clis()
        api_keys = detect_api_keys()

        lines: list[str] = []

        # Ollama
        lines.append("[bold]Ollama (local)[/bold]")
        if ollama:
            for m in ollama:
                lines.append(f"  [green]✓[/green]  {m}")
        else:
            lines.append("  [dim]no models — is ollama running? try: ollama pull mistral[/dim]")

        # CLI tools
        lines.append("")
        lines.append("[bold]CLI tools[/bold]")
        for cli, path in clis.items():
            if path:
                lines.append(f"  [green]✓[/green]  {cli:<10} [dim]{path}[/dim]")
            else:
                lines.append(f"  [dim]✗  {cli}   not found[/dim]")

        # API providers
        lines.append("")
        lines.append("[bold]API providers[/bold]")
        for provider, env_var in KNOWN_PROVIDERS.items():
            has_key = api_keys[provider]
            tick = "[green]✓[/green]" if has_key else "[dim]✗[/dim]"
            note = "[green]key set[/green]" if has_key else f"[dim]export {env_var}[/dim]"
            lines.append(f"  {tick}  {provider:<18} {note}")

        self.update("\n".join(lines))
