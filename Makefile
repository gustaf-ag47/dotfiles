.PHONY: help install test lint lint-shell lint-lua lint-yaml lint-build

# Default target - show help
help:
	@echo "📦 Dotfiles Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make install       - Install dotfiles and create symlinks"
	@echo "  make test          - Run E2E tests (requires docker compose)"
	@echo "  make lint          - Run all linters (Docker-based)"
	@echo "  make lint-shell    - Run shellcheck on shell scripts"
	@echo "  make lint-lua      - Run luacheck on Lua files"
	@echo "  make lint-yaml     - Run yamllint on YAML files"
	@echo "  make lint-build    - Build/rebuild Docker linter image"
	@echo "  make help          - Show this help message"
	@echo ""
	@echo "For more information, see docs/README.md and docs/LINTING.md"

install:
	@sh ./scripts/install.sh

test:
	@sh ./scripts/test.sh

lint:
	@bin/lint --all

lint-shell:
	@bin/lint --shellcheck

lint-lua:
	@bin/lint --luacheck

lint-yaml:
	@bin/lint --yamllint

lint-build:
	@bin/lint --build
