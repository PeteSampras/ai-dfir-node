# Manual Validation Runbook

Maps spec §10's six success criteria to what's actually been verified vs.
what remains. **Status as of 2026-08-20: the full provisioning pipeline has
been run live, repeatedly, end-to-end against a real Proxmox-managed Rocky 9
VM (VMID 960, `ainode-test-vm`), and the OVA build pipeline has produced and
verified a real, checksummed `.ova`.** Everything gated on real GPU hardware,
a live Elasticsearch cluster, or a live Arkime instance is still genuinely
outstanding — this workstation has none of those — but nothing in that
category is a "might not work" risk anymore; it's a "hasn't been run against
real hardware yet" gap, and the seams it needs (quadlets, skip-paths,
`elasticsearch_configured`/`arkime_configured`/`gpu_available` flags) are all
proven to work correctly with those features off.

## 1. "OVA imports into ESXi, boots, node-status green, nvidia-smi shows the L4"

- **Verified: OVA build pipeline.** `scripts/ova-postprocess.sh` run for
  real against VM 960's actual LVM-backed disk on pve, producing a real
  6.74 GB `ai-dfir-node.ova`. Checksums in `ai-dfir-node.mf` verified to
  match the extracted `.ovf`/`.vmdk` byte-for-byte
  (`sha256sum ai-dfir-node.ovf ai-dfir-node-disk1.vmdk`). `.ovf` XML
  confirmed well-formed (`xml.dom.minidom`) and its hardware section
  matches spec exactly: 12 vCPU, 65536 MB (64 GB) RAM, `rhel9_64Guest` OS
  type, `vmx-19` hardware version. Disk capacity in the `.ovf`
  (`42949672960` bytes = 40 GB) reflects VM 960's own test-sized disk —
  it's read dynamically from the source image at build time
  (`qemu-img info`), not hardcoded, so a real production build against
  the R6615's 160 GB disk will pick that size up automatically with no
  script change.
- **Remains manual:** the ESXi import itself, GPU passthrough, and
  `node-status.sh` all-green on real hardware. Follow `esxi-import.md`
  then `gpu-passthrough.md` — the artifact this step consumes is now a
  real, verified `.ova`, not a hypothetical one.

## 2. "From a laptop browser: chat with muse glimmer; get real Zeek/Suricata results back"

- **Verified: the whole non-GPU chain deploys and starts cleanly.** A full
  `ansible-playbook -i inventory/test.ini site.yml` run against VM 960
  (`provision` account, not `ainode` — see note below) completes with
  `failed=0`: nginx installed, self-signed TLS cert generated, Open WebUI
  + mcpo + attack-mcp quadlets deployed and systemd-enabled, `mcpo-config.json`
  rendered correctly, and the `open_webui`/`nginx` reload steps succeed.
  The `mcpo` container's image reference bug (`docker.io/ghcr.io/...`,
  a malformed double-registry prefix) was found and fixed live
  (`ghcr.io/open-webui/mcpo:latest`).
- **Remains manual:** local test-VM proof that podman actually pulls and
  starts the `mcpo`/`open-webui`/`attack-mcp` containers (VM 960 has never
  had `podman_base` exercised against real container pulls — only the
  quadlet/config layer, since the containers themselves weren't started in
  these runs), then with the GPU attached and `elasticsearch_configured:
  true`, a real chat session against a live model and live ES.

## 3. "From VS Code Remote-SSH: opencode pulls a PCAP slice via Arkime MCP, dissects with tshark"

- **Verified: opencode installs for real.** The `opencode` role's live run
  (not just lint) shows `opencode : Install opencode as the ainode user`
  as `changed`, followed by successful venv creation
  (`/opt/ainode/venvs/attack-mcp`) and `pip` install of attack-mcp into it
  — confirms both the install script and the dual-interpreter fix
  (`python3-pip` for Ansible's own module execution + `python3.11` for the
  venv itself) work against a real Rocky 9 target, not just in theory.
  arkime-mcp's four tools remain unit-tested against mocked HTTP only
  (6 passing tests, `arkime_configured: false` in the test VM, so its
  quadlet is skipped by design).
- **Remains manual:** a real Remote-SSH session actually invoking opencode
  interactively, and — once `arkime_configured: true` with real
  credentials — a real PCAP-slice pull and `tshark` dissection.

## 4. "Map this activity to MITRE with no internet"

- **Verified: the container builds and deploys for real.** `attack-mcp`'s
  image is built live via `containers.podman.podman_image` in every clean
  run (`ok`/`changed` on first apply), its quadlet is deployed, and the
  ATT&CK-dataset-present guard passes correctly against the committed test
  fixture (`tests/fixtures/mini-attack.json`, 890 bytes, above the 500-byte
  guard threshold). `lookup_technique`/`search_techniques` remain
  unit-tested (6 passing tests) against that fixture.
- **Remains manual:** confirm the running container actually answers SSE
  requests on the test VM (build success is confirmed; a live query isn't
  yet); separately, run `scripts/pin-attack-data.sh` (needs internet) at
  production build time to swap the test fixture for the real ATT&CK
  dataset before shipping.

## 5. "audit/ contains shell commands, session recording, prompts, MCP tool calls"

- **Verified live, including the deepest part of the mechanism.** This
  was the hardest bug in the whole build and it's now fully closed:
  - **Root cause chased and fixed, live, three layers deep.** `tlog-rec-session`
    is setuid/setgid to a dedicated `tlog` system user (RPM packaging
    design — the recorded user can never tamper with their own log), so
    the session directory has to be owned `tlog:tlog`, not `ainode:ainode`
    as originally written. Separately, `/srv/ainode` itself (the parent of
    every audit/scratch/backup path) was being implicitly created by
    Ansible's auto-parent-creation as `root:root` mode `0750` —
    untraversable by anyone outside the root group, silently blocking
    `tlog` (and `ainode`) regardless of what the child directories were
    chowned to. Both fixed in `roles/podman_base` and `roles/audit_logging`.
  - **A real interactive SSH session was captured, end to end**, after the
    fix: logging in as `ainode` lands cleanly at a shell (no more
    "Permission denied / Failed opening log file"), and
    `/srv/ainode/audit/sessions/tlog.log` contains real, well-formed tlog
    JSON for that exact session (`"user":"ainode"`, real terminal I/O).
  - **A second architectural bug found and fixed the same day:** once
    `ForceCommand tlog-rec-session` is live for `ainode`, Ansible can never
    manage that account again — `tlog-rec-session` always launches an
    interactive shell and ignores `SSH_ORIGINAL_COMMAND`
    ([Scribery/tlog#227](https://github.com/Scribery/tlog/issues/227)).
    Fixed by adding a separate `provision` account (kickstart-created,
    NOPASSWD sudo, unrecorded) that Ansible/day-2 management connects as
    instead. Both `inventory/test.ini` and `inventory/production.ini.example`
    now use `ansible_user=provision`.
  - auditd install and rule deployment confirmed via the clean playbook
    run (`changed` on rules deploy, `ok` on enable/start); a real
    `auditctl -l` / `ausearch` hit and the MCP-tool-call `_audit()` JSONL
    path are still to be exercised live.
- **Remains manual:** confirm `auditctl -l` shows the loaded execve rules
  and a real command produces a real `ausearch` hit; confirm a live MCP
  tool call writes a JSONL line to `audit/mcp-calls/`. Both are much
  smaller/lower-risk than the tlog mechanism that's now proven.

## 6. "With egress locked to ES+Arkime only, steps 2-5 still pass"

- **Written, not yet verified live.** The `air_gapped` block in
  `base_hardening` (firewalld default-DROP + explicit allow-list for
  ES/Arkime hosts) is ansible-lint clean and its tasks correctly `skip`
  (not error) when `air_gapped: false`, confirmed in every test-VM run —
  but it's never actually been flipped to `true` and applied to a running
  firewalld instance.
- **Remains manual:** on the test VM (or a fresh clone of it), set
  `air_gapped: true` plus one allow-listed host in
  `group_vars/ainode_test.yml`, re-run the playbook, and confirm traffic
  to that host succeeds while traffic to every other host is blocked —
  the first real test of the rule, not just a syntax/skip check.

## What's actually left, in priority order

1. **Podman container start-up on the test VM** — the quadlets deploy
   cleanly but the containers themselves (`mcpo`, `open-webui`,
   `attack-mcp`) have not been confirmed to actually pull images and come
   up healthy. This is the next highest-value local (no-GPU-needed) proof.
2. **`air_gapped: true` live test** (criterion 6) — needs a second
   allow-listed host to test against; low effort, currently the only
   *written* criterion with zero live exercise.
3. **`auditctl -l` / `ausearch` / MCP `_audit()` JSONL** (criterion 5) —
   small, mechanical, no blockers.
4. **Everything GPU/ES/Arkime-gated** (criteria 1's hardware half, 2's live
   chat, 3's live PCAP pull) — genuinely blocked on hardware this
   workstation doesn't have; proceeds once the operator is on-site with
   the R6615 tomorrow. `production.ini.example` → `production.ini` and
   `group_vars/all.yml.example` → `production.yml` are the templates to
   fill in for that run; `ansible_user=provision` is already correct in
   the example.
