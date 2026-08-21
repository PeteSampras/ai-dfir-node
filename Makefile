# Minimal AI DFIR node -- Docker-only build.
# The full Packer/Ansible appliance build lives on the `main` branch.
.PHONY: up down build ps logs restart test render hunt playbooks audit health seed fields

COMPOSE := docker compose -f docker-compose.minimal.yml --env-file .env.minimal
PLAYBOOK ?= network-beaconing
WINDOW   ?= 24h
N        ?= 20

up:            ## build if needed and start the whole stack
	$(COMPOSE) up -d --build

down:          ## stop the stack (named volumes, and so chat/queue/audit data, survive)
	$(COMPOSE) down

build:
	$(COMPOSE) build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

restart:
	$(COMPOSE) restart

health:        ## quick reachability check of every published endpoint
	@printf 'llama-server  ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8080/health
	@printf 'llm-queue     ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8090/healthz
	@printf 'audit-proxy   ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8001/healthz
	@printf 'open-webui    ' ; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:3000/

seed:          ## create admin, register the tool server, import playbooks as /commands
	@SEED_EMAIL="$(SEED_EMAIL)" SEED_PASSWORD="$(SEED_PASSWORD)" python3 scripts/seed-openwebui.py

test:          ## skill-library render tests (needs pytest; see README if unavailable)
	python3 -m pytest skills/tests -q

fields:        ## regenerate the Elasticsearch field reference from the live cluster
	@set -a && . ./.env.minimal && set +a && python3 scripts/gen-field-reference.py

render:        ## regenerate skills/rendered/ for Open WebUI + opencode
	python3 skills/render.py

playbooks:     ## list available playbooks
	@python3 scripts/dfir-hunt.py --list-playbooks

hunt:          ## run one playbook: make hunt PLAYBOOK=host-baseline WINDOW=7d
	python3 scripts/dfir-hunt.py --playbook $(PLAYBOOK) --window $(WINDOW) --verbose

audit:         ## show the most recent AI tool calls: make audit N=50
	@curl -s "http://127.0.0.1:8001/audit?limit=$(N)" | \
	  python3 -c 'import json,sys; [print("%s  %-14s %-14s %s" % (c["ts"], c["server"], c["tool"], (c["arguments"] or "")[:80])) for c in json.load(sys.stdin)["calls"]]'
