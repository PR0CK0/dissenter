# Pinned benchmark configs

These configs are **pinned and committed** — unlike the working
`dissenter.toml` in the repo root or configs under `~/Documents/dissenter/configs/`,
these are meant for reproducible benchmark runs. Do not edit an existing
config after it has been used for a paper run; add a new one instead.

## Conventions

- Filename: `bench-<identifier>.toml`
- `identifier` describes the model pool, e.g. `ministral-baseline`, `claude-sonnet`, `mixed-frontier`
- Every config must specify `output_dir = "decisions/benchmark"` so benchmark runs
  don't pollute the normal decisions folder

## Current configs

| Config | Description | API keys needed |
|--------|-------------|-----------------|
| `bench-ministral-baseline.toml` | ministral-3:3b × 3 (liberal + conservative → chairman) | None (local ollama) |

## Adding a frontier config

When you have API keys set up, add configs like:

```toml
# configs/bench-claude-sonnet.toml
output_dir = "decisions/benchmark"

[[rounds]]
name = "debate"

[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "liberal"
auth = "cli"

[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "conservative"
auth = "cli"

[[rounds]]
name = "final"

[[rounds.models]]
id      = "anthropic/claude-sonnet-4-6"
role    = "chairman"
auth    = "cli"
timeout = 300
```

## Running a benchmark

```bash
dissenter benchmark datasets/test-mini.jsonl \
  -c configs/bench-ministral-baseline.toml \
  -o results/test-mini-ministral.json
```
