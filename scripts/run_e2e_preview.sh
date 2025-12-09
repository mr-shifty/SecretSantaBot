#!/usr/bin/env bash
set -euo pipefail

# Helper: apply alembic migrations and run preview scripts
# Usage: ./scripts/run_e2e_preview.sh [--docker]

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

USE_DOCKER=0
if [[ "${1:-}" == "--docker" ]]; then
  USE_DOCKER=1
fi

if [[ "$USE_DOCKER" -eq 1 ]]; then
  echo "Running migrations inside docker and executing preview script"
  docker compose run --rm secret_santa_bot alembic upgrade head
  docker compose run --rm secret_santa_bot python3 scripts/run_draw_and_preview.py
else
  echo "Running migrations locally and executing preview script"
  alembic upgrade head
  python3 scripts/run_draw_and_preview.py
fi

echo "E2E preview finished"
