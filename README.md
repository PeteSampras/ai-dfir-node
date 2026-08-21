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
| `mcp-audit-proxy` | 127.0.0.1:8001 | **audit log of every AI tool call**, forwards to mcpo |
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

Check it came up with `make health` (four `200`s), then open
`http://<this-host>:3000`.

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
a bounded result digest, duration, and caller.

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
