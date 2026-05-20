# Penumbra — task runner. Run `just` to list targets.

default:
    @just --list

# ── setup ──────────────────────────────────────────────────────────────
setup:
    uv sync --all-extras
    pnpm install
    uv run pre-commit install

# ── python ─────────────────────────────────────────────────────────────
test *args:
    uv run pytest {{args}}

typecheck:
    uv run pyright

lint:
    uv run ruff check .

format:
    uv run ruff format .

check: lint typecheck test

# ── web ────────────────────────────────────────────────────────────────
web-dev:
    pnpm --filter web dev

web-typecheck:
    pnpm --filter web typecheck

web-lint:
    pnpm --filter web lint

web-build:
    pnpm --filter web build

# ── runtime ────────────────────────────────────────────────────────────
api-dev:
    PENUMBRA_SEED=42 uv run uvicorn penumbra_transport.api:app --reload --port 8000

up:
    docker compose -f infra/docker-compose.yml up --build

down:
    docker compose -f infra/docker-compose.yml down

# ── housekeeping ───────────────────────────────────────────────────────
clean:
    rm -rf .venv .pytest_cache .ruff_cache .pyright dist build
    find . -name "__pycache__" -type d -prune -exec rm -rf {} +
    find . -name ".coverage" -delete
