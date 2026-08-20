.PHONY: test lint packer-validate packer-build vm-up vm-down provision-test ova

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

packer-validate:
	cd packer && packer validate $(PACKER_VARS) .

packer-build:
	cd packer && packer build $(PACKER_VARS) .

vm-up:
	scripts/tests/vm-up.sh $(VM_NAME) $(SSH_KEY)

vm-down:
	scripts/tests/vm-down.sh $(VM_NAME)

provision-test:
	cd ansible && ansible-playbook -i inventory/test.ini site.yml

ova:
	scripts/ova-postprocess.sh
