# Entry points for running and checking the Modellbahn-Shop. `make` lists all targets.
# Stack targets use Docker Compose; quality targets run uv (backend) and npm (frontend) locally.

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help
# Several targets write files that others read (openapi, client, check-contract); keep the order.
.NOTPARALLEL:
MAKEFLAGS += --no-print-directory

COMPOSE ?= docker compose
BACKEND := backend
FRONTEND := frontend
OPENAPI := $(FRONTEND)/openapi.json
GENERATED_CLIENT := $(FRONTEND)/src/lib/api/generated
# Written by npm on every install, so it is newer than package-lock.json after `npm ci`.
NODE_MODULES := $(FRONTEND)/node_modules/.package-lock.json

EXPORT_OPENAPI = cd $(BACKEND) && uv run python -m modellbahn.cli export-openapi --output ../$(OPENAPI)
GENERATE_CLIENT = cd $(FRONTEND) && npm run client

# make logs [SERVICE=worker]
SERVICE ?=
# make staff EMAIL=... NAME="..." [ROLE=owner|staff|packer]
ROLE ?= owner

.PHONY: help up down logs dev-db test lint fmt typecheck migrate openapi client staff check \
	check-build check-contract check-compose

help: ## Diese Übersicht
	@awk 'BEGIN { FS = ":.*## " } /^[a-z-]+:.*## / { printf "  %-10s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# Compose needs .env to resolve docker-compose.yml, even for `down` and `logs`.
.env:
	cp .env.example .env
	@echo "Hinweis: .env aus .env.example angelegt. Die Werte taugen nur für die lokale Entwicklung."

# Frontend dependencies are (re)installed whenever package-lock.json has changed.
$(NODE_MODULES): $(FRONTEND)/package-lock.json
	cd $(FRONTEND) && npm ci
	touch $@

# --- Stack ------------------------------------------------------------------------------

up: .env ## Gesamten Stack bauen und starten (https://localhost)
	$(COMPOSE) up --detach --build --wait
	@echo
	@echo "  Shop:     https://localhost"
	@echo "  Admin:    https://localhost/admin   (Zugang: make staff EMAIL=... NAME=\"...\")"
	@echo "  Mailpit:  http://localhost:8025"

down: .env ## Stack stoppen (Daten bleiben erhalten)
	$(COMPOSE) down

logs: .env ## Logs verfolgen; nur ein Dienst: make logs SERVICE=worker
	$(COMPOSE) logs --follow --tail=100 $(SERVICE)

dev-db: .env ## Nur Datenbank und Mailpit starten (Entwicklung ohne Docker)
	$(COMPOSE) up --detach --wait db mailpit

migrate: .env ## Migrationen auf die Datenbank im Stack anwenden
	$(COMPOSE) run --rm --build migrate

# The values travel as environment variables, so quotes in a name cannot break the command.
staff: export STAFF_EMAIL = $(EMAIL)
staff: export STAFF_NAME = $(NAME)
staff: export STAFF_ROLE = $(ROLE)
staff: .env ## Mitarbeiterkonto anlegen: make staff EMAIL=... NAME="..." [ROLE=owner]
	$(if $(and $(EMAIL),$(NAME)),,$(error Aufruf: make staff EMAIL=chef@example.de NAME="Vorname Nachname" [ROLE=owner|staff|packer]))
	$(COMPOSE) run --rm api python -m modellbahn.cli create-staff \
		--email "$$STAFF_EMAIL" --name "$$STAFF_NAME" --role "$$STAFF_ROLE"

# --- Code quality -----------------------------------------------------------------------

test: $(NODE_MODULES) ## Tests von Backend und Frontend
	cd $(BACKEND) && uv run pytest
	cd $(FRONTEND) && npm test

lint: $(NODE_MODULES) ## Linter, Formatprüfung und Architekturregeln
	cd $(BACKEND) && uv run ruff check
	cd $(BACKEND) && uv run ruff format --check
	cd $(BACKEND) && uv run lint-imports
	cd $(FRONTEND) && npm run lint

fmt: $(NODE_MODULES) ## Code formatieren und automatisch behebbare Lint-Fehler beheben
	cd $(BACKEND) && uv run ruff check --fix
	cd $(BACKEND) && uv run ruff format
	cd $(FRONTEND) && npm run lint -- --fix

typecheck: $(NODE_MODULES) ## Typprüfung (mypy --strict, tsc)
	cd $(BACKEND) && uv run mypy src tests
	cd $(FRONTEND) && npm run typecheck

openapi: ## OpenAPI-Schema des Backends nach frontend/openapi.json exportieren
	$(EXPORT_OPENAPI)

client: openapi $(NODE_MODULES) ## API-Client des Frontends aus dem OpenAPI-Schema erzeugen
	$(GENERATE_CLIENT)

# Like CI, the checks must not silently rewrite uv.lock.
check: export UV_LOCKED := 1
check: lint typecheck test check-build check-contract check-compose ## Alles, was die CI prüft

check-build: $(NODE_MODULES)
	cd $(FRONTEND) && npm run build

# Regenerates schema and client and fails if that changed anything in the working tree.
check-contract: $(NODE_MODULES)
	@snapshot="$$(mktemp -d)"; trap 'rm -rf "$$snapshot"' EXIT; \
	cp $(OPENAPI) "$$snapshot/openapi.json"; \
	cp -R $(GENERATED_CLIENT) "$$snapshot/generated"; \
	($(EXPORT_OPENAPI)); \
	($(GENERATE_CLIENT)); \
	if ! diff -u "$$snapshot/openapi.json" $(OPENAPI) \
		|| ! diff -ru "$$snapshot/generated" $(GENERATED_CLIENT); then \
		echo "openapi.json oder der API-Client waren veraltet und wurden neu erzeugt: prüfen und committen." >&2; \
		exit 1; \
	fi

# Compose file, Caddyfile and both images, exactly as in the CI job "compose".
check-compose:
	$(COMPOSE) --env-file .env.example config --quiet
	docker run --rm --volume "$(CURDIR)/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2-alpine \
		caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
	$(COMPOSE) --env-file .env.example build
