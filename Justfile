set windows-shell := ["cmd", "/c"]

# Run a debate
ask question:
    uv run dissenter ask "{{question}}"

# Run with local Ollama models only (no API keys needed)
ask-local question:
    uv run dissenter ask "{{question}}" --config dissenter-test.toml

# Auto-detect installed Ollama models and run immediately
quick question:
    uv run dissenter ask "{{question}}" --quick

# Interactive setup wizard
init:
    uv run dissenter init

# Save a named config preset (~/.config/dissenter/<name>.toml)
init-save name:
    uv run dissenter init --save {{name}}

# Auto-generate config from local Ollama models (optional: memory=8 rounds=2)
init-auto memory="" rounds="1":
    uv run dissenter init --auto {{ if memory != "" { "--memory " + memory } else { "" } }} --rounds {{rounds}}

# Show detected models, CLIs, and API key status
models:
    uv run dissenter models

# Show current config (rounds, models, roles)
show:
    uv run dissenter show

# Browse past decisions
history:
    uv run dissenter history

# Search past decisions
search term:
    uv run dissenter history --search "{{term}}"

# Delete all run history
clear:
    uv run dissenter clear

# Remove all app data from this machine
uninstall:
    uv run dissenter uninstall

# Run test suite
test:
    uv run pytest tests/ -v

# Install dependencies into local .venv
install:
    uv sync

# Install dissenter globally so `dissenter` works anywhere without `uv run`
global-install:
    uv tool install .
