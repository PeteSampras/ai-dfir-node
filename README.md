# AI DFIR Node

A Rocky Linux 9 VM appliance for digital-forensics analysis: a local LLM
(muse glimmer, served by llama.cpp) reachable through a web chat UI and a
terminal/VS Code CLI agent (opencode), wired via MCP to your existing SOC
Elasticsearch and Arkime, plus a fully offline MITRE ATT&CK reference. Every
shell command, AI prompt, and tool call is logged locally for accountability.

See `docs/specs/2026-08-20-ai-dfir-node-design.md` for the full design and
`docs/plans/2026-08-20-ai-dfir-node.md` for the build plan.

## Quick start (local test build — no ESXi/GPU required)

```bash
make packer-build   # builds a Rocky 9 qcow2 under local KVM
make vm-up           # boots it, waits for SSH
make provision-test  # runs the full Ansible site.yml against it (test group_vars)
make test             # runs every automated check this box can run
make vm-down
```

Already have the Rocky 9 minimal ISO downloaded? Point Packer at it instead of
re-fetching (`iso_checksum=none` skips verification — trust the file, or pass
your own `-var 'iso_checksum=sha256:<hash>'` instead):

```bash
make packer-build PACKER_VARS="-var iso_url=/path/to/Rocky-9-x86_64-minimal.iso -var iso_checksum=none"
```

`PACKER_VARS` passes through to both `packer-build` and `packer-validate` for
any variable in `packer/variables.pkr.hcl` — e.g. `-var accelerator=tcg` on a
host where `/dev/kvm` group membership needs a fresh login to take effect.

Already have the muse glimmer GGUF downloaded? Set `model_local_path` in
`ansible/group_vars/production.yml` (see `all.yml.example`) and Ansible
copies it straight to the target VM instead of fetching it from Hugging
Face on the target.

## Real deployment (ESXi + NVIDIA L4 + live ES/Arkime)

See `docs/runbooks/esxi-import.md`, `docs/runbooks/gpu-passthrough.md`, and
`docs/runbooks/manual-validation.md`.
