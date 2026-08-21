# Configuration Guide

Where to look to set up a node and change what it points at. This is the
practical companion to `docs/specs/2026-08-20-ai-dfir-node-design.md`
(the "why") — this doc is the "where."

## The one file that matters most: `ansible/group_vars/production.yml`

Copy `ansible/group_vars/all.yml.example` → `ansible/group_vars/production.yml`
(gitignored — it holds real credentials) and fill in:

```yaml
gpu_available: true
elasticsearch_configured: true
arkime_configured: true
air_gapped: false

elasticsearch_url: "https://es.your-soc.example:9200"
elasticsearch_api_key: "CHANGEME"

arkime_base_url: "https://arkime.your-soc.example"
arkime_api_token: "CHANGEME"

model_repo: "unsloth/muse-glimmer-GGUF"
model_file: "muse-glimmer.Q5_K_M.gguf"
model_context_size: 32768
# model_local_path: "/home/you/models/muse-glimmer.Q5_K_M.gguf"  # skip the HF download
```

Every one of these flows through to the actual configs below — you should
rarely need to touch a template directly. The three `_configured` booleans
are the master switches: each one gates a whole MCP server (its container,
its quadlet, its entry in both opencode's and Open WebUI's tool lists) on
or off. Leave `arkime_configured`/`elasticsearch_configured: false` and
those integrations simply don't exist on the node — no half-configured
server sitting there failing.

Then point Ansible at the real box: copy
`ansible/inventory/production.ini.example` → `production.ini.example`'s
sibling `production.ini` (also gitignored) and fill in the real hostname/IP.
**Connect as `provision`, not `ainode`** — the example file already has this
right; see the "Two accounts" note below if you're wondering why.

## Where the LLM endpoint is set

- **The model itself**: `model_repo`/`model_file`/`model_local_path` above,
  consumed by `ansible/roles/llama_server` — either downloads from Hugging
  Face on the target (`fetch-model.sh`) or copies a pre-downloaded GGUF
  straight from wherever you run `ansible-playbook` (set `model_local_path`,
  no internet needed on the target for this step).
- **The serving endpoint**: llama.cpp's CUDA server container, always on
  `127.0.0.1:8080` inside the node (`roles/llama_server/templates/llama-server.container.j2`).
  Nothing outside the node talks to it directly.
- **Who talks to it**:
  - opencode: `ansible/roles/opencode/templates/opencode-config.json.j2` —
    the `provider.llama-local.options.baseURL` field, hardcoded to
    `http://127.0.0.1:8080/v1` (same-node, so this never needs to change
    across deployments).
  - Open WebUI: wired to the same `127.0.0.1:8080` endpoint via its own
    connection settings, deployed by `roles/open_webui`.

## Where the MCP servers are configured

Three MCP servers, each independently gated by a `_configured` flag:

| Server | Role | Container config | Consumed by |
|---|---|---|---|
| attack-mcp (offline MITRE ATT&CK) | always on | `roles/mcp_servers/templates/attack-mcp.container.j2` | both, always |
| arkime-mcp | `arkime_configured` | `.../arkime-mcp.container.j2` + `.../arkime-mcp.env.j2` | both, if enabled |
| elasticsearch-mcp | `elasticsearch_configured` | `.../elasticsearch-mcp.container.j2` + `.../elasticsearch-mcp.env.j2` | both, if enabled |

Each server is reachable **two different ways**, because opencode and Open
WebUI consume MCP differently:

- **opencode** (CLI) talks to attack-mcp/arkime-mcp directly as local
  stdio processes — see `opencode-config.json.j2`'s `mcp` block. Their
  venvs live at `/opt/ainode/venvs/<name>/`. elasticsearch-mcp is the
  exception: it's the *official* `@elastic/mcp-server-elasticsearch` npm
  package, run via `npx` directly (no custom venv), configured with
  `ES_URL`/`ES_API_KEY` env vars in that same block.
- **Open WebUI** can't speak MCP's stdio/local transport, so `mcpo`
  (MCP-to-OpenAPI proxy) sits in front of all three, translating each into
  an OpenAPI tool Open WebUI can call. Its server list is
  `roles/open_webui/templates/mcpo-config.json.j2` — each entry points at
  the corresponding container's own SSE port (attack-mcp `:9001`, arkime-mcp
  `:9002`, elasticsearch-mcp `:9003`, all `127.0.0.1`-only).

**To add a fourth MCP server**, the pattern to copy is arkime-mcp end to
end: a `Containerfile` under `mcp-servers/<name>/`, a `<name>.container.j2`
+ `<name>.env.j2` template in `roles/mcp_servers/templates/`, a new block in
`roles/mcp_servers/tasks/main.yml` gated by whatever flag makes sense, and
matching entries in both `opencode-config.json.j2` and `mcpo-config.json.j2`.

## Two accounts, on purpose: `ainode` vs `provision`

The node has two Linux accounts and they are **not interchangeable**:

- **`ainode`** — the analyst's own login. Every interactive SSH session is
  forced through `tlog-rec-session` (session recording, `audit_logging`
  role) for accountability. This is deliberate and load-bearing — don't
  "fix" it by loosening `ForceCommand`.
- **`provision`** — Ansible/automation only, never session-recorded. This
  split exists because `tlog-rec-session` always launches an interactive
  shell and ignores `SSH_ORIGINAL_COMMAND`
  ([Scribery/tlog#227](https://github.com/Scribery/tlog/issues/227)) — so
  Ansible can never run module code as `ainode` once the audit_logging role
  has deployed. **Always point `ansible_user` at `provision`** in any
  inventory file for this project; both example inventories already do.

## Where accountability logs land

`audit_root` (default `/srv/ainode/audit`, override in `production.yml`):

- `sessions/` — tlog recordings of every `ainode` interactive SSH session
  (owned `tlog:tlog` — see the two-accounts note above for why).
- `mcp-calls/mcp-calls.jsonl` — one line per MCP tool call, from both
  attack-mcp and arkime-mcp's own `_audit()` helper.
- auditd execve rules (shell command logging) go to the standard auditd
  log, not under `audit_root` — query with `ausearch`.

## Quick reference: what changes where

| I want to... | Edit |
|---|---|
| Point at a different model | `model_repo`/`model_file`/`model_local_path` in `production.yml` |
| Turn Arkime/ES integration on/off | `arkime_configured`/`elasticsearch_configured` in `production.yml` |
| Change ES/Arkime credentials | `elasticsearch_api_key`/`arkime_api_token` in `production.yml` |
| Add a new MCP server | See "add a fourth MCP server" above |
| Change where audit logs live | `audit_root` in `production.yml` |
| Lock egress to ES/Arkime only | `air_gapped: true` in `production.yml` |
| Deploy to a real box | `production.ini` (host/IP, `ansible_user=provision`) |
