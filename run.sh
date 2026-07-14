#!/usr/bin/env bash
# Convenience launcher: starts backend + frontend together.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# --- backend ---
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] || cp .env.example .env
./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# --- frontend ---
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
npm run dev &
FRONTEND_PID=$!

echo "Backend  PID $BACKEND_PID  (http://localhost:8000)"
echo "Frontend PID $FRONTEND_PID (http://localhost:5173)"
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
