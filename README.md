# dissenter

[![PyPI version](https://img.shields.io/pypi/v/dissenter)](https://pypi.org/project/dissenter/)
[![Python](https://img.shields.io/pypi/pyversions/dissenter)](https://pypi.org/project/dissenter/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Build](https://img.shields.io/github/actions/workflow/status/PR0CK0/dissenter/publish.yml?label=publish)](https://github.com/PR0CK0/dissenter/actions/workflows/publish.yml)
[![LiteLLM](https://img.shields.io/badge/powered%20by-LiteLLM-blueviolet)](https://docs.litellm.ai/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![LLMs](https://img.shields.io/badge/LLMs-Ollama%20%7C%20Claude%20%7C%20Gemini%20%7C%20Codex-ff6f00)](https://docs.litellm.ai/docs/providers)

**Run multiple LLMs through a structured debate for complex questions. Surface where they disagree. Synthesize a decision.**

```bash
dissenter                    # launch the TUI
dissenter ask "Should I use Kafka or a Postgres outbox pattern?"  # CLI mode
```

---

## Table of Contents

- [Quick start](#quick-start)
- [Terminal UI](#terminal-ui)
- [Why this exists](#why-this-exists)
- [What the existing tools get wrong](#what-the-existing-tools-get-wrong)
- [What dissenter does differently](#what-dissenter-does-differently)
- [Architecture](#architecture)
- [Installation](#installation)
- [CLI Commands](#cli-commands)
- [Configuration](#configuration)
  - [Minimal config](#minimal-config)
  - [Multi-round](#multi-round)
  - [Dual-arbiter final](#dual-arbiter-final)
  - [CLI auth — no API keys](#cli-auth--no-api-keys)
  - [Same model, multiple roles](#same-model-multiple-roles)
  - [Per-model API key](#per-model-api-key)
- [Roles](#roles)
- [Output](#output)
- [Testing](#testing)
- [Comparison](#comparison)
- [Academic foundations](#academic-foundations)
- [Roadmap](#roadmap)

---

## Quick start

```bash
# Install
uv tool install dissenter

# Option A: launch the TUI (interactive, no flags needed)
dissenter

# Option B: one-shot CLI
dissenter ask "Should I use Kafka or a Postgres outbox?"

# Option C: fully local, no API keys
ollama serve
dissenter ask "..." --quick
```

---

## Terminal UI

**v3.0.0** introduces a full terminal UI built with [Textual](https://textual.textualize.io/). Run `dissenter` with no arguments to launch it.

```
┌──────────────────────────────────────────────────────────────┐
│  dissenter v3.0.0                                            │
├───────────────────┬──────────────────────────────────────────┤
│                   │                                          │
│  NEW              │  Welcome to dissenter                    │
│  ───              │  Run multiple LLMs through structured    │
│  ▸ Ask a question │  debate. Surface where they disagree.    │
│  ▸ Generate config│  Synthesize a decision.                  │
│                   │                                          │
│  HISTORY          │  Past decisions:  12                     │
│  ───────          │  Available models: 14                    │
│  ▸ 03-28 Kafka..  │                                          │
│  ▸ 03-27 Redis..  │  Press n to ask a question               │
│  ▸ 03-26 K8s..   │  Press g to generate a config            │
│                   │  Press ? for help                        │
│  ENVIRONMENT      │                                          │
│  ───────────      │                                          │
│  ▸ Models & keys  │                                          │
│  ▸ Active config  │                                          │
│                   │                                          │
├───────────────────┴──────────────────────────────────────────┤
│  n Ask  g Generate  h History  q Quit  ? Help                │
└──────────────────────────────────────────────────────────────┘
```

### TUI views

| View | How to get there | What it shows |
|------|-----------------|---------------|
| **Home** | Launch `dissenter` | Quick stats, keyboard shortcuts |
| **Ask** | Press `n` | Question input, config selector, context files, `--deep` toggle, Start button |
| **Debate progress** | Press Start | Loading animation with rotating thematic messages, then the ADR in a markdown viewer |
| **History** | Press `h` or click a sidebar history item | DataTable of all past runs — click any to view the full decision |
| **Decision viewer** | Click a history row | Full ADR rendered as markdown, with Continue / Re-run / Back buttons |
| **Models & keys** | Click "Models & keys" in sidebar | Detected Ollama models, CLI tools, API key status |
| **Config** | Click "Active config" in sidebar | Tree view of the loaded config (rounds, models, roles, auth) |
| **Generate** | Press `g` | Natural-language prompt input for LLM-powered config generation |

### TUI keybindings

| Key | Action |
|-----|--------|
| `n` | New debate (ask form) |
| `g` | Generate config |
| `h` | History browser |
| `q` | Quit |
| `?` | Help |
| `Escape` | Back (from debate screen) |

The TUI and CLI share the same engine. All CLI commands still work for scripting and CI — the TUI is an interactive layer on top.

---

## Why this exists

There are already tools that aggregate multiple LLMs for consensus answers. This is not that.

Every existing tool — [llm-council](https://github.com/karpathy/llm-council), [llm-consortium](https://github.com/irthomasthomas/llm-consortium), [consilium](https://github.com/terry-li-hm/consilium), the reference implementations of [Mixture of Agents](https://github.com/togethercomputer/MoA) — is trying to build a better oracle. They treat disagreement as noise to eliminate and convergence as success.

For architectural decisions, that's exactly backwards.

**When multiple expert models disagree, that disagreement tells you where the decision is genuinely hard and context-dependent.** That's not noise — it's the most useful information you can get. A tool that eliminates it to produce confident-sounding consensus is actively hiding the difficulty of your decision.

`dissenter` treats disagreement as the signal, not the problem.

---

## What the existing tools get wrong

### They use identical prompts for all models
Sending the same neutral question to five models gets you five statistically similar answers with slight variation. You're not extracting diverse perspectives — you're sampling noise from similar training distributions. The February 2025 LLM ensemble survey (arXiv 2502.18036) found this is the primary reason naive ensembles underperform.

### They chase consensus
The goal of arbiter/judge patterns in llm-council, consilium, and llm-consortium is to produce a single authoritative answer. For architectural decisions — which involve trade-offs specific to *your* team, stack, and constraints — false consensus is worse than acknowledged uncertainty. The models don't know your system. The arbiter doesn't know your team.

### They're stateless
No tool persists your decisions. You can't ask "given we chose Kafka three months ago, how does that change this?" Every query is context-free. Architectural decisions form a causal chain; these tools treat each one as an isolated question.

### They depend on OpenRouter or require specific infrastructure
llm-consortium is a plugin for Simon Willison's `llm` tool. consilium requires a Rust binary. MoA reference implementations need TogetherAI. None mix cloud and local models cleanly without a proxy service.

### They require API keys for every model
Every tool assumes you're accessing models via API key. If you have a `claude` CLI or `gemini` CLI installed and authenticated, that credential is invisible to them — you still need a separate API key.

---

## What dissenter does differently

### 1. Multi-round debate with context passing

Models run in parallel within each round. Each subsequent round receives all prior rounds as context. A typical pipeline:

- **Round 1 (debate):** Any number of models argue from adversarial roles in parallel
- **Round 2 (refine):** A smaller panel reviews the debate and sharpens the analysis
- **Final round:** 1 chairman synthesizes into a decisive ADR, or 2 arbiters (conservative + liberal) produce side-by-side recommendations

Round depth is arbitrary. Configure as many rounds as the decision warrants.

### 2. Role-differentiated prompting

Rather than asking all models the same neutral question, each model is assigned an adversarial role with a distinct mandate. The research backing: the "Rethinking MoA" paper (OpenReview 2025) found that diversity of *framing* produces better results than diversity of *model*. You get more useful signal from one model asked with five different stances than five models asked the same way.

### 3. Roles as external files

Role prompts are not hardcoded. They live in `src/dissenter/roles/*.toml` — plain text files you can read and edit. Add a new file, get a new role. No code changes required.

### 4. Dual-arbiter output

The final round can use 2 models instead of 1. A `conservative` arbiter recommends the safest proven path; a `liberal` arbiter recommends the boldest high-upside path. A `combine_model` merges them side-by-side into a single document. Useful when the right answer genuinely depends on your team's risk tolerance.

### 5. Disagreement is the output, not the problem

The synthesized ADR has a dedicated **Disagreements** section — a structured analysis of where models converged, where they diverged, and what specific context would resolve the disagreement. A **Confidence Signals** table shows each model's self-reported certainty (1–10) and what would flip their recommendation — giving the chairman (and you) a calibrated picture of where the debate is genuinely uncertain.

### 6. Two auth modes: API key or CLI session

Every model can use either an API key **or** the authentication from an installed CLI tool — per model, mixed freely in the same config. If you have `claude` and `gemini` CLIs installed and logged in, dissenter works with zero API key configuration.

### 7. No OpenRouter dependency, genuine provider heterogeneity

Uses [LiteLLM](https://docs.litellm.ai/) directly — a unified interface to 100+ providers. Cloud, local, and CLI-authenticated models all participate in the same ensemble.

### 8. Context injection — reference files and prior decisions

Inject planning documents, specs, RFCs, or prior decisions as context for all debate models. Use `--context <file>` for files or `--prior <id>` to pull a past decision from the SQLite database. Decisions form a causal chain — each new debate can build on previous ones.

### 9. LLM-powered config generation

`dissenter generate "describe what you want"` uses an LLM to write a valid config from natural language. The generator sees your full environment (detected models, CLI tools, API keys), the role catalog, and the TOML schema — then validates the output and retries with injected error context on failure.

---

## Architecture

```mermaid
flowchart TD
    Q([Question]) --> CFG[Load dissenter.toml]
    CFG --> R1

    subgraph R1["Round 1: debate (parallel)"]
        M1[Model A\ndevil's advocate]
        M2[Model B\npragmatist]
        M3[Model C\nskeptic]
    end

    R1 --> CTX1[Collect outputs\n+ build context]
    CTX1 --> R2

    subgraph R2["Round 2: refine (parallel)"]
        M4[Model D\nanalyst]
        M5[Model E\ncontrarian]
    end

    R2 --> CTX2[Collect outputs\n+ build context]
    CTX2 --> FINAL

    subgraph FINAL["Final Round (1 or 2 models)"]
        direction LR
        CHAIR["1 model\nchairman → ADR"]
        OR["or"]
        CON["conservative"]
        LIB["liberal"]
        CON --> COMBINE[combine_model\nside-by-side MD]
        LIB --> COMBINE
    end

    FINAL --> OUT[decisions/<timestamp>/decision.md]
```

---

## Installation

Requires [uv](https://docs.astral.sh/uv/).

**Option A — install from PyPI (recommended):**
```bash
uv tool install dissenter    # puts `dissenter` on PATH everywhere
```

**Option B — from source:**
```bash
git clone https://github.com/PR0CK0/dissenter
cd dissenter
just global-install          # installs globally via uv tool
# or: just install           # local .venv only (use `uv run dissenter ...`)

# Set up your config
cp dissenter.example.toml dissenter.toml   # Mac/Linux
copy dissenter.example.toml dissenter.toml # Windows
# Edit dissenter.toml to match your models and API keys
```

`uv tool install` automatically adds `dissenter` to your PATH on all platforms.

`dissenter.toml` is gitignored since it may contain API keys. `dissenter.example.toml` is the committed template — copy and customise it. For shared team configs, use named presets (`dissenter init --save <name>`).

**Choose your auth method — mix freely per model:**

**Option A — CLI auth (no API keys needed)**
If you have `claude` and/or `gemini` CLIs installed and logged in, set `auth = "cli"` in your config. Done.

**Option B — API keys**
```bash
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...          # or GOOGLE_API_KEY
export GROQ_API_KEY=...            # optional, free tier
export PERPLEXITY_API_KEY=...      # optional, web-search grounding
```

**Option C — fully local, no credentials**
```bash
ollama pull ministral-3:3b
ollama serve
dissenter ask "..." --config dissenter-test.toml
```

---

## CLI Commands

All CLI commands work alongside the TUI. Use the CLI for scripting, CI, and one-shot queries. Use the TUI for interactive exploration.

`dissenter --version` (or `-v`) prints the installed version.

### `dissenter` (no args)

Launch the interactive terminal UI. Browse history, start debates, view decisions, inspect models and config — all from a single screen.

### `dissenter ask`

Run a debate and save the decision.

| Flag | Description |
|------|-------------|
| _(no flags)_ | Load `dissenter.toml` from the current directory |
| `--config <path\|name>` | Path to a TOML file, or a named preset (`~/.config/dissenter/<name>.toml`) |
| `--quick` | Auto-detect all installed Ollama models and run immediately |
| `--model <id[@role]>` | Add a model inline — repeatable, bypasses config file |
| `--chairman <id>` | Set the final-round chairman when using `--model` |
| `--output <dir>` | Override the output directory (default: `decisions/`) |
| `--deep` | Inject a mutual critique round before synthesis — each model critiques the others' arguments, then the chairman synthesizes everything |
| `--context <file>`, `-x` | Inject a reference file as context for all models — repeatable for multiple files |
| `--prior <id>`, `-p` | Inject a past decision (by ID from `dissenter history`) as context |

```bash
dissenter ask "Should I use Kafka or Postgres outbox?"
dissenter ask "..." --config fast                             # named preset
dissenter ask "..." --context planning-doc.md                 # inject a reference file
dissenter ask "..." --context spec.md --context rfc.md        # multiple files
dissenter ask "..." --prior 3                                 # inject past decision #3
dissenter ask "..." --quick                                   # auto-detect Ollama
dissenter ask "..." --deep                                    # add mutual critique round
dissenter ask "..." --model ollama/mistral@skeptic --model ollama/phi3@pragmatist --chairman ollama/mistral
```

Every run saves a `config.toml` snapshot in the run directory for exact re-runs. Every debate model also self-reports a confidence score (1–10) and what would change its stance — shown in the live table and rendered as a `## Confidence Signals` table in the ADR.

---

### `dissenter init`

Interactive config wizard. Uses arrow-key selection throughout — model list is credential-aware (only shows installed Ollama models and cloud providers where a CLI or API key is detected). Prompts for a config name upfront: leave blank for a timestamped filename (`dissenter_20260326_143022.toml`), or type a name (`fast` → `dissenter_fast.toml`).

| Flag | Description |
|------|-------------|
| _(no flags)_ | Full interactive wizard → `dissenter.toml` in current dir |
| `--force` | Overwrite existing `dissenter.toml` without prompting |
| `--save <name>` | Save as a named preset → `~/.config/dissenter/<name>.toml` |
| `--auto` | Non-interactive: auto-generate from all local Ollama models |
| `--memory <GB>` | With `--auto`: fit models within this RAM budget per round |
| `--rounds <N>` | With `--auto`: number of debate rounds before the final (default: 1) |

```bash
dissenter init                                    # interactive
dissenter init --save fast                        # save as named preset
dissenter init --auto --memory 8 --rounds 2 --save deep
dissenter ask "..." --config deep                 # use named preset
```

---

### `dissenter generate`

Generate a config file from a natural-language prompt. An LLM reads your intent plus the full detected environment (installed models, CLI tools, API keys, role catalog, TOML schema) and writes a valid config. Validates through the full pipeline and retries with injected error context on failure.

| Flag | Description |
|------|-------------|
| `--model <id>`, `-m` | Model to use for generation (auto-picked if omitted: Claude CLI > Gemini CLI > API > Ollama) |
| `--output <name>`, `-o` | Config name — saved as `dissenter_<name>.toml` (timestamped if omitted) |
| `--retries <N>`, `-r` | Max generation attempts (default: 3) |

```bash
dissenter generate "fast 2-round debate with local ollama models"
dissenter generate "claude vs gemini, skeptic and pragmatist roles" --output claude-gemini
dissenter generate "..." --model ollama/mistral:latest
```

---

### `dissenter models`

Show detected Ollama models, CLI tool paths, and API key status. No flags.

---

### `dissenter config`

Inspect the active config as a tree (rounds, models, roles, auth). Useful for verifying a config before running a debate.

| Flag | Description |
|------|-------------|
| `--config <path\|name>` | Config to inspect (default: `dissenter.toml`) |

---

### `dissenter history`

Browse and search past decisions. Every `dissenter ask` run is automatically saved to a local SQLite database — no flags needed.

| Flag | Description |
|------|-------------|
| `--search <term>`, `-s` | Filter by keyword in question or decision text |
| `--limit <n>`, `-n` | Max rows to show (default: 20) |
| `--clear` | Delete all run history (prompts for confirmation) |
| `--yes`, `-y` | Skip confirmation when using `--clear` |

Database location:
- Mac: `~/Library/Application Support/dissenter/dissenter.db`
- Linux: `~/.local/share/dissenter/dissenter.db`
- Windows: `%LOCALAPPDATA%\dissenter\dissenter.db`

---

### `dissenter upgrade`

Self-upgrade to the latest version from PyPI. No flags needed.

```bash
dissenter upgrade
```

---

### `dissenter uninstall`

Remove all app data from this machine (database + config presets). Does not remove the package itself — for that, run `uv tool uninstall dissenter`.

| Flag | Description |
|------|-------------|
| `--yes`, `-y` | Skip confirmation prompt |

---

## Configuration

Edit `dissenter.toml` in the project directory. Pass `--config <path>` to override. Bare names resolve to `~/.config/dissenter/<name>.toml`.

### Minimal config

```toml
output_dir = "decisions"

[[rounds]]
name = "debate"

[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "devil's advocate"

[[rounds.models]]
id   = "gemini/gemini-2.0-flash"
role = "pragmatist"

# Final round: must be exactly 1 or 2 enabled models
[[rounds]]
name = "final"

[[rounds.models]]
id      = "anthropic/claude-opus-4-6"
role    = "chairman"
timeout = 300
```

### Multi-round

Rounds execute sequentially. Each round receives all prior rounds as context.

```toml
output_dir = "decisions"

[[rounds]]
name = "debate"

[[rounds.models]]
id    = "anthropic/claude-sonnet-4-6"
role  = "devil's advocate"
auth  = "cli"

[[rounds.models]]
id    = "gemini/gemini-2.0-flash"
role  = "pragmatist"
auth  = "cli"

[[rounds.models]]
id    = "ollama/mistral"
role  = "skeptic"
extra = { api_base = "http://localhost:11434" }

[[rounds]]
name = "refine"

[[rounds.models]]
id   = "gemini/gemini-2.0-flash"
role = "analyst"
auth = "cli"

[[rounds]]
name = "final"

[[rounds.models]]
id      = "anthropic/claude-opus-4-6"
role    = "chairman"
auth    = "cli"
timeout = 300
```

### Dual-arbiter final

When the final round has exactly 2 models, set `combine_model` to produce a side-by-side recommendation document.

```toml
[[rounds]]
name            = "final"
combine_model   = "ollama/mistral"
combine_timeout = 60

[[rounds.models]]
id      = "anthropic/claude-opus-4-6"
role    = "conservative"
auth    = "cli"
timeout = 300

[[rounds.models]]
id      = "gemini/gemini-2.0-flash"
role    = "liberal"
auth    = "cli"
timeout = 300
```

### CLI auth — no API keys

The default for every model is `auth = "api"` — litellm reads the API key from your environment. Set `auth = "cli"` to use the provider's installed CLI instead. The prompt is piped to the CLI via stdin; the response is captured from stdout. Uses whatever session the CLI has — OAuth, browser login, enterprise SSO.

```toml
[[rounds.models]]
id   = "anthropic/claude-sonnet-4-6"
role = "devil's advocate"
auth = "cli"                  # uses `claude --print` via stdin

[[rounds.models]]
id   = "gemini/gemini-2.0-flash"
role = "pragmatist"
auth = "cli"                  # uses `gemini` via stdin

# Explicit CLI command (for providers not auto-detected)
[[rounds.models]]
id          = "anthropic/claude-opus-4-6"
role        = "chairman"
auth        = "cli"
cli_command = "claude"        # usually inferred automatically
```

Auto-detected CLI commands by provider prefix:

| Provider prefix | CLI used |
|---|---|
| `anthropic/` | `claude` |
| `gemini/` or `google/` | `gemini` |
| anything else | set `cli_command` explicitly |

### Same model, multiple roles

A round can list the same model ID multiple times with different roles. The `dissenter-test.toml` config does this to run the full pipeline with no API keys.

```toml
output_dir = "decisions/test"

[[rounds]]
name = "debate"

[[rounds.models]]
id    = "ollama/ministral-3:3b"
role  = "devil's advocate"
extra = { api_base = "http://localhost:11434" }

[[rounds.models]]
id    = "ollama/ministral-3:3b"
role  = "skeptic"
extra = { api_base = "http://localhost:11434" }

[[rounds.models]]
id    = "ollama/ministral-3:3b"
role  = "pragmatist"
extra = { api_base = "http://localhost:11434" }

[[rounds]]
name = "final"

[[rounds.models]]
id      = "ollama/ministral-3:3b"
role    = "chairman"
timeout = 180
extra   = { api_base = "http://localhost:11434" }
```

### Per-model API key

Override the environment variable with an explicit key per model.

```toml
[[rounds.models]]
id      = "anthropic/claude-sonnet-4-6"
role    = "devil's advocate"
api_key = "sk-ant-..."
```

---

## Roles

Roles live in `src/dissenter/roles/*.toml`. Each file defines a `name`, `description`, and `prompt`. Add a new `.toml` file to create a new role — no code changes needed.

| Role | Description | Typical round |
|------|-------------|---------------|
| `devil's advocate` | Argue against the obvious or popular choice | debate |
| `pragmatist` | Focus on what actually works in production at scale | debate |
| `skeptic` | Find hidden failure modes and long-term risks | debate |
| `contrarian` | Surface the minority expert view and missed nuance | debate |
| `analyst` | Rigorous balanced analysis with concrete numbers | debate / refine |
| `researcher` | Find the most current information using web access | debate |
| `second opinion` | Fresh-eyes independent review | refine |
| `chairman` | Decisive synthesis after all debate | final (1-model) |
| `conservative` | Pragmatic executor — safest proven path | final (2-model) |
| `liberal` | Ambitious visionary — boldest high-upside path | final (2-model) |

Any string is a valid role — unknown roles fall back to the `analyst` prompt.

To add a custom role:

```toml
# src/dissenter/roles/security_auditor.toml
name        = "security auditor"
description = "Identify attack surfaces and compliance risks"
prompt      = "Your role is security auditor. Identify the attack surface, likely CVEs, supply chain risks, and compliance implications of each option."
```

---

## Output

Each run produces a timestamped directory:

```
decisions/
  20260320_143022/
    decision.md              <- the ADR (commit this)
    config.toml              <- exact config snapshot for re-runs
    round_1_debate/
      anthropic_claude-sonnet-4-6__devils_advocate.md
      gemini_gemini-2.0-flash__pragmatist.md
      ollama_mistral__skeptic.md
    round_2_refine/
      gemini_gemini-2.0-flash__analyst.md
    round_3_final/
      anthropic_claude-opus-4-6__chairman.md
```

The decision file path is printed at the end of each run. The ADR follows a structured format: Context, Consensus, Disagreements, Confidence Signals, Options table, Decision, Consequences, Mitigations, Open Questions.

Every run is automatically saved to a local SQLite database, browsable via `dissenter history` or the TUI.

---

## Testing

```bash
just test       # runs the pytest suite (96 tests)
```

**Testing without API keys — fully local:**

```bash
ollama pull ministral-3:3b
ollama serve
dissenter ask "Should I use Redis or Postgres for session storage?" --config dissenter-test.toml
```

`dissenter-test.toml` runs `ministral-3:3b` with different roles across all rounds. It exercises the full multi-round pipeline with zero external API access.

**`ministral-3:3b` is the recommended Ollama baseline.** Fast, coherent under adversarial role prompting, and produces structured output reliably at 3B params.

---

## Comparison

| Feature | dissenter | llm-council | llm-consortium | consilium | MoA ref impl |
|---------|:---:|:---:|:---:|:---:|:---:|
| Role-differentiated prompts | ✓ | ✗ | ✗ | ✗ | ✗ |
| Multi-round debate hierarchy | ✓ | ✗ | partial¹ | partial² | partial³ |
| Disagreement as structured output | ✓ | ✗ | ✗ | partial⁴ | ✗ |
| Dual-arbiter output | ✓ | ✗ | ✗ | ✗ | ✗ |
| External role files | ✓ | ✗ | ✗ | ✗ | ✗ |
| Same model multiple roles | ✓ | ✗ | ✗ | ✗ | ✗ |
| CLI session auth (no API key) | ✓ | ✗ | ✗ | ✗ | ✗ |
| No OpenRouter/proxy required | ✓ | ✗ | ✗ | ✓ | ✗ |
| Local + cloud in same ensemble | ✓ | ✗ | ✗ | ✗ | ✗ |
| Persistent decision history | ✓ | ✗ | ✗ | ✗ | ✗ |
| ADR output format | ✓ | ✗ | ✗ | ✗ | ✗ |
| Single-file config | ✓ | ✗ | partial | ✗ | ✗ |
| Per-model API key override | ✓ | ✗ | ✗ | ✗ | ✗ |
| `uv tool install` | ✓ | ✗ | partial | ✗ | ✗ |
| Peer critique round (`--deep`) | ✓ | partial⁵ | ✗ | ✓⁶ | ✗ |
| Terminal UI | ✓ | ✗ | ✗ | ✗ | ✗ |
| Context injection (files + prior decisions) | ✓ | ✗ | ✗ | ✗ | ✗ |
| LLM config generation | ✓ | ✗ | ✗ | ✗ | ✗ |

*¹ llm-consortium retries up to 3× when arbiter confidence < 0.8 — iteration toward convergence, not debate.*
*² consilium has configurable `--rounds N` in `discuss`/`socratic` modes.*
*³ MoA has configurable layers (default 3), but each layer refines toward consensus — no debate structure.*
*⁴ consilium uses ACH (Analysis of Competing Hypotheses) synthesis — the most honest competitor approach, but still ends in a verdict.*
*⁵ llm-council Stage 2 is anonymous peer **ranking**, not written critique of reasoning.*
*⁶ consilium has cross-pollination (models investigate each other's gaps) and a rotating challenger role.*

---

## Academic foundations

- **Mixture of Agents** (arXiv 2406.04692, TogetherAI, June 2024) — the canonical proposer→aggregator architecture. dissenter is a multi-layer MoA with adversarial role differentiation on the proposer layer.
- **ICE: Iterative Critique and Ensemble** (medrxiv, December 2024) — mutual critique between models before synthesis yields +7–45% accuracy on hard benchmarks. Basis for the `--deep` flag.
- **LLM Ensemble Survey** (arXiv 2502.18036, February 2025) — taxonomy of ensemble methods; identifies prompt diversity as the strongest lever.
- **Rethinking MoA** (OpenReview 2025) — finds diverse *framing* of the same question outperforms diverse *models* asked the same way. Direct justification for role-differentiated prompting.

---

## Roadmap

**Done:**
- [x] Multi-round debate with context passing between rounds
- [x] Role prompts as external TOML files (`src/dissenter/roles/*.toml`)
- [x] Dual-arbiter final round (conservative + liberal + combine_model)
- [x] CLI session auth (`auth = "cli"`) — use installed CLIs without API keys
- [x] Same model, different roles in a single round
- [x] SQLite decision history — `dissenter history` / `dissenter history --clear`
- [x] Named config presets (`--save <name>`, `--config <name>`)
- [x] `dissenter init --auto` — non-interactive Ollama config generation with RAM budgeting
- [x] Questionary wizard — arrow-key selection throughout, credential-aware model list, timestamped/named config output
- [x] Ollama RAM estimation and warnings before running
- [x] Config snapshot per run for exact reproducibility
- [x] `uv tool install` / `just global-install` — global PATH install
- [x] `dissenter uninstall` — full app data removal
- [x] `--deep` flag: peer critique round (ICE paper, +7–45% accuracy on hard benchmarks)
- [x] Automated versioning via `hatch-vcs` — version derived from git tag at build time
- [x] Confidence scoring — each model self-reports certainty (1–10) and what would change its stance; surfaced in the live table and ADR
- [x] `dissenter generate` — LLM-powered config generation from a natural-language prompt with validation + retry loop
- [x] Pre-flight credential check — validates all model availability before starting a debate
- [x] Context injection — `--context <file>` and `--prior <id>` for reference material in debates
- [x] Textual TUI — full terminal UI with sidebar navigation, debate progress, history browser, decision viewer, models panel, config inspector

**Planned:**
- [ ] Disagreement classifier: factual vs. trade-off vs. context-dependent
- [ ] Dynamic role inference: infer relevant roles from question type (security, performance, cost, maintainability)
- [ ] Live round-by-round progress in TUI (granular model completion updates instead of spinner)
- [ ] TUI config editor (edit TOML inline from the terminal UI)
