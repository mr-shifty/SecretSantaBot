#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/backup_postgres.sh backup.sql
OUTFILE=${1:-backup.sql}
# Source .env.production if exists
if [ -f .env.production ]; then
  # export variables from file (simple parsing)
  set -a
  . .env.production
  set +a
fi

if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_DB:-}" ]; then
  echo "Please set POSTGRES_USER and POSTGRES_DB environment variables (or provide via .env.production)"
  exit 1
fi

echo "Creating backup to ${OUTFILE}..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" > "${OUTFILE}"
echo "Backup saved to ${OUTFILE}"
