# Nightshift — single entry point across the Python and TypeScript toolchains.
#
# A developer should never need to know which directory a thing lives in.
# Every target here is runnable from the repo root and nowhere else.

.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

API_DIR   := services/api
WEB_DIR   := apps/web
VENV      := $(API_DIR)/.venv
PY        := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
PYTEST    := $(VENV)/bin/pytest
RUFF      := $(VENV)/bin/ruff
MYPY      := $(VENV)/bin/mypy
ALEMBIC   := $(VENV)/bin/alembic
ARQ       := $(VENV)/bin/arq
COMPOSE   := docker compose --env-file .env -f infra/docker-compose.yml
PYTHON    ?= python3.12

# Alembic and the seed CLI need the .env values; the API/worker load them via
# pydantic-settings. `set -a` exports every assignment so child processes see them.
LOADENV := set -a && source .env && set +a

.PHONY: help setup up down migrate migrate-down seed dev demo test test-py test-web \
        test-e2e check fmt lint typecheck reset-db ingest logs ps clean doctor \
        verify acceptance test-e2e-seeded browsers drift constraints \
        discover registry-validate registry-approve registry-approve-write coverage \
        worksheets

help: ## Show available targets
	@echo "Nightshift — make targets"
	@echo
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "First run:  make setup && make demo"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

.env:
	@cp .env.example .env
	@echo "created .env from .env.example"

$(VENV)/.installed: $(API_DIR)/pyproject.toml
	@echo "==> python deps"
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install --quiet -e "$(API_DIR)[dev]"
	@touch $@

$(WEB_DIR)/node_modules/.installed: $(WEB_DIR)/package.json
	@echo "==> js deps"
	@cd $(WEB_DIR) && npm install --silent --no-audit --no-fund
	@touch $@

setup: .env $(VENV)/.installed $(WEB_DIR)/node_modules/.installed model ## Install JS + Python deps, fetch the embedding model, create .env
	@echo "==> setup complete. next: make demo"

# ~130 MB, downloaded once (AMENDMENTS A5). Kept inside `setup` rather than in
# the test targets — unlike Playwright's browser, the product itself needs this,
# and `make demo` must work offline afterwards.
model: $(VENV)/.installed ## Download the local embedding model
	@cd $(API_DIR) && ../../$(PY) -c "\
	from nightshift.domain.embeddings import FastEmbedEmbedder, cache_dir, real_model_available; \
	print('==> embedding model already present at', cache_dir()) if real_model_available() else \
	(FastEmbedEmbedder().embed(['warm the cache']), print('==> embedding model ready at', cache_dir()))"

doctor: ## Check that required tooling is present
	@$(PYTHON) scripts/doctor.py

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

up: .env ## Start postgres + redis, wait for healthy
	@$(COMPOSE) up -d --wait
	@echo "==> postgres and redis healthy"

down: ## Stop containers
	@$(COMPOSE) down

ps: ## Show container status
	@$(COMPOSE) ps

logs: ## Tail container logs
	@$(COMPOSE) logs -f

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

migrate: setup ## Alembic upgrade head
	@$(LOADENV) && cd $(API_DIR) && ../../$(ALEMBIC) upgrade head

migrate-down: setup ## Alembic downgrade one revision
	@$(LOADENV) && cd $(API_DIR) && ../../$(ALEMBIC) downgrade -1

seed: setup ## Load fixture data (dev user, sources, companies, jobs)
	@$(LOADENV) && $(PY) -m nightshift.cli seed

reset-db: ## Drop, recreate, migrate, seed
	@$(COMPOSE) down -v
	@$(MAKE) up migrate seed

# The one CI assertion that had no local counterpart, and it cost a session to
# notice. On 2026-08-05 the migrations job went red on a branch that had touched
# no migration; no `make` target could reproduce it, because nothing local ever
# compared the models against a live schema. This is that comparison.
#
# Not part of `make check`, which must run without a database. It runs inside
# `make acceptance`, which has already brought a migrated stack up.
drift: setup ## Assert the models have not drifted from the migrations
	@$(LOADENV) && cd $(API_DIR) && \
	trap 'rm -f migrations/versions/*drift_probe.py' EXIT; \
	../../$(ALEMBIC) revision --autogenerate -m drift_probe --rev-id drift_probe > /dev/null; \
	if grep -qE '^[[:space:]]+op\.(create|drop|alter|add)' migrations/versions/*drift_probe.py; then \
	  echo "==> the models have drifted from the migrations:"; \
	  grep -E '^[[:space:]]+op\.' migrations/versions/*drift_probe.py; \
	  exit 1; \
	fi; \
	echo "==> no model/migration drift"

# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

dev: setup ## Web + API + worker, concurrently
	@$(LOADENV) && $(PY) scripts/dev.py

demo: ## up && migrate && seed && dev — fully offline, no network
	@$(MAKE) up
	@$(MAKE) migrate
	@$(MAKE) seed
	@$(MAKE) dev

ingest: setup ## Run one live ingestion pass (requires OUTBOUND_HTTP_ENABLED=true)
	@$(LOADENV) && $(PY) -m nightshift.cli ingest

# ---------------------------------------------------------------------------
# Board discovery (M1c)
#
# Three targets, run by a human, never scheduled (A1, ADR 0006). They form a
# chain that only a person can advance: discover writes candidates,
# registry-validate asks the providers what they are, registry-approve prints
# what it *would* promote. `registry-approve` is dry-run on purpose — a target
# that edits a committed file deciding which employers this product can see
# should need an extra word typed at it.
# ---------------------------------------------------------------------------

discover: setup ## Harvest board candidates from the committed crawl fixture (offline)
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli discover --provider ashby

registry-validate: setup ## Probe candidates and classify them (requires OUTBOUND_HTTP_ENABLED=true)
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli validate

registry-approve: setup ## Show the approval report; nothing is written
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli approve

registry-approve-write: setup ## Actually promote approved candidates, then commit the diff yourself
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli approve --write

coverage: setup ## Print what is covered and, more to the point, what is not
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli coverage

# Both labeling worksheets. Neither reads the database or the network — they are
# built from the committed fixture corpus — and both preserve every answer
# already filled in, so this is safe to run at any time.
worksheets: setup ## Regenerate the eligibility and relevance labeling worksheets
	@$(PY) scripts/make_label_worksheet.py
	@$(PY) scripts/make_relevance_worksheet.py

verify: setup ## Assert the stack actually works, and exit with a status code
	@$(LOADENV) && $(PY) scripts/verify.py

# `demo` ends in a foreground dev server, which is right for a human and
# impossible to check the exit code of. `acceptance` is the scriptable path:
# it brings the stack up, seeds it, proves it, and exits.
#
# `verify` covers the API and the database; `test-e2e-seeded` covers the one
# criterion neither can reach — that the jobs actually render in a browser.
acceptance: ## up && migrate && drift && seed && verify && seeded e2e — the acceptance run
	@$(MAKE) up
	@$(MAKE) migrate
	@$(MAKE) drift
	@$(MAKE) seed
	@$(MAKE) verify
	@$(MAKE) test-e2e-seeded

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

fmt: setup ## Format both languages
	@$(RUFF) format $(API_DIR)
	@$(RUFF) check --fix-only --quiet $(API_DIR)
	@cd $(WEB_DIR) && npm run --silent fmt

lint: setup ## Lint both languages
	@$(RUFF) format --check $(API_DIR)
	@$(RUFF) check $(API_DIR)
# The web formatter is checked here, not only in CI. Until M1b it was not, so
# `make check` passed on unformatted TypeScript and the `web` job failed on the
# push: the Python side had `ruff format --check` and the web side had only
# eslint. A formatting rule no local command runs is a rule CI enforces alone,
# which is the exact gap M0's CI session cost five defects to learn about.
	@cd $(WEB_DIR) && npm run --silent fmt:check
	@cd $(WEB_DIR) && npm run --silent lint

typecheck: setup ## mypy + tsc
	@cd $(API_DIR) && ../../$(MYPY) nightshift
	@cd $(WEB_DIR) && npm run --silent typecheck

test: test-py test-web ## Unit tests, both languages

test-py: setup ## Python unit tests
	@cd $(API_DIR) && ../../$(PYTEST) -q

test-web: setup ## Web unit tests
	@cd $(WEB_DIR) && npm run --silent test

# Playwright ships its browser separately from its npm package, and bumps the
# required build on minor upgrades. Left to `make setup` it would put a ~100MB
# download in front of every first run, so it lives here: the e2e targets
# provision it, and `npm exec playwright install` is a no-op once satisfied.
browsers: $(WEB_DIR)/node_modules/.installed
	@cd $(WEB_DIR) && npm exec --silent -- playwright install chromium

test-e2e: setup browsers ## Playwright, with no API behind it (the degraded path)
	@cd $(WEB_DIR) && npm run --silent test:e2e

# Needs a seeded stack. Separate from `test-e2e` because it has real
# prerequisites; run it via `make acceptance`, which guarantees them.
test-e2e-seeded: setup browsers ## Playwright against a seeded stack (acceptance row 5)
	@$(LOADENV) && cd $(WEB_DIR) && npm run --silent test:e2e:seeded

check: lint typecheck test ## format + lint + typecheck + test. Run before every commit.
	@echo "==> check passed"

# ADR 0016. Only needed when services/api/pyproject.toml changes, or when the
# scheduled canary reports a drift worth taking. Needs docker and the network —
# it resolves on linux because the developer's machine cannot stand in for a
# runner; see the comment at the top of the script.
constraints: ## Regenerate CI's pinned dependency set (needs docker + network)
	@./scripts/regenerate_constraints.sh

clean: ## Remove build artifacts and virtualenvs
	@rm -rf $(VENV) $(WEB_DIR)/node_modules $(WEB_DIR)/.next
	@find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
