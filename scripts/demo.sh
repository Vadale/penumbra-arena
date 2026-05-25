#!/usr/bin/env bash
#
# Penumbra demo bootstrap — one-shot "clone-to-browser" entry point.
#
# Steps:
#   1. Resolve dependencies via uv + pnpm (idempotent; re-running is cheap).
#   2. Start the FastAPI backend on PENUMBRA_API_PORT (default 8100).
#      Honour any process already bound to that port.
#   3. Start the Vite dev server on PENUMBRA_WEB_PORT (default 5173).
#   4. Poll /health until the backend answers.
#   5. Open http://localhost:5173 in the user's default browser
#      (unless --no-open was passed).
#
# The script intentionally leaves the backend + frontend running in the
# background after exit so the user can keep clicking around. To stop
# them, run `pkill -f 'penumbra_transport.api' ; pkill -f 'vite'`.

set -euo pipefail

# ── flags ──────────────────────────────────────────────────────────────
OPEN_BROWSER=true
for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN_BROWSER=false ;;
    -h|--help)
      echo "Usage: $0 [--no-open]"
      echo "  --no-open   skip launching the browser at the end"
      exit 0 ;;
  esac
done

# ── config ─────────────────────────────────────────────────────────────
API_PORT="${PENUMBRA_API_PORT:-8100}"
WEB_PORT="${PENUMBRA_WEB_PORT:-5173}"
SEED="${PENUMBRA_SEED:-42}"
TICK_HZ="${PENUMBRA_TICK_HZ:-2.0}"
HEALTH_URL="http://localhost:${API_PORT}/health"
WEB_URL="http://localhost:${WEB_PORT}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${REPO_ROOT}/state/demo_logs"
mkdir -p "${LOG_DIR}"

cd "${REPO_ROOT}"

# ── helpers ────────────────────────────────────────────────────────────
say() { printf "\033[36m[demo]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[demo]\033[0m %s\n" "$*" >&2; }
die() { printf "\033[31m[demo]\033[0m %s\n" "$*" >&2; exit 1; }

port_in_use() {
  # Returns 0 if the port is taken on localhost.
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_health() {
  local tries=60
  for ((i = 1; i <= tries; i++)); do
    if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

# ── 1. deps ────────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  die "uv not installed. See https://docs.astral.sh/uv/getting-started/installation/"
fi
if ! command -v pnpm >/dev/null 2>&1; then
  die "pnpm not installed. Run 'corepack enable && corepack prepare pnpm@latest --activate' or see https://pnpm.io/installation"
fi

say "syncing Python deps (uv sync --all-packages)…"
uv sync --all-packages >"${LOG_DIR}/uv_sync.log" 2>&1 \
  || die "uv sync failed — see ${LOG_DIR}/uv_sync.log"

say "syncing frontend deps (pnpm install)…"
pnpm install --frozen-lockfile=false >"${LOG_DIR}/pnpm_install.log" 2>&1 \
  || die "pnpm install failed — see ${LOG_DIR}/pnpm_install.log"

# ── 2. backend ─────────────────────────────────────────────────────────
if port_in_use "${API_PORT}"; then
  warn "backend port ${API_PORT} is already in use. Skipping backend boot — assuming you already have one running."
  BACKEND_PID=""
else
  say "starting backend on http://localhost:${API_PORT}…"
  PENUMBRA_SEED="${SEED}" \
  PENUMBRA_TICK_HZ="${TICK_HZ}" \
  PENUMBRA_ENABLE_PTY=1 \
  PENUMBRA_ENABLE_REPL=1 \
  PENUMBRA_MAPPO_CHECKPOINT="${REPO_ROOT}/checkpoints/mappo_v0.pt" \
  uv run uvicorn penumbra_transport.api:app --port "${API_PORT}" \
    >"${LOG_DIR}/backend.log" 2>&1 &
  BACKEND_PID=$!
  say "backend pid=${BACKEND_PID} — log at ${LOG_DIR}/backend.log"
fi

# ── 3. frontend ────────────────────────────────────────────────────────
if port_in_use "${WEB_PORT}"; then
  warn "frontend port ${WEB_PORT} is already in use. Skipping frontend boot."
  FRONTEND_PID=""
else
  say "starting frontend on http://localhost:${WEB_PORT}…"
  PENUMBRA_API_PORT="${API_PORT}" \
  pnpm --filter web dev >"${LOG_DIR}/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  say "frontend pid=${FRONTEND_PID} — log at ${LOG_DIR}/frontend.log"
fi

# ── 4. health check ────────────────────────────────────────────────────
say "waiting for backend /health…"
if ! wait_for_health; then
  warn "backend didn't answer /health within 30 s — check ${LOG_DIR}/backend.log"
  warn "the frontend may still load but tiles will show 'analytics offline'."
fi

# ── 5. open browser ────────────────────────────────────────────────────
if [[ "${OPEN_BROWSER}" == "true" ]]; then
  sleep 1  # give Vite a moment to bind
  if command -v open >/dev/null 2>&1; then
    say "opening ${WEB_URL}…"
    open "${WEB_URL}"
  elif command -v xdg-open >/dev/null 2>&1; then
    say "opening ${WEB_URL}…"
    xdg-open "${WEB_URL}"
  else
    say "open ${WEB_URL} manually."
  fi
fi

cat <<EOF

\033[32m[demo]\033[0m Penumbra is up.
  dashboard : ${WEB_URL}
  api       : http://localhost:${API_PORT}
  logs      : ${LOG_DIR}

To stop the stack:
  pkill -f 'penumbra_transport.api' ; pkill -f 'vite'

To explore via terminal:
  uv tool install ./packages/attacker     # then 'pna --help'
  uv tool install ./packages/shell_coach  # then 'psh lessons'
  uv tool install ./packages/operator     # then 'pno --help'

EOF
