.PHONY: help install install-system test test-unit test-node test-bootstrap test-install test-system lint lint-shell lint-lua lint-yaml lint-stylua lint-build

# Default target - show help
help:
	@echo "📦 Dotfiles Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make install       - Install dotfiles and create symlinks"
	@echo "  make install-system- Show root-side drift (system/); apply: sudo scripts/install-system.sh --apply"
	@echo "  make test          - Run all unit tests (python + node)"
	@echo "  make test-unit     - Run Python unit tests (tests/unit/)"
	@echo "  make test-node     - Run Node unit tests (tests/unit/*.mjs, node >= 22.6)"
	@echo "  make test-bootstrap- Run bootstrap-kit round-trip tests (needs age)"
	@echo "  make test-install  - Run the real installer + assertions in Docker (CI parity)"
	@echo "  make test-system   - Test the system layer (system/) in a fake root"
	@echo "  make lint          - Run all linters (Docker-based)"
	@echo "  make lint-shell    - Run shellcheck on shell scripts"
	@echo "  make lint-lua      - Run luacheck on Lua files"
	@echo "  make lint-yaml     - Run yamllint on YAML files (incl. workflows)"
	@echo "  make lint-stylua   - Run stylua --check on nvim Lua (CI gate)"
	@echo "  make lint-build    - Build/rebuild Docker linter image"
	@echo "  make help          - Show this help message"
	@echo ""
	@echo "For more information, see docs/README.md and docs/LINTING.md"

install:
	@bash ./scripts/install.sh

# Dry run on purpose: root-side changes are applied explicitly with sudo.
install-system:
	@bash ./scripts/install-system.sh

test: test-unit test-node

test-unit:
	@python3 -m unittest discover -s tests/unit -t tests/unit -v

# PI_LLM_CLASS leaks from agent shells into class-sensitive tests; strip it.
test-node:
	@env -u PI_LLM_CLASS -u PI_LLM_CLASS_ESCALATE \
		node --test --experimental-strip-types tests/unit/*.mjs

test-bootstrap:
	@bash tests/bootstrap-preflight.sh
	@bash tests/bootstrap-kit.sh

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

test-system:
	@bash tests/system-layer.sh
	@bash tests/git-bundles.sh

lint:
	@bin/lint --all

lint-shell:
	@bin/lint --shellcheck

lint-lua:
	@bin/lint --luacheck

lint-yaml:
	@bin/lint --yamllint

lint-stylua:
	@bin/lint --stylua

lint-build:
	@bin/lint --build
