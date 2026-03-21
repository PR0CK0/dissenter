.PHONY: ask ask-test show install test publish

UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

ask:
	@$(UV) run dissenter ask "$(Q)"

ask-test:
	@$(UV) run dissenter ask "$(Q)" --config dissenter-test.toml

show:
	@$(UV) run dissenter show

install:
	@$(UV) sync

test:
	@$(UV) run pytest tests/ -v

publish:
	@$(UV) build
	@UV_PUBLISH_TOKEN=$(PYPI_TOKEN) $(UV) publish
