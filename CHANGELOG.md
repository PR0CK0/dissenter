# Changelog

All notable changes to this project are documented here.

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
