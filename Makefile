.PHONY: setup lint test dist testbed-up testbed-down testbed-seed testbed-load

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
