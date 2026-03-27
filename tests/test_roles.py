from __future__ import annotations

from dissenter.roles import get_prompt, load_roles

EXPECTED_ROLES = [
    "devil's advocate",
    "pragmatist",
    "skeptic",
    "contrarian",
    "researcher",
    "analyst",
    "second opinion",
    "chairman",
    "conservative",
    "liberal",
]


def test_all_roles_loaded():
    roles = load_roles()
    for role in EXPECTED_ROLES:
        assert role in roles, f"Role '{role}' not found in loaded roles"


def test_role_prompts_non_empty():
    roles = load_roles()
    for name, prompt in roles.items():
        assert prompt.strip(), f"Role '{name}' has empty prompt"


def test_unknown_role_falls_back():
    prompt = get_prompt("nonexistent role xyz")
    assert len(prompt) > 10  # returns fallback analyst prompt


def test_known_role_returns_correct_prompt():
    roles = load_roles()
    prompt = get_prompt("chairman", roles)
    assert "chairman" in prompt.lower() or "synthesize" in prompt.lower() or "decisive" in prompt.lower()


def test_devil_advocate_prompt_content():
    roles = load_roles()
    prompt = roles["devil's advocate"]
    assert "devil" in prompt.lower()
