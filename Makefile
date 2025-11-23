.PHONY: help install test

# Default target - show help
help:
	@echo "📦 Dotfiles Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make install    - Install dotfiles and create symlinks"
	@echo "  make test       - Run E2E tests (requires docker compose)"
	@echo "  make help       - Show this help message"
	@echo ""
	@echo "For more information, see docs/README.md"

install:
	@sh ./scripts/install.sh

test:
	@sh ./scripts/test.sh
