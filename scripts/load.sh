#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
. ./.env.local
set +a

tables=(dim_realty dim_gauges dim_tariffs dim_users fact_gauge_bindings fact_meter_readings fact_invoice)

args=(--user "$CLICKHOUSE_USER" --database "$CLICKHOUSE_DATABASE")
if [[ -n "${CLICKHOUSE_PASSWORD:-}" ]]; then
  args+=(--password "$CLICKHOUSE_PASSWORD")
fi

echo "Truncating tables before load (make load is idempotent)..."
docker compose --env-file .env.local exec -T clickhouse \
  clickhouse-client "${args[@]}" --multiquery < sql/truncate.sql

for table in "${tables[@]}"; do
  file="data/${table}.csv"
  if [[ ! -f "$file" ]]; then
    echo "Missing dataset $file, run 'make gen' first" >&2
    exit 1
  fi
  echo "Loading ${table} from ${file}..."
  docker compose --env-file .env.local exec -T clickhouse \
    clickhouse-client "${args[@]}" \
    --query "INSERT INTO ${table} FORMAT CSVWithNames" < "$file"
done

echo "All datasets loaded into ${CLICKHOUSE_DATABASE}."
