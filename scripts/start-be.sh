#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BE="$ROOT/be"

# ── Env file ──────────────────────────────────────────────────────────────────
if [[ ! -f "$ROOT/.env.local" ]]; then
  echo "⚠  .env.local not found — copy .env.local.example and fill in secrets"
  echo "   cp .env.local.example .env.local"
  exit 1
fi

# ── Venv ──────────────────────────────────────────────────────────────────────
if [[ ! -d "$BE/.venv" ]]; then
  echo "→ No venv found, running uv sync..."
  cd "$BE" && uv sync
fi

# ── Start ─────────────────────────────────────────────────────────────────────
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/be.log"
echo "→ Starting FastAPI on http://localhost:${API_PORT:-8000} (log: logs/be.log)"
cd "$BE" && uv run uvicorn app.main:app \
  --reload \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}" \
  2>&1 | tee -a "$LOG"
