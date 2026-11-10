#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
. ./.env.local
set +a

args=(--user "$CLICKHOUSE_USER")
if [[ -n "${CLICKHOUSE_PASSWORD:-}" ]]; then
  args+=(--password "$CLICKHOUSE_PASSWORD")
fi

exec docker compose --env-file .env.local exec -T clickhouse \
  clickhouse-client "${args[@]}" "$@"
