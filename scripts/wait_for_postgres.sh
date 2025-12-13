#!/usr/bin/env bash
set -euo pipefail

# Wait for Postgres to be ready if DATABASE_URL references it (simple parsing)
DB_URL=${DATABASE_URL:-}

parse_postgres() {
  # try to extract host and port from DATABASE_URL like postgresql+asyncpg://user:pass@host:port/db
  if [[ "$DB_URL" =~ @([^:/]+)(:([0-9]+))?/ ]]; then
    HOST="${BASH_REMATCH[1]}"
    PORT="${BASH_REMATCH[3]:-5432}"
    return 0
  fi
  return 1
}

if parse_postgres; then
  echo "Detected Postgres host: $HOST, port: $PORT"
else
  if [[ -n "${POSTGRES_HOST:-}" ]]; then
    HOST=${POSTGRES_HOST}
    PORT=${POSTGRES_PORT:-5432}
    echo "Using POSTGRES_HOST: $HOST:$PORT"
  else
    # No postgres configured — nothing to wait for
    exit 0
  fi
fi

ATTEMPTS=30
SLEEP_SEC=2
for i in $(seq 1 $ATTEMPTS); do
  if command -v pg_isready >/dev/null 2>&1; then
    if pg_isready -h "$HOST" -p "$PORT" -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1; then
      echo "Postgres is available at $HOST:$PORT"
      exit 0
    fi
  else
    # Fallback: try to open TCP socket
    if (echo > /dev/tcp/$HOST/$PORT) >/dev/null 2>&1; then
      echo "Postgres TCP port $HOST:$PORT is reachable"
      exit 0
    fi
  fi
  echo "Waiting for Postgres at $HOST:$PORT... ($i/$ATTEMPTS)"
  sleep $SLEEP_SEC
done

echo "Postgres did not become available in time" >&2
exit 1
