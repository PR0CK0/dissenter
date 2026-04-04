from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.message import Message
from textual.widgets import Static, ListView, ListItem, Label


class SidebarItem(ListItem):
    """A clickable sidebar navigation item."""

    def __init__(
        self,
        label: str,
        item_type: str,
        item_data: dict | None = None,
        classes: str = "",
    ) -> None:
        super().__init__(classes=classes)
        self.item_label = label
        self.item_type = item_type
        self.item_data = item_data or {}

    def compose(self) -> ComposeResult:
        yield Label(self.item_label)


class Sidebar(Container):
    """Left navigation sidebar with sections for New, History, and Environment."""

    class Selected(Message):
        """Emitted when a sidebar item is clicked."""

        def __init__(self, item_type: str, data: dict | None = None) -> None:
            super().__init__()
            self.item_type = item_type
            self.data = data or {}

    def compose(self) -> ComposeResult:
        yield ListView(
            SidebarItem("Home", "home", classes="sidebar-item"),
            id="nav-home",
            classes="sidebar-list",
        )
        yield Static("NEW", classes="sidebar-section-header")
        yield ListView(
            SidebarItem("Ask a question", "ask", classes="sidebar-item"),
            SidebarItem("Create config", "create-config", classes="sidebar-item"),
            # TODO: re-add when AI config generation is implemented
            # SidebarItem("Generate config (AI)", "generate", classes="sidebar-item"),
            id="nav-new",
            classes="sidebar-list",
        )
        yield Static("HISTORY", classes="sidebar-section-header")
        yield ListView(
            SidebarItem("View all history", "history", classes="sidebar-item"),
            id="nav-history-link",
            classes="sidebar-list",
        )
        yield VerticalScroll(id="history-container", classes="sidebar-history")
        yield Static("ENVIRONMENT", classes="sidebar-section-header")
        yield ListView(
            SidebarItem("Models & keys", "models", classes="sidebar-item"),
            SidebarItem("Saved configs", "configs-list", classes="sidebar-item"),
            id="nav-env",
            classes="sidebar-list",
        )

    async def on_mount(self) -> None:
        await self.refresh_history()

    async def refresh_history(self) -> None:
        """Reload history items from the database."""
        # Lazy import to avoid pulling in heavy deps at import time
        from dissenter.db import list_runs

        container = self.query_one("#history-container", VerticalScroll)
        await container.remove_children()

        try:
            runs = list_runs(limit=10)
        except Exception:
            runs = []

        if not runs:
            await container.mount(Static("No decisions yet", classes="sidebar-muted"))
            return

        items: list[SidebarItem] = []
        for run in runs:
            ts = run.get("timestamp", "")
            date_part = ts[:10] if len(ts) >= 10 else ts
            question = run.get("question", "")
            truncated = question[:40] + ("..." if len(question) > 40 else "")
            label = f"{date_part}  {truncated}"
            items.append(
                SidebarItem(
                    label,
                    "decision",
                    item_data={"run_id": run["id"]},
                    classes="sidebar-item sidebar-history-item",
                )
            )

        history_list = ListView(*items, id="nav-history", classes="sidebar-list")
        await container.mount(history_list)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Forward list item selection as a Sidebar.Selected message."""
        item = event.item
        if isinstance(item, SidebarItem):
            # Clear highlight from all OTHER ListViews so only one is active
            source_list = event.list_view
            for lv in self.query(ListView):
                if lv is not source_list:
                    lv.index = None
            self.post_message(self.Selected(item.item_type, item.item_data))
