# AI DFIR Node — Design Spec

**Date:** 2026-08-20
**Status:** Draft for review
**Target:** MVP (single analyst), air-gap-ready by design

## 1. Purpose

A self-contained "AI node" VM for a digital forensics analyst. It hosts a local
LLM (muse glimmer) with a web chat interface and a terminal/VS Code CLI agent,
wired via MCP to the existing SOC Elasticsearch (Zeek, Logstash, Sysmon,
Suricata indices) and Arkime (PCAP), with a local MITRE ATT&CK reference. Every
shell command, AI interaction, and tool call is logged locally for
accountability. The VM imports into ESXi as an OVA and will eventually run
air-gapped; internet is touched only at build time.

## 2. Environment & assumptions

- **Host:** Dell R6615 running ESXi; NVIDIA L4 (24 GB) attached to this VM via
  **DirectPath I/O passthrough** (no vGPU licensing). Host-side VM config needs
  `pciPassthru.use64bitMMIO=TRUE` and `pciPassthru.64bitMMIOSizeGB=64`
  (documented in the repo since it lives outside the OVA).
- **Clients:** analyst laptops reach the node over the network — browser for
  the web UI, SSH / VS Code Remote-SSH for the CLI.
- **External services (existing SOC infra, not on this VM):**
  Elasticsearch (Zeek/Sysmon/Suricata via Logstash) and Arkime. The node needs
  network reachability and read-only credentials for both.
- **Users:** single analyst for MVP. Multi-user attribution is out of scope.
- **Guest OS:** Rocky Linux 9 minimal, SELinux enforcing, firewalld on.

## 3. VM sizing

| Resource | Value | Rationale |
|---|---|---|
| vCPU | 12 | container stack + tshark/Zeek local dissection; model runs on GPU |
| RAM | 64 GB | RAM is the less-scarce resource; headroom for PCAP work |
| Disk | 160 GB thin | disk is the scarcer resource; growing a VMDK later is easy, shrinking isn't |
| GPU | full L4 passthrough | llama-server is the only GPU consumer |

Disk budget: OS ~12 GB · model GGUF ~20 GB · container images ~15 GB ·
reference data ~2 GB · remainder for chat DB, audit logs, PCAP scratch.

## 4. Architecture

```
laptops ──browser──► nginx (TLS) ──► Open WebUI ─┐
laptops ──SSH/VS Code Remote-SSH──► opencode ────┼──► llama-server (L4, muse glimmer GGUF)
                                                 │
                                                 └──► MCP servers:
                                                       • elasticsearch-mcp ──► SOC ES (read-only API key)
                                                       • arkime-mcp ─────────► Arkime REST (view-only user)
                                                       • attack-mcp ─────────► local attack-stix-data (offline)
```

All services are **podman quadlets** (systemd-native, no Docker daemon,
rootless where practical). Container images are pre-loaded from archives baked
into the OVA — no registry needed at runtime.

### 4.1 Model serving — llama.cpp
- One `llama-server` quadlet with GPU (nvidia-container-toolkit + CDI).
- Model: **Unsloth's muse glimmer GGUF** (dynamic quant), largest quant that
  fits 24 GB alongside a ≥32k context; exact quant/context tuned at build and
  pinned in config.
- OpenAI-compatible API on `localhost:8080`, tool/function calling enabled
  (jinja chat template). Nothing else touches the GPU.
- Model choice is a swappable layer: the swap procedure (new GGUF + one config
  change + rebuild) is documented, so muse glimmer is not load-bearing.

### 4.2 Web interface — Open WebUI
- Behind nginx with TLS (self-signed/internal CA for MVP).
- Single admin account. Signups disabled.
- Tools exposed via **mcpo** (MCP→OpenAPI proxy) so the MCP servers below are
  callable from chat.
- Chat history in its SQLite DB — part of the case-documentation trail, backed
  up nightly (§6).

### 4.3 CLI — opencode (on the node, by design)
- opencode is a **client**, not a model host; it calls the same llama-server
  endpoint. It runs **on the node**, reached over SSH, so its every action is
  captured by the node's session recording — running it on laptops would
  bypass accountability logging and is explicitly not the supported path for
  MVP.
- Configured with llama-server as a local OpenAI-compatible provider and the
  same three MCP servers.
- VS Code workflow = Remote-SSH into the node, integrated terminal runs
  opencode there.

### 4.4 MCP servers
1. **Elasticsearch MCP** — official `elastic/mcp-server-elasticsearch`,
   pointed at the SOC cluster with a **read-only API key scoped to the
   Zeek/Sysmon/Suricata/Logstash indices**. List indices, inspect mappings,
   run queries. Never write.
2. **Arkime MCP** — small custom Python FastMCP wrapper over Arkime's REST
   API, using a view-only Arkime account: session search (expression + time
   range), SPI data, unique-values, and fetch-PCAP-slice into
   `/srv/ainode/scratch/` for local dissection. tshark/capinfos and Zeek are
   installed on the node for that local analysis.
3. **MITRE ATT&CK MCP** — serves technique/tactic/group/software/mitigation
   lookup and "map these observations to ATT&CK" from a **pinned local copy of
   `attack-stix-data`**. Zero network dependency; air-gap safe from day one.
   Dataset version pinned in the build and updated by rebuilding.

### 4.5 DFIR skill library
Versioned prompt/skill files in the repo, one source rendered into both
frontends (Open WebUI workspace prompts / custom models; opencode `AGENTS.md`
+ custom agents):
- DFIR-analyst system prompt (evidence-handling tone, cite log lines/doc IDs,
  confidence language, never fabricate indicators).
- Task playbooks: Zeek conn/dns/http/ssl triage · Suricata alert review ·
  Sysmon process-tree analysis · PCAP walkthrough (Arkime pull → tshark/Zeek
  local dissection) · ATT&CK mapping with stated confidence.

## 5. Accountability logging (MVP: local-only)

No log shipping anywhere. Everything lands under **`/srv/ainode/audit/`**
(one retrievable location), JSONL where applicable, logrotate with long
retention.

| Layer | Mechanism | Captures |
|---|---|---|
| Shell | auditd execve rules | every command, kernel-level, all users |
| Session | tlog on SSH sessions | full terminal I/O — opencode sessions replayable |
| AI | Open WebUI chat DB + opencode session logs, both copied nightly into the audit tree | prompts, completions, agent actions |
| Tools | each MCP server logs every invocation | query text, target (index / Arkime expression / ATT&CK object), result digest, timestamp |

Retrieval = copy one directory. Deferred hardening (post-MVP): hash-chained
daily archives; optional Filebeat shipping into SOC ES (decided against for
now).

## 6. Air gap, hardening, ops

- **Build-time-only internet:** RPMs, container image archives, Unsloth GGUF,
  attack-stix-data, and prompts are all baked into the OVA. Runtime needs no
  registry, no repo, no model hub.
- **Going dark** = flip one build variable → firewalld default-deny egress,
  allowing only ES, Arkime, and enclave DNS/NTP. Until then egress is open for
  convenience.
- **Hardening:** SSH key-only + password auth off, SELinux enforcing,
  firewalld on, TLS on the web UI, read-only external credentials.
- **Time:** chrony → enclave NTP (forensic timestamps depend on it).
- **Backup:** nightly on-node bundle (chat DB, audit tree, configs) to
  `/srv/ainode/backup/` for the analyst to copy off.
- **Health:** `node-status` script — GPU visible, model loaded, MCP servers
  answering, ES/Arkime reachable, disk/log headroom.
- **Updates after air gap:** rebuild the OVA outside, carry it across; a
  documented export/import script migrates chat DB + audit data to the new VM.

## 7. Build pipeline (the public GitHub repo)

1. **Packer (qemu builder) + kickstart** — unattended Rocky 9 minimal install;
   builds on any Linux box with KVM, no vCenter dependency.
2. **Ansible provisioner** — NVIDIA datacenter driver (open kernel module,
   pinned to image kernel) + nvidia-container-toolkit, podman + quadlets,
   pre-loaded image archives, model GGUF (fetched at build, never committed to
   git), MITRE data, nginx/TLS, logging stack, hardening, skill library.
3. **Post-process** — qcow2 → streamOptimized VMDK (`qemu-img`) → OVF
   descriptor → **OVA**.

`make ova` produces the artifact; the repo is simultaneously the
documentation and the disaster-recovery plan. Secrets (ES API key, Arkime
creds, TLS material) are **never in git**: injected at build from a local
untracked vars file, or entered on first boot via a `firstboot-config` script.

## 8. Out of scope (MVP)

- Multi-user auth/attribution; log shipping; hash-chained audit archives.
- Sigma rule reference bundle (cheap later add).
- vGPU; CPU-only inference; hosting ES/Arkime on this VM.
- Fine-tuning muse glimmer (Unsloth makes this possible later; not MVP).

## 9. Risks

| Risk | Mitigation |
|---|---|
| muse glimmer's tool-calling quality with ES/Arkime MCP is unproven | validate in week one with scripted tool-call evals; model layer is swappable by design |
| L4 passthrough quirks on ESXi (MMIO sizing) | documented host-side config + verification step in the import runbook |
| Arkime REST wrapper scope creep | MVP endpoints fixed at four (search, SPI, unique, pcap-slice) |
| GGUF/context won't fit 24 GB as guessed | quant/context chosen empirically at build; spec pins the decision procedure, not the number |

## 10. Success criteria

1. OVA imports into ESXi, boots, `node-status` green, `nvidia-smi` shows the L4.
2. From a laptop browser: chat with muse glimmer; ask a question that makes it
   query ES and get real Zeek/Suricata results back.
3. From VS Code Remote-SSH: opencode session does the same, plus pulls a PCAP
   slice via Arkime MCP and dissects it locally with tshark.
4. "Map this activity to MITRE" answers from the local ATT&CK dataset with no
   internet.
5. After the session: `/srv/ainode/audit/` contains the shell commands, the
   session recording, the prompts, and every MCP tool call from steps 2–4.
6. With egress locked to ES+Arkime only, steps 2–5 still pass.
