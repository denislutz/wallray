#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FE="$ROOT/fe"

# ── Deps ──────────────────────────────────────────────────────────────────────
if [[ ! -d "$FE/node_modules" ]]; then
  echo "→ node_modules not found, running pnpm install..."
  cd "$FE" && pnpm install
fi

# ── Start ─────────────────────────────────────────────────────────────────────
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/fe.log"
echo "→ Starting Next.js on http://localhost:${FE_PORT:-3000} (log: logs/fe.log)"
cd "$FE" && pnpm dev --port "${FE_PORT:-3000}" 2>&1 | tee -a "$LOG"
