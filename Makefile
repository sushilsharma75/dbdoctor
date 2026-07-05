.PHONY: setup lint test dist audit-local testbed-up testbed-down testbed-seed testbed-load

PG_DSN ?= postgresql://dbdoctor:dbdoctor@127.0.0.1:15432/shop
MYSQL_DSN ?= mysql://dbdoctor:dbdoctor@127.0.0.1:13306/shop

# --- development -------------------------------------------------------------

setup:  ## create .venv and install all dependency groups
	uv sync --group dev --group testbed

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest

dist:  ## build shippable single-file collector artifacts + checksums
	uv run python tools/build_dist.py

audit-local:  ## collector -> engine -> findings table, straight off the testbed
	mkdir -p out
	uv run python collector/pg_collect.py --dsn "$(PG_DSN)" --out out/pg_snapshot.json
	uv run python collector/mysql_collect.py --dsn "$(MYSQL_DSN)" --out out/mysql_snapshot.json
	uv run python -m cli.audit_local out/pg_snapshot.json out/mysql_snapshot.json

# --- testbed (see testbed/README.md) ----------------------------------------

testbed-up:  ## start PG15 + MySQL8 with slow-query instrumentation enabled
	docker compose -f testbed/docker-compose.yml up -d --wait

testbed-down:
	docker compose -f testbed/docker-compose.yml down -v

testbed-seed:  ## create the ecommerce schema and bulk rows in all three DBs
	uv run python testbed/seed/seed.py
	MYSQL_PORT=13307 uv run python testbed/seed/seed.py --engine mysql

testbed-load:  ## run the mixed problem workload (default 3 minutes)
	uv run python testbed/seed/workload.py --minutes $(or $(MINUTES),3)
