# AI DFIR Node

A Rocky Linux 9 VM appliance for digital-forensics analysis: a local LLM
(muse glimmer, served by llama.cpp) reachable through a web chat UI and a
terminal/VS Code CLI agent (opencode), wired via MCP to your existing SOC
Elasticsearch and Arkime, plus a fully offline MITRE ATT&CK reference. Every
shell command, AI prompt, and tool call is logged locally for accountability.

See `docs/specs/2026-08-20-ai-dfir-node-design.md` for the full design,
`docs/plans/2026-08-20-ai-dfir-node.md` for the build plan, and
**`docs/CONFIGURATION.md` for where to set the LLM/MCP/ES/Arkime config** —
start there if you just need to point an existing node at something.

## Quick start — provisioning against a test VM

`make provision-test` runs the full `ansible/site.yml` against whatever
`inventory/test.ini` points at (test `group_vars`, all GPU/ES/Arkime
features off by default) — this is what's actually been run and verified,
repeatedly, this project's whole build. Two ways to get a target VM for it:

**Proxmox (recommended if you have it — this is the path that's actually
been proven):** build a Rocky 9 qcow2 with `make packer-build`, `qm importdisk`
it into a VM on your Proxmox host, point `inventory/test.ini` at its IP
(`ansible_user=provision`, see `docs/CONFIGURATION.md`'s two-accounts note),
then `make provision-test`.

**Local KVM, no Proxmox needed:**
```bash
make packer-build   # generates a per-host SSH test key + kickstart, builds a Rocky 9 qcow2 under local KVM
make vm-up           # boots it via raw qemu, waits for SSH
make provision-test  # runs the full Ansible site.yml against it
make test             # runs every automated check this box can run
make vm-down
```
This path works but is a disposable, unmanaged qemu process (no snapshots,
no console, no clean lifecycle) — fine for a quick smoke test, but the
Proxmox path is what this project's own real testing has used.

Nothing to prepare by hand first: `packer-build`/`packer-validate` both depend on the
`kickstart` target, which generates `~/.ssh/ai_dfir_node_test_ed25519` (if it doesn't
already exist) and renders `packer/http/ks.cfg` from `ks.cfg.tmpl` with that key baked
in. `ks.cfg` itself is gitignored on purpose — it always carries a real key, so it must
never be the thing that's committed (only `ks.cfg.tmpl`, with the `__SSH_PUBLIC_KEY__`
placeholder, is tracked).

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
`ansible/group_vars/ainode_production.yml` (see `all.yml.example`) and
Ansible copies it straight to the target VM instead of fetching it from
Hugging Face on the target.

## Real deployment (ESXi + NVIDIA L4 + live ES/Arkime)

See `docs/runbooks/esxi-import.md`, `docs/runbooks/gpu-passthrough.md`, and
`docs/runbooks/manual-validation.md`.

## Minimal Docker bring-up (no OVA/ESXi needed)

If you already have Rocky (or any Linux with Docker + working GPU passthrough) and just
need the web UI, the model, the Elasticsearch MCP tool, and a submit/poll job queue —
skip Packer/Ansible entirely and use `docker-compose.minimal.yml`. See the comment block
at the top of that file for the exact steps. This is a fast-path subset, not a
replacement for the full provisioned node: no auditd/tlog accountability logging, no
firewalld/SELinux hardening, no Arkime/ATT&CK MCP, no opencode CLI.
