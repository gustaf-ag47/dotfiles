.PHONY: help install test test-unit test-install lint lint-shell lint-lua lint-yaml lint-build

# Default target - show help
help:
	@echo "📦 Dotfiles Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make install       - Install dotfiles and create symlinks"
	@echo "  make test          - Run E2E tests (requires docker compose)"
	@echo "  make test-unit     - Run Python unit tests (tests/unit/)"
	@echo "  make test-install  - Run the real installer + assertions in Docker (CI parity)"
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

test-unit:
	@python3 -m unittest discover -s tests/unit -t tests/unit -v

# Same commands the `install` job runs in .github/workflows/dotfiles.yml, so a
# CI failure reproduces locally with one target.
test-install:
	@docker run --rm --pull=always -v "$(CURDIR):/src:ro" archlinux:latest bash -c '\
		set -e; \
		pacman -Syu --noconfirm --needed base-devel git rsync zsh tmux neovim curl fzf sudo python jq >/dev/null; \
		useradd -m -G wheel tester; \
		install -d -o tester -g tester /home/tester/sync/src; \
		rsync -a --exclude .git --exclude local /src/ /home/tester/sync/src/dotfiles/; \
		chown -R tester:tester /home/tester/sync; \
		su - tester -c "cd ~/sync/src/dotfiles && make install" >/dev/null; \
		su - tester -c "cd ~/sync/src/dotfiles && bash tests/install-assertions.sh"; \
		su - tester -c "cd ~/sync/src/dotfiles && bash tests/idempotency.sh"'

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
