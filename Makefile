.PHONY: test lint kickstart packer-validate packer-build vm-up vm-down provision-test ova \
	up down ps logs health seed fields render hunt playbooks audit

VM_NAME := ai-dfir-node-test
SSH_KEY := $(HOME)/.ssh/ai_dfir_node_test_ed25519

test: lint
	@echo "== attack-mcp tests ==" && cd mcp-servers/attack-mcp && .venv/bin/python -m pytest -q
	@echo "== arkime-mcp tests ==" && cd mcp-servers/arkime-mcp && .venv/bin/python -m pytest -q
	@echo "== skills render tests ==" && python3 -m pytest skills/tests -q
	@echo "== script tests ==" && bash scripts/tests/test-node-status.sh && bash scripts/tests/test-backup.sh

lint:
	@echo "== shellcheck ==" && shellcheck scripts/*.sh scripts/tests/*.sh scripts/tests/stubs/*
	@echo "== ansible-lint ==" && cd ansible && ansible-lint
	@echo "== ansible syntax-check ==" && cd ansible && ansible-playbook -i inventory/test.ini site.yml --syntax-check

kickstart:
	scripts/render-kickstart.sh

packer-validate: kickstart
	cd packer && packer validate $(PACKER_VARS) .

packer-build: kickstart
	cd packer && packer build $(PACKER_VARS) .

vm-up:
	scripts/tests/vm-up.sh $(VM_NAME) $(SSH_KEY)

vm-down:
	scripts/tests/vm-down.sh $(VM_NAME)

provision-test:
	cd ansible && ansible-playbook -i inventory/test.ini site.yml

ova:
	scripts/ova-postprocess.sh

# ---------------------------------------------------------------------------
# Minimal Docker build (docker-compose.minimal.yml). Independent of the Packer/
# Ansible appliance targets above -- see SETUP.md. The `minimal` branch carries
# the same stack with the appliance tooling stripped out.
# ---------------------------------------------------------------------------
COMPOSE := docker compose -f docker-compose.minimal.yml --env-file .env.minimal
PLAYBOOK ?= network-beaconing
WINDOW   ?= 24h
N        ?= 20

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

health:
	@printf 'llama-server  ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8080/health
	@printf 'llm-queue     ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8090/healthz
	@printf 'audit-proxy   ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8001/healthz
	@printf 'open-webui    ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:3000/

fields:
	@set -a && . ./.env.minimal && set +a && python3 scripts/gen-field-reference.py

render:
	python3 skills/render.py

seed:
	@SEED_EMAIL="$(SEED_EMAIL)" SEED_PASSWORD="$(SEED_PASSWORD)" python3 scripts/seed-openwebui.py

playbooks:
	@python3 scripts/dfir-hunt.py --list-playbooks

hunt:
	python3 scripts/dfir-hunt.py --playbook $(PLAYBOOK) --window $(WINDOW) --verbose

audit:
	@curl -s "http://127.0.0.1:8001/audit?limit=$(N)" | \
	  python3 -c 'import json,sys; [print("%s  %-14s %-14s %s" % (c["ts"], c["server"], c["tool"], (c["arguments"] or "")[:80])) for c in json.load(sys.stdin)["calls"]]'
