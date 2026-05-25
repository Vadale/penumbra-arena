# Penumbra — one-shot Makefile for visitors and contributors.
#
# `justfile` already exists for the dev workflow; this Makefile is the
# discoverable top-level interface for anyone who clones the repo and
# wants to "just see it work". The two intentionally overlap.
#
# Usage:
#   make demo    # clone-to-browser one-shot: deps + boot stack + open browser
#   make dev     # boot both backend + frontend, no auto-browser
#   make test    # backend pytest (-k "not slow") + frontend vitest
#   make lint    # ruff + pyright + biome
#   make clean   # remove .venv, node_modules, build artifacts

.PHONY: demo dev test lint clean help

# `make` with no target shows the help.
help:
	@echo "Penumbra — make targets:"
	@echo "  make demo     clone-to-browser: install deps, boot stack, open http://localhost:5173"
	@echo "  make dev      boot backend on 8100 + frontend on 5173 (no browser open)"
	@echo "  make test     run backend pytest (fast subset) + frontend vitest"
	@echo "  make lint     ruff + pyright + biome"
	@echo "  make clean    remove .venv, node_modules, dist"
	@echo ""
	@echo "Penumbra is v1.0 (feature-frozen). See CHANGELOG.md."

demo:
	@bash scripts/demo.sh

dev:
	@bash scripts/demo.sh --no-open

test:
	uv run pytest -p no:warnings -q packages -k "not slow"
	pnpm --filter web test

lint:
	uv run ruff check packages
	uv run ruff format --check packages
	uv run pyright packages
	pnpm --filter web exec biome check src
	pnpm --filter web typecheck

clean:
	rm -rf .venv .ruff_cache .pytest_cache .hypothesis
	rm -rf apps/web/node_modules apps/web/dist
	rm -rf node_modules
	@echo "cleaned. run 'make demo' to rebuild."
