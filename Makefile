.PHONY: ask ask-test show install test

UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

ask:
	@$(UV) run dissent ask "$(Q)"

ask-test:
	@$(UV) run dissent ask "$(Q)" --config dissent-test.toml

show:
	@$(UV) run dissent show

install:
	@$(UV) sync

test:
	@$(UV) run pytest tests/ -v
