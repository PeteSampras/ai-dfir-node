# Manual Validation Runbook

Maps spec §10's six success criteria to what's actually been verified so
far vs. what remains. **Status as of this writing: all role/script/server
file content is written and internally consistent (ansible-lint clean at
the `production` profile, `make test` green — 25 automated tests), but
ZERO live verification against a booted VM has happened yet.** This
workstation has no root access to install Packer/QEMU-KVM (needed to build
and boot the local test VM this plan's design relies on for proof), so the
"run the whole stack against a real Rocky 9 instance" step described
throughout `docs/plans/2026-08-20-ai-dfir-node.md` is still pending. This
document will be updated with real results once that unblocks.

## 1. "OVA imports into ESXi, boots, node-status green, nvidia-smi shows the L4"

- **Written, not yet verified even locally:** the OVA build pipeline
  (`scripts/ova-postprocess.sh` + `scripts/ovf-template.xml.j2`) exists but
  has not been run — it needs `qemu-img` (also blocked on sudo) and a real
  provisioned qcow2 from the test VM, neither of which exist yet.
- **Remains manual:** everything — local test-VM boot, OVA build, ESXi
  import, GPU passthrough, `node-status.sh` all-green. Follow
  `esxi-import.md` then `gpu-passthrough.md` once the local pipeline has
  been proven first.

## 2. "From a laptop browser: chat with muse glimmer; get real Zeek/Suricata results back"

- **Written, not yet verified:** nginx/Open WebUI/mcpo/attack-mcp quadlets
  and configs are all written and lint-clean, but no container has ever
  actually been built or started — that requires podman on a real Rocky 9
  host, which only exists once the test VM boots.
- **Remains manual:** local test-VM proof first (nginx→Open WebUI→mcpo→
  attack-mcp chain live, mcpo's OpenAPI translation of a real MCP server
  confirmed), then with the GPU attached and `elasticsearch_configured:
  true`, a real chat session against a live model and live ES.

## 3. "From VS Code Remote-SSH: opencode pulls a PCAP slice via Arkime MCP, dissects with tshark"

- **Partially verified:** arkime-mcp's four tools are unit-tested against
  mocked HTTP (6 passing tests including the audit-log write) —
  `fetch_pcap_slice` is proven to write bytes to disk correctly in
  isolation. opencode's role/config file is written but has never
  installed or run opencode for real.
- **Remains manual:** local test-VM proof that opencode installs and its
  config renders valid JSON, then with real Arkime credentials, a real
  Remote-SSH session pulling and dissecting a real PCAP.

## 4. "Map this activity to MITRE with no internet"

- **Verified in isolation, not yet verified as a running service.**
  attack-mcp's `lookup_technique` and `search_techniques` are unit-tested
  (6 passing tests) against a fixture STIX bundle and the audit-log write
  path is proven. The `attack-mcp.container` quadlet and Containerfile are
  written but the image has never actually been built or run — that needs
  podman on the test VM.
- **Remains manual:** confirm the containerized server starts and answers
  SSE on the test VM; separately, run `scripts/pin-attack-data.sh` (needs
  internet) at production build time to swap the test fixture for the real
  ATT&CK dataset.

## 5. "audit/ contains shell commands, session recording, prompts, MCP tool calls"

- **Mechanism written, not yet exercised live.** `audit_logging` role
  (auditd execve rules + tlog session recording) and the per-MCP-tool-call
  `_audit()` logging in both custom servers (unit-tested: each server has
  a passing test asserting a JSONL line is written per tool call) are
  complete. No real auditd rule has ever been loaded into a kernel, and no
  real tlog session has ever been recorded, because no target VM has
  booted yet.
- **Remains manual:** on the test VM, confirm `auditctl -l` shows the
  loaded rules, a real command produces a real `ausearch` hit, and a real
  interactive SSH session is captured by tlog. Then, on the real deploy,
  confirm a live chat session produces entries across all four layers at
  once.

## 6. "With egress locked to ES+Arkime only, steps 2-5 still pass"

- **Written, not yet verified.** The `air_gapped` block in `base_hardening`
  (firewalld default-DROP + explicit allow-list for ES/Arkime hosts) is
  written and ansible-lint clean, but has never been applied to a running
  firewalld instance.
- **Remains manual:** on the test VM, apply with `air_gapped=true` and one
  allow-listed host, confirm traffic to that host succeeds and traffic to
  every other host is blocked — this is the first real test of the rule,
  not just a syntax check.

## What to do first once tooling is available

1. `sudo apt install -y packer qemu-kvm qemu-utils libvirt-daemon-system` on
   this workstation (or hand the repo to a box that already has them).
2. `make packer-build && make vm-up` — first real proof any of this works
   end to end.
3. `cd ansible && ansible-playbook -i inventory/test.ini
   -e @group_vars/test.yml site.yml` — the first real run of all 10 roles
   together.
4. Work through this document top to bottom, replacing each "not yet
   verified" with the actual command output, or a filed bug if something
   that lint-checked clean turns out not to work live — lint proves syntax,
   not behavior, and the gap between those two is exactly what this
   document exists to close.
