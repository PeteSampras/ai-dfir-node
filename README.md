# AI DFIR Node — minimal build

A single-host, offline stack for analysing an Elasticsearch SOC cluster with a
local LLM: a web chat UI, a GPU-served model, the Elasticsearch MCP tools, a
submit/poll job queue, an audited tool proxy, and a scriptable hunt agent.

This branch is the **minimal Docker build** only. The full appliance build
(Packer image, Ansible provisioning, auditd/tlog hardening, Arkime and MITRE
ATT&CK MCP servers, opencode CLI) lives on **`main`**.

## What runs

| Service | Port | Purpose |
|---|---|---|
| `llama-server` | 127.0.0.1:8080 | llama.cpp, CUDA, serves the GGUF |
| `open-webui` | 0.0.0.0:3000 | analyst chat UI |
| `mcpo` | internal | spawns MCP servers, re-exposes them as OpenAPI |
| `mcp-audit-proxy` | 127.0.0.1:8001 | **audit log of every AI tool call**; OpenAPI at `/<server>`, MCP at `/mcp` |
| `mcp-bridge` | internal | stdio→streamable-HTTP MCP, for llama.cpp's built-in WebUI |
| `llm-queue` | 127.0.0.1:8090 | submit/poll queue in front of the model |

## Requirements

Linux with Docker, a working NVIDIA GPU passthrough (`nvidia-container-toolkit`
+ `nvidia-smi` seeing the card), and a GGUF model file. Your user must be in the
`docker` group. Nothing else — no Packer, no Ansible, no KVM.

**GPU sizing matters.** The model must fit in VRAM alongside its KV cache. A
~18 GB GGUF at 32k context needs ~19 GB of a 24 GB card. If the model fails to
load, lower `MODEL_CONTEXT_SIZE` before anything else.

## Bring-up

```bash
cp .env.minimal.example .env.minimal     # then edit it
mkdir -p models && cp /path/to/your.gguf models/
make up
```

`.env.minimal` needs:

- `MODEL_FILE` — filename of the GGUF inside `./models/`
- `MODEL_CONTEXT_SIZE` — must not exceed what the GGUF was converted for
- `ES_URL`, `ES_API_KEY` — your Elasticsearch endpoint and key
- `ES_SSL_SKIP_VERIFY=true` — **required** if Elasticsearch uses a self-signed
  certificate (Security Onion's default). Without it the first query fails with
  `unable to verify the first certificate`. For production prefer `ES_CA_CERT`,
  which validates properly instead of disabling verification against a SOC
  cluster.

Check it came up with `make health` (four `200`s), then seed the UI:

```bash
make seed SEED_EMAIL=you@example.com SEED_PASSWORD='...'
```

That creates the admin account, registers the audited tool server, and imports
all 11 playbooks as slash commands. It is idempotent — safe after every
`make up`. Then open `http://<this-host>:3000`.

On a **fresh** volume the tool server is already registered by
`TOOL_SERVER_CONNECTIONS` in compose before `make seed` runs. That variable is a
PersistentConfig: it seeds the database on first boot only, and afterwards the
stored value wins. So editing it does nothing to an instance that has already
started — `make seed` writes through the API and does work on a running one.
Prompts have no env-var path at all and only ever arrive through the API.

## Wiring the Elasticsearch tools into Open WebUI

Admin Panel → Settings → Tools → add an OpenAPI tool server:

```
http://mcp-audit-proxy:8001/elasticsearch
```

Use the **compose service name**, not `localhost` — inside the Open WebUI
container `127.0.0.1` is itself, and the host IP will not work either because
the proxy is bound to loopback. Set the model's **Function Calling** to
**Native** in its advanced parameters; the stack supports real tool calls, and
Native is markedly more reliable than the prompt-based fallback.

Point tools at **8001 (the audit proxy), not 8000 (mcpo)**. Both work, but only
8001 records the call.

## Wiring tools into llama.cpp's built-in WebUI

llama.cpp's own UI on `:8080` has an MCP client (`#/mcp-servers`). It speaks
streamable-HTTP MCP, which is a different protocol from the OpenAPI that mcpo
serves Open WebUI — so point it at the proxy's MCP endpoint:

```
http://localhost:8001/mcp
```

Use `localhost` here, not a service name: unlike Open WebUI, this client runs in
**your browser**, so the URL is resolved on your machine. Both `:8080` and
`:8001` are bound to loopback, so the browser must be on this host.

`mcp-bridge` deliberately publishes no host port. The browser is meant to reach
it only through the audit proxy, which parses the JSON-RPC and records every
`tools/call`. Exposing the bridge directly would work — and would hand a browser
an unaudited path to your SOC cluster.

## Hunting

```bash
make playbooks                                   # list them
make hunt PLAYBOOK=network-beaconing WINDOW=24h  # run one
python3 scripts/dfir-hunt.py --prompt "Any RDP logons from outside the subnet today?"
```

`scripts/dfir-hunt.py` runs the tool-calling loop: it discovers what mcpo
exposes, hands the schemas to the model, executes what the model calls, and
feeds results back until it answers. Stdlib only, so it runs on a stock
`python3` with nothing installed.

Each run writes a timestamped `.md` and `.json` into `./hunts/` containing the
answer **and the full tool transcript** — every query and its raw result. The
skill library requires that analysts be shown the query behind a claim, so the
transcript is part of the deliverable.

Exit codes: `0` complete, `2` step budget exhausted with the model still
working (the report is marked INCOMPLETE — re-run with a larger `--max-steps`).

### On a schedule

```bash
sudo cp scripts/dfir-hunt.py /usr/local/bin/
sudo cp scripts/systemd/ainode-hunt@.* /etc/systemd/system/
sudo install -D scripts/systemd/hunt.env.example /etc/ainode/hunt.env
sudo systemctl enable --now ainode-hunt@network-beaconing.timer
```

Cadence is a real trade-off: there is one GPU and `llama-server` is its only
consumer, so a long scheduled hunt competes with analysts in the UI. Keep
frequent hunts narrow and run broad ones off-hours.

## Accountability

Every MCP tool call is logged to the `ai_audit` table in the queue's sqlite
database, recorded at the mcpo chokepoint so coverage is structural rather than
per-caller. Failed calls are logged too, and the record is written before the
response returns.

```bash
make audit N=50
curl -s 'http://127.0.0.1:8001/audit?limit=20' | python3 -m json.tool
```

Captured per call: server, tool, verbatim arguments, HTTP status, result size,
a bounded result digest, duration, and caller (plus MCP session id where there
is one).

Both tool paths land in the same table: Open WebUI's OpenAPI calls via
`/<server>/<tool>`, and llama.cpp WebUI's MCP calls via `/mcp`. Protocol
handshake traffic (`initialize`, `tools/list`, notifications) is excluded so the
trail stays readable; anything not on that allowlist is recorded, so a method
introduced by a future MCP revision is audited by default rather than silently
escaping.

**Scope:** this covers tool invocations. Prompts and completions live in Open
WebUI's own database; shell activity needs the auditd/tlog layer from the full
build. Do not treat this table as a complete record of analyst activity.

## Skills

`skills/` holds the system prompt and the playbooks, rendered by
`python3 skills/render.py` (or `make render`) into `skills/rendered/` for both
Open WebUI prompt import and opencode's `AGENTS.md`. Two playbooks are marked
as requiring the full build.

`make test` runs the render tests and needs `pytest`. If the host has no `pip`,
run them in a container:

```bash
docker run --rm -v "$PWD:/w:Z" -w /w python:3.11-slim \
  sh -c 'pip install -q pytest && python -m pytest skills/tests -q'
```
