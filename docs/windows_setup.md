# Windows setup (and running without uv)

Two problems this guide solves:

1. **`uv sync` fails downloading Python from Astral.** On corporate Windows,
   `astral.sh` / the `python-build-standalone` CDN is often blocked. uv tries
   to download its *own* Python interpreter and hangs or errors.
2. **You want to avoid uv entirely** and use plain `pip` + `venv`.

Package downloads (from PyPI) are usually *not* blocked — only the interpreter
download is. So the fix is simply to make the tooling use the Python already
installed on your machine.

---

## Prerequisite: install Python 3.12+

Install from <https://www.python.org/downloads/> (not blocked). Verify:

```bat
py -3.12 --version
```

---

## Option A — keep using uv (recommended)

The repo now pins `python-downloads = "never"` in `pyproject.toml`, so uv will
use your system Python and never contact Astral. Just run:

```bat
uv sync --group dev --group testbed
```

If you are on an older checkout without that setting, force it per-command:

```bat
set UV_PYTHON_DOWNLOADS=never
uv sync --group dev --group testbed
```

(PowerShell: `$env:UV_PYTHON_DOWNLOADS = "never"`)

If uv still can't find your interpreter, point it at the exact path once:

```bat
uv python pin 3.12
```

---

## Option B — plain pip + venv (no uv)

### One-time setup (replaces `make setup`)

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip

:: install the project + all runtime dependencies from pyproject.toml
pip install -e .

:: dev group (tests + lint) and testbed group (mysql driver)
pip install pytest ruff httpx pymysql

:: browser used for PDF rendering (optional; audits still work without it)
python -m playwright install chromium
```

`pip install -e .` reads `[project].dependencies`, so it pulls in fastapi,
sqlalchemy, psycopg[binary], playwright, pydantic, and everything else. The
extra `pip install` line covers the `dev` and `testbed` dependency groups,
which classic pip does not install automatically.

> Modern pip (25.1+) can read the groups directly instead of listing them:
> `pip install -e . --group dev --group testbed`

Once the venv is activated (`.venv\Scripts\activate`), drop the `uv run`
prefix from every command — the tools are on your PATH.

### make target → pip/venv equivalent

Activate the venv first (`.venv\Scripts\activate`), then:

| make target       | Windows command (venv active)                                             |
|-------------------|---------------------------------------------------------------------------|
| `make lint`       | `ruff check .`  then  `ruff format --check .`                             |
| `make test`       | `pytest`                                                                   |
| `make dist`       | `python tools\build_dist.py`                                              |
| `make report-sample` | see block below                                                        |
| `make audit-local`   | see block below                                                        |
| `make testbed-up`    | `docker compose -f testbed\docker-compose.yml up -d --wait`            |
| `make testbed-down`  | `docker compose -f testbed\docker-compose.yml down -v`                 |
| `make testbed-seed`  | `python testbed\seed\seed.py`  then  `set MYSQL_PORT=13307 && python testbed\seed\seed.py --engine mysql` |
| `make testbed-load`  | `python testbed\seed\workload.py --minutes 3`                          |

**`make report-sample`** (sample PDF bundles from committed fixtures):

```bat
dbdoctor-audit --snapshot fixtures\pg_full.json --client-alias "Sample Co (PG)" --out out\sample_pg --skip-ai
dbdoctor-audit --snapshot fixtures\mysql_full.json --client-alias "Sample Co (MySQL)" --out out\sample_mysql --skip-ai
copy out\sample_pg\report.pdf out\sample_pg.pdf
copy out\sample_mysql\report.pdf out\sample_mysql.pdf
```

`dbdoctor-audit` is installed as a console script by `pip install -e .`. If it
isn't on PATH, use `python -m cli.audit` with the same arguments.

**`make audit-local`** (collector → engine → findings, off the testbed):

```bat
mkdir out
python collector\pg_collect.py --dsn "postgresql://dbdoctor:dbdoctor@127.0.0.1:15432/shop" --out out\pg_snapshot.json
python collector\mysql_collect.py --dsn "mysql://dbdoctor:dbdoctor@127.0.0.1:13306/shop" --out out\mysql_snapshot.json
python -m cli.audit_local out\pg_snapshot.json out\mysql_snapshot.json
```

### Notes

- **Path separators:** the table uses `\` for Windows. In PowerShell, `/` also
  works if you prefer.
- **Env vars inline:** `cmd` uses `set VAR=value && command`; PowerShell uses
  `$env:VAR="value"; command`.
- **Backend dev server** (not a make target, handy to know):
  `uvicorn webapp.backend.app.main:app --reload` — or with uv,
  `uv run uvicorn webapp.backend.app.main:app --reload`.
- **The collectors need only stdlib + one DB driver.** A customer running
  `pg_collect.py` / `mysql_collect.py` on their own machine needs just
  `pip install "psycopg[binary]"` or `pip install pymysql` — not this whole
  dev environment.
