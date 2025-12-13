#!/usr/bin/env bash
set -euo pipefail

# Script to migrate SQLite (data.db) -> Postgres using pgloader (Docker).
# Usage: ./scripts/sqlite_to_postgres.sh

if [ -f .env.production ]; then
  set -a
  . .env.production
  set +a
fi

POSTGRES_USER=${POSTGRES_USER:-secret}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-secret}
POSTGRES_DB=${POSTGRES_DB:-secret_santa}

if [ ! -f data.db ]; then
  echo "SQLite file data.db not found in current directory"
  exit 1
fi

echo "Migrating data.db -> postgres://${POSTGRES_USER}:****@postgres:5432/${POSTGRES_DB}"

# Find the docker network name where 'postgres' service is running
NETNAME=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -q postgres | xargs -r docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')
if [ -z "$NETNAME" ]; then
  echo "Could not determine Docker network for postgres. Is the postgres container running?"
  exit 1
fi

docker run --rm --network "$NETNAME" -v "$(pwd):/work" dpage/pgloader:latest \
  pgloader /work/data.db postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

echo "Migration finished. Please check the DB and run alembic upgrade head if necessary."
