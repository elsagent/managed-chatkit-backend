#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root (where package.json is), but point Python to backend/
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[backend] Installing backend deps..."
python -m pip install --upgrade pip

# Install deps (no editable install)
if [ -f "backend/requirements.txt" ]; then
  pip install -r backend/requirements.txt
elif [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
else
  echo "[backend] ERROR: requirements.txt not found."
  exit 1
fi

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"

echo "[backend] Starting uvicorn on ${HOST}:${PORT} ..."
# ✅ Key fix: --app-dir backend so import "app.main:app" works
exec uvicorn app.main:app --app-dir backend --host "${HOST}" --port "${PORT}" --reload
