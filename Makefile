.PHONY: run rund services stop clean wait gen load schema setup teardown logs

.DEFAULT_GOAL = run

# Runs all services in detached mode.
run:
	docker compose --env-file .env.local up -d --build

# Runs all services without detached mode (for debugging).
rund:
	docker compose --env-file .env.local up --build

# Shows all service statuses.
services:
	docker compose --env-file .env.local ps

# Stops all running services.
stop:
	docker compose --env-file .env.local down

# Cleans up all resources including volumes.
clean:
	docker compose --env-file .env.local down -v

# Waits until ClickHouse answers on the published HTTP port.
wait:
	@set -a; . ./.env.local; set +a; \
	echo "Waiting for ClickHouse at $$CLICKHOUSE_HOST:$$CLICKHOUSE_HTTP_PORT..."; \
	for i in $$(seq 1 60); do \
		if curl -fsS "http://$$CLICKHOUSE_HOST:$$CLICKHOUSE_HTTP_PORT/ping" 2>/dev/null | grep -q '^Ok\.$$'; then \
			echo "ClickHouse is ready"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "ClickHouse did not become ready in 60 seconds" >&2; \
	exit 1

# Generates all CSV datasets in data/.
gen:
	python3 scripts/generate.py

# Creates the database and tables.
schema: wait
	./scripts/ch.sh --multiquery < sql/schema.sql

# Loads the CSV datasets into ClickHouse.
load: wait
	./scripts/load.sh

# Creates the schema, generates the datasets and loads them.
setup: wait
	./scripts/ch.sh --multiquery < sql/schema.sql
	$(MAKE) gen
	./scripts/load.sh

# Drops the database with all tables and data.
teardown: wait
	./scripts/ch.sh --multiquery < sql/teardown.sql

# Shows service logs.
logs:
	docker compose --env-file .env.local logs
