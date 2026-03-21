from __future__ import annotations

import tomllib
from pathlib import Path

_ROLES_DIR = Path(__file__).parent / "roles"

_FALLBACK_PROMPT = (
    "Your role is balanced analyst. Be rigorous and cite specific trade-offs "
    "with concrete numbers and real-world examples where possible."
)


def load_roles() -> dict[str, str]:
    """Return mapping of role name → prompt text, loaded from roles/*.toml."""
    roles: dict[str, str] = {}
    for path in _ROLES_DIR.glob("*.toml"):
        data = tomllib.loads(path.read_text())
        name = data.get("name", path.stem)
        prompt = data.get("prompt", _FALLBACK_PROMPT)
        roles[name] = prompt
    return roles


def get_prompt(role: str, roles: dict[str, str] | None = None) -> str:
    """Return the prompt for a role, falling back to analyst if unknown."""
    if roles is None:
        roles = load_roles()
    return roles.get(role, _FALLBACK_PROMPT)
