# Changelog

All notable changes to this project are documented here.

## [2.3.0] — 2026-03-30

### Added
- **`--context <file>` / `-x`** on `ask` — inject one or more reference files as context for all debate models. Repeatable. The file contents are prepended to every model's prompt as `[User-supplied reference material]`.
- **`--prior <id>` / `-p`** on `ask` — inject a past decision (by ID from `dissenter history`) as context. Pulls the full ADR from the SQLite database and prepends it the same way.

---

## [2.2.1] — 2026-03-30

### Added
- **`dissenter upgrade`** — self-upgrade to the latest PyPI version. Runs `uv tool install dissenter --force --no-cache` under the hood.

---

## [2.2.0] — 2026-03-28

### Added
- **`dissenter generate "prompt"`** — LLM-powered config generation from a natural-language description. The generator reads the full detected environment (Ollama models, CLI tools, API keys), the complete role catalog, and the TOML schema spec, then writes a valid config. Output is validated through a 4-stage pipeline (TOML parse → pydantic schema → pre-flight credentials → sanity) and automatically retried with injected error context on failure (default 3 attempts). Generator model is auto-picked (Claude CLI > Gemini CLI > API > Ollama) or set via `--model`.
- **`validate.py`** — shared config validation module used by both `ask` and `generate`. Validates TOML parsing, pydantic schema, credential availability, and structural sanity. Returns typed `ConfigError` objects with stage labels.
- **`generate.py`** — prompt builder with modular constant string blocks (`_INTRO`, `_SCHEMA_SPEC`, `_ROLES_CATALOG`, `_ENV_TEMPLATE`, `_INTENT_TEMPLATE`, `_RETRY_TEMPLATE`) assembled by `build_prompt()` and `build_retry_prompt()`. Includes TOML extraction from code fences, model auto-picker, and async generate-validate-retry loop.

### Changed
- **Pre-flight check refactored** — `ask` now uses the shared `validate_toml()` from `validate.py` instead of inline checks.

### Fixed
- **Loading spinner style** — `dim grey` → `dim`
- **Confidence display** — `8/10` → `confidence 8/10` in status table

---

## [2.1.2] — 2026-03-27

### Fixed
- **Pre-flight credential check** — `dissenter ask` now validates all models before starting: Ollama models must be installed, CLI-auth models must have the CLI on PATH, API-auth models must have the env var set (or `api_key` in config). Exits with a clear per-model error list instead of failing mid-run.
- **Confidence display** — status table now shows `confidence 8/10` instead of bare `8/10`.

---

### Fixed
- **Loading spinner style** — was `dim grey` (unrecognised), now `dim` to match synthesis/exit message styling.
- **Pre-flight credential check** — `dissenter ask` now validates all models before starting: Ollama models must be installed, CLI-auth models must have the CLI on PATH, API-auth models must have the env var set (or `api_key` in config). Exits with a clear per-model error list instead of failing mid-run.
- **Confidence display** — status table now shows `confidence 8/10` instead of bare `8/10`.

---

### Fixed
- **Loading spinner style** — was `dim grey` (unrecognised), now `dim` to match synthesis/exit message styling.
- **Ollama pre-flight check** — `dissenter ask` now validates all Ollama models in the config are installed before starting the debate. If any are missing, it exits immediately with a clear error and the `ollama pull` command to fix it.

---

## [2.1.1] — 2026-03-27

### Fixed
- **Startup latency** — `models`, `history`, `config`, `init` now start in ~0.1s instead of ~3s. `litellm` (~1s cold import) is now lazy-loaded inside `ask` only, since no other command needs it.

### Added
- **Loading spinner** — `ask` shows a dim grey spinner with a random thematic message ("Convening the council...", "Assembling the panel...", etc.) while `litellm` loads, before the debate begins.

---

## [2.1.0] — 2026-03-27

### Added
- **Auto update check** — on every invocation, dissenter checks PyPI for a newer version in a background thread (non-blocking, cached for 24h). If an update is available, a `↑ vX.Y.Z available (uv tool upgrade dissenter)` notice appears under the command header. Dev/local builds are silently skipped.

---

## [2.0.2] — 2026-03-27

### Changed
- **`--help` header** — `dissenter vX.Y.Z — <cmd>` rule line now appears at the top of every `--help` output, matching the runtime command headers.

---

## [2.0.1] — 2026-03-27

### Changed
- **`src/dissent` → `src/dissenter`** — Python import path now matches the package name, CLI name, and PyPI name. Internal change only; no user-facing impact.

---

## [2.0.0] — 2026-03-27

### Changed
- **`dissenter show` → `dissenter config`** — more explicit about what it does; avoids confusion with `history`.
- **`dissenter clear` removed** — absorbed into `dissenter history --clear` (`--yes` to skip prompt). Clears history from the same place you browse it.
- **`dissenter uninstall`** — help text now explicitly states it does not remove the package, and shows the correct `uv tool uninstall dissenter` command for that.
- **`--help` improvements** — all commands now include concrete usage examples in their help text (visible via `dissenter <cmd> --help`).

---

## [1.7.0] — 2026-03-26

### Added
- **Confidence scoring** — each debate model now self-reports a confidence score (1–10) and states what specific evidence would change its recommendation. Confidence is parsed out of the model response, shown in the live status table during each round, included inline in the debate context passed to the chairman, and rendered as a `## Confidence Signals` table in the synthesized ADR. Low-confidence signals and cross-model divergence are explicitly flagged in the synthesis rationale.

---

## [1.6.0] — 2026-03-26

### Added
- **`dissenter --version` / `-v`** — prints the installed version and exits.
- **Uniform command headers** — every command (`ask`, `init`, `history`, `clear`, `uninstall`, `models`, `show`) now opens with `dissenter vX.Y.Z — <command>` rendered as a rule line.

### Changed
- **Wizard environment panel** — title changed from `dissenter init` to `environment` (dim grey) for cleaner visual hierarchy.
- **README** — `dissenter init` description updated to reflect arrow-key select throughout (no autocomplete); config naming behaviour documented; auto-save to SQLite called out explicitly; `--deep` moved from roadmap to Done; academic foundations reference fixed; clickable-link language removed; `--version` documented.

---

## [1.5.0] — 2026-03-26

### Added
- **Automated versioning** — version is now derived from the git tag at build time via `hatch-vcs`. No more manual `pyproject.toml` bumps — tag `vX.Y.Z`, the wheel gets that version automatically.

### Changed
- **Wizard: config name upfront** — asked before rounds collection. Leave blank for a timestamp-based filename (`dissenter_20260326_143022.toml`), or type a name (`test` → `dissenter_test.toml`).
- **Wizard: existing config conflict** — replaced yes/no overwrite prompt with a numbered 4-option select: `1. Use existing`, `2. Create new named config`, `3. Overwrite with this new config`, `4. Exit`.
- **Wizard: save step** — replaced yes/no confirm with a 3-option select: `Save → <filename>`, `Redo wizard`, `Exit without saving`. Redo loops back to the start of rounds collection.
- **Wizard: role selector** — removed `default` highlight that caused two competing visual indicators (box + cursor arrow). Cursor only.
- **Wizard: exit and synthesis messages** — all rendered in dim grey for consistent styling.
- **Cleanup** — removed leftover `llm-ensemble` era files: `ensemble` binary, `ensemble.toml`, `src/ensemble/`, `test-ollama.sh`.

---

## [1.4.0] — 2026-03-22

### Added
- **`--deep` flag** — injects a mutual critique round between the last debate round and final synthesis. Each model receives the other models' prior outputs and writes a structured critique: what's wrong, what was missed, and what would change its stance. The chairman reads all debate + critique before synthesizing the ADR. Based on the ICE paper (medrxiv, Dec 2024), which found mutual critique before synthesis yields +7–45% accuracy on hard benchmarks.

### Changed
- **Round counter** — `Round N of M` now correctly counts the injected critique round (e.g. `Round 2 of 3: critique` with `--deep`).
- **Synthesis spinner** — animated dots spinner shown while the chairman is writing, replacing the blank pause.
- **Synthesis messages** — random thematic message shown in the spinner while the chairman writes (same pattern as Ctrl+C exit messages).
- **Output paths** — plain paths printed after each run, no link markup (OSC 8 hyperlinks not supported in macOS Terminal.app).
- README updated with `--deep` flag in the `ask` command table and roadmap checked off.

---

## [1.3.0] — 2026-03-21

### Changed
- **Wizard model chooser** — switched from autocomplete to arrow-key `select`, matching the role picker UX. Model list is now credential-aware: only shows Ollama models detected locally and cloud models for providers where a CLI (`claude`, `gemini`) or API key env var is present. A `[ type custom ID... ]` escape hatch covers anything else.
- **Wizard "copy example" prompt** — clarified that declining the copy offer starts the step-by-step wizard (`Starting step-by-step wizard...` message shown before proceeding).
- **README** — shortened by ~25%, all semantics retained. Added per-command flag tables for `ask`, `init`, `show`, and `history`. Updated roadmap to reflect all shipped features.

---

## [1.2.0] — 2026-03-21

### Added
- **Questionary wizard** — `dissenter init` now uses arrow-key selection and autocomplete instead of free-text prompts.
  - Model ID: autocomplete from detected Ollama models + curated cloud model list, type to filter.
  - Role: arrow-key select from all 10 built-in roles, with a custom escape hatch.
  - Auth: select with inferred default and plain-English descriptions.
  - Final round type: select (chairman vs dual-arbiter).
- **Exit messages** — Ctrl+C anywhere (wizard or mid-debate) shows a random cryptic message from a pool of 12 thematic lines.
- **Version in header** — `ask` header now shows `dissenter vX.Y.Z` pulled live from package metadata.

### Changed
- `dissenter.toml` renamed to `dissenter.example.toml` — follows `.env.example` convention. Copy it to `dissenter.toml` (gitignored) to get started.
- `dissenter.toml` added to `.gitignore` — safe to include `api_key` entries without committing secrets.
- `dissenter init` — detects example-only state and offers to copy it before running the full wizard.
- `dissenter ask` — missing config error is now rich-formatted with exact copy commands per platform.
- `dissenter uninstall` — deduplicates paths on Mac/Windows where data and config dirs are the same.
- Wizard no longer prompts for output directory — hardcoded to `decisions`, editable in the TOML.
- `just test` and `just install` now include dev extras so `pytest-asyncio` is always present.

---

## [1.1.0] — 2026-03-21

### Added
- **SQLite persistence** (`db.py`) — all runs stored in platform-native data dir (`platformdirs.user_data_dir`). Cross-platform: Mac `~/Library/Application Support/dissenter/`, Linux `~/.local/share/dissenter/`, Windows `%LOCALAPPDATA%\dissenter\`.
- **`dissenter history`** — browse and search past decisions interactively. Numbered table, keyword filter (`--search`), open any decision by number, shows re-run command.
- **`dissenter clear`** — delete all run history from the database.
- **`dissenter uninstall`** — remove all app data (database + config presets) from the machine.
- **Ollama memory estimation** — `ask` shows estimated peak RAM for Ollama models before running. Warns at ≥8 GB, alerts at ≥16 GB. Based on concurrent models per round (not total).
- **Config snapshot** — every `ask` run writes `config.toml` to the run directory for exact re-runs: `dissenter ask "..." --config decisions/<ts>/config.toml`.
- **Named presets** — `dissenter init --save <name>` saves to `~/.config/dissenter/<name>.toml`. `dissenter ask "q" --config <name>` resolves by name automatically.
- **`dissenter init --auto`** — non-interactive: auto-generates a config from all local Ollama models. `--memory <GB>` fits models within a RAM budget per round. `--rounds <N>` sets debate depth.
- **`Justfile`** — cross-platform shortcuts for all commands (Windows/Linux/Mac). `just ask "question"`, `just init-auto memory=8`, `just global-install`, etc.
- **`just global-install`** — installs `dissenter` globally via `uv tool install .` so `dissenter` works anywhere without `uv run`.

### Changed
- `dissenter init` default: warns clearly if `dissenter.toml` already exists instead of silently overwriting. Suggests `--force` or `--save <name>`.
- `--config` on `ask`/`show` now accepts a preset name (no path separators) and resolves to `~/.config/dissenter/<name>.toml`.

---

## [1.0.4] — 2026-03-21

### Added
- README badges: uv, LLMs (Ollama | Claude | Gemini | Codex).

### Fixed
- Python version badge restored to dynamic PyPI source after confirming package is indexed.

---

## [1.0.3] — 2026-03-21

### Added
- `README.md` badges: PyPI version, Python versions, license, publish workflow status, LiteLLM.
- `LICENSE` (MIT, Dr. Tyler T. Procko).
- Full `pyproject.toml` metadata: `readme`, `license`, `authors`, `keywords`, `classifiers`, `[project.urls]` — populates the PyPI project page.

### Changed
- Project description updated to reflect use for complex questions generally, not just architectural decisions.

---

## [1.0.2] — 2026-03-21

### Added
- `make publish` target for manual PyPI deploys (`PYPI_TOKEN=pypi-xxxx make publish`).
- GitHub Actions `workflow_dispatch` trigger — publish manually from the GitHub Actions UI without a tag push.

---

## [1.0.1] — 2026-03-21

### Changed
- Renamed project/package/CLI from `dissent` to `dissenter` (PyPI name `dissent` was taken).
  - PyPI package: `pip install dissenter`
  - CLI command: `dissenter ask / init / models / show`
  - Default config file: `dissenter.toml` (was `dissent.toml`)
  - Config dir: `~/.config/dissenter/` (was `~/.config/dissent/`)
  - GitHub repo renamed to `PR0CK0/dissenter`
  - Python import path unchanged (`from dissent.xxx import ...`)
- Bumped version to 1.0.1.

---

## [1.0.0] — 2026-03-21

### Added
- **`dissent init`**: Interactive config wizard. Detects installed Ollama models and
  claude/gemini CLI tools, prompts for rounds/models/roles/auth, previews generated
  TOML, and saves to `dissent.toml`. Supports both chairman and dual-arbiter finals.
- **`dissent models`**: Shows detected Ollama models, CLI tool paths, and API provider
  key status (which env vars are set) in one command.
- **`dissent ask --model` / `--chairman` / `--quick`**: Run debates without a config file.
  `--model model_id[@role]` (repeatable) builds a debate round inline.
  `--quick` auto-detects all installed Ollama models and runs immediately.
- **PyPI publishing**: GitHub Actions workflow triggers on version tags and publishes
  via `uv publish` with OIDC trusted publishing (no token management needed).
- **`detect.py`**: Shared environment detection utilities (`detect_ollama_models`,
  `detect_clis`, `detect_api_keys`, `infer_auth`).

### Changed
- `dissent show` now displays auth mode alongside each model.
- Config priority for `ask`: `--quick` > `--model/--chairman` > config file.

---

## [0.2.1] — 2026-03-21

### Changed
- Output structure unified: all files for a run now live under
  `decisions/<timestamp>/`. The decision is `decision.md` and per-round
  debug files are subdirectories within the same folder. Previously the
  decision file and the debug directory were siblings with different names.

---

## [0.2.0] — 2026-03-21

### Added
- **CLI auth mode** (`auth = "cli"`): Each model can now authenticate via a locally-installed
  provider CLI instead of an API key. Auto-detects `claude` for Anthropic and `gemini` for
  Google/Gemini providers. Override with `cli_command = "..."` in config.
- **Dual-arbiter final round**: Final round can have 2 models (conservative + liberal roles)
  combined side-by-side using a `combine_model`. Output is a `Dual Recommendation` document.
- **Synthesis respects auth mode**: Synthesis phase now correctly routes through CLI or API
  based on each model's `auth` field (was previously always using litellm).
- **Error classification**: Friendly error messages for missing API keys, Ollama not running,
  model not installed, rate limits, and context window exceeded.
- **Clickable output links**: Terminal output uses OSC 8 hyperlinks to the saved decision file.
- `dissent-test.toml`: Minimal test config using `ollama/ministral-3:3b` (no API keys needed).
- `ensemble` binary removed from tracked files.

### Changed
- `dissent.toml`: Updated to use `auth = "cli"` for Anthropic and Gemini models.
- `dissent.toml`: Fixed `qwen2.5:7b` → `qwen2.5:1.5b`.
- `dissent.toml`: Fixed `ministral:3b` → `ministral-3:3b`.
- CLI no longer prints full ADR to stdout; links to the saved file instead.

### Fixed
- Same model with different roles in one round: composite key `id::role::index` prevents
  collision when the same model ID appears multiple times.
- Synthesis `combine_model` (a string) is now wrapped in a `ModelConfig` for routing.

---

## [0.1.0] — 2026-03-18

### Added
- **Multi-round debate engine**: Arbitrary number of sequential rounds; models run in parallel
  within each round and receive prior round context.
- **Enforced final round**: Last `[[rounds]]` block must have exactly 1 model (chairman) or
  2 models with a `combine_model` (dual-arbiter). Validated at config load.
- **Role prompt system**: 10 adversarial roles extracted to individual TOML files under
  `src/dissent/roles/`. Roles: analyst, chairman, conservative, contrarian, devil's advocate,
  liberal, pragmatist, researcher, second opinion, skeptic.
- **ADR output**: Chairman synthesis produces a structured Architectural Decision Record with
  Context, Consensus, Disagreements, Options, Decision, Consequences, and Open Questions.
- **Rich live status display**: Per-round tables showing model, role, elapsed time, and
  word count / error for each model as they complete.
- **Config validation**: pydantic v2 models with `model_validator` enforcing round constraints.
- **`dissent ask`**: Run a debate and save output to `decisions/` with timestamped filenames.
- **`dissent show`**: List saved decisions and open one interactively.
- **Debug dir**: Per-run `debug/` subdirectory with raw round outputs for inspection.
- **Unit and integration tests**: 23 tests across config, roles, runner, and integration.
- **Makefile**: `ask`, `ask-test`, `show`, `install`, `test` targets.
- **README**: Full documentation with architecture diagram, competitor comparison, install
  guide, config reference, role catalog, and academic foundations.

### Project
- Renamed from `llm-ensemble` to `dissent`.
- Package: `dissent` v0.1.0 → v0.2.0 (single release includes all above).
- Requires Python 3.11+, uv, litellm, typer, rich, pydantic, platformdirs.
