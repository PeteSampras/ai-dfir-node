# Setup

Complete build-out of the minimal AI DFIR node: a local LLM analysing an
Elasticsearch SOC cluster, with every tool call audited.

Target is a **single host**. Nothing here needs a second machine.

---

## 1. Prerequisites

| Need | Why | Check |
|---|---|---|
| Linux + Docker | the whole stack is containers | `docker version` |
| NVIDIA GPU + `nvidia-container-toolkit` | llama.cpp serves the model on GPU | `nvidia-smi -L` |
| Membership of the `docker` group | the stack is driven without `sudo` | `id -nG \| grep docker` |
| A GGUF model file | llama.cpp loads a local GGUF; nothing is downloaded at runtime | — |
| Network reachability to Elasticsearch | the MCP tools query it | `curl -sk https://<es-host>:9200` → `401` |

**GPU sizing is the constraint that bites first.** The model *and* its KV cache
must fit in VRAM. An ~18 GB GGUF at 32k context needs ~19 GB of a 24 GB card. A
large system RAM figure does not help here — inference speed is bound by memory
bandwidth and core count, not capacity, so CPU offload is not a rescue.

If you are not in the `docker` group:

```bash
sudo usermod -aG docker "$USER"      # must run in a real terminal; sudo needs a TTY
```

Log out and back in, or use `sg docker -c '<command>'` in the current session.

---

## 2. Clone

```bash
git clone -b minimal git@github.com:PeteSampras/ai-dfir-node.git
cd ai-dfir-node
```

The `minimal` branch is the Docker-only build. `main` carries the full appliance
build (Packer image, Ansible provisioning, auditd/tlog hardening, Arkime and
ATT&CK MCP servers, opencode CLI) and is a different deployment path.

---

## 3. Place the model

```bash
mkdir -p models
cp /path/to/your-model.gguf models/
```

`models/` is gitignored. If you already have the file elsewhere on the same
filesystem, hardlink instead of copying — instant, and no second copy of 18 GB:

```bash
ln /existing/path/model.gguf models/
```

---

## 4. Configure

```bash
cp .env.minimal.example .env.minimal
chmod 600 .env.minimal
```

Edit it:

| Variable | Notes |
|---|---|
| `MODEL_FILE` | filename only, as it appears inside `models/` |
| `MODEL_CONTEXT_SIZE` | must not exceed what the GGUF was converted for. Lower it first if the model fails to load |
| `ES_URL` | e.g. `https://es.example:9200` |
| `ES_API_KEY` | base64 API key, `Authorization: ApiKey <this>` |
| `ES_SSL_SKIP_VERIFY` | **`true` is required for a self-signed cert** (Security Onion's default) |
| `SEED_EMAIL` / `SEED_PASSWORD` | admin account for the web UI |

`.env.minimal` is gitignored and holds real credentials — it must never be
committed.

### About `ES_SSL_SKIP_VERIFY`

This is not optional against a self-signed cluster. Without it the first query
fails with `unable to verify the first certificate`. Confirm which case you are
in before assuming:

```bash
curl -s  -o /dev/null -w '%{http_code}\n' -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL"  # fails → self-signed
curl -sk -o /dev/null -w '%{http_code}\n' -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL"  # 200 → creds are good
```

For production prefer pinning the CA instead of disabling verification, if the
cert carries a correct SAN for the ES host:

```
ES_CA_CERT=/path/to/ca.crt
```

---

## 5. Bring up

```bash
make up
```

First run pulls a multi-GB CUDA image and builds three local images, so expect
several minutes. Then:

```bash
make health
```

Four `200`s. The model takes ~30 s to load after the container starts; until it
does, `llama-server` reports unhealthy rather than failing.

---

## 6. Build the field reference

```bash
make fields
```

**Do this before seeding.** It samples real documents from your cluster and
writes a per-dataset list of the fields that are actually populated, which then
travels inside every prompt.

Without it the model is guessing field names. Its only schema tool,
`get_mappings`, returns ~44 KB for a single index across 412 fields; any sane
truncation cuts that to the alphabetical head — `agent.*`, `container.*` — so it
never sees `process.*` or `winlog.*`. Mappings also list hundreds of declared
ECS fields that carry no data. Sampling shows what is real.

The output is environment-specific and gitignored. Regenerate it whenever the
cluster's shape changes.

It costs context: roughly 4–6k tokens inside a 32k window. If that squeezes long
investigations, trim it with `FIELD_MIN_DOCS` (drop small datasets) or
`FIELD_MAX_PER_DATASET`.

---

## 7. Seed the UI

```bash
make seed SEED_EMAIL=you@example.com SEED_PASSWORD='...'
```

This creates the admin account, registers the audited tool server, and imports
every playbook as a slash command. It is **idempotent** — safe to re-run after
every `make up`.

Two mechanisms are in play, and the distinction matters when something looks
like it did not apply:

- On a **fresh volume**, `TOOL_SERVER_CONNECTIONS` in compose registers the tool
  server at first boot. It is a `PersistentConfig`: it seeds the database once,
  and thereafter the stored value wins and edits to it are ignored.
- On an **already-running instance**, only `make seed` has any effect, because
  it writes through the API. Prompts have no env-var path at all and always
  arrive this way.

If the instance already has an admin, `SEED_EMAIL`/`SEED_PASSWORD` must match it
— Open WebUI exempts only the *first* admin from `ENABLE_SIGNUP=False` and
refuses later signups.

---

## 8. Verify it actually works

```bash
# the model answers
curl -s http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Reply with exactly: node online"}],"max_tokens":400}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])'

# the tools reach Elasticsearch
curl -s -X POST http://127.0.0.1:8001/elasticsearch/list_indices \
  -H 'Content-Type: application/json' -d '{"indexPattern":"*"}' | head -c 200

# the call was audited
make audit N=5

# end to end, model + tools together
python3 scripts/dfir-hunt.py --prompt "How many indices match *zeek*? Use the tools."
```

If the model is a reasoning model it may spend its whole budget thinking and
return empty `content` with `finish_reason: length`. That is not a failure —
raise `max_tokens`.

---

## 9. Using it

### Open WebUI — `http://<this-host>:3000`

Type `/` in a chat to insert a playbook (`/network-beaconing`,
`/windows-logon-triage`, …). The playbook supplies the method; you supply the
scope in plain language.

Set the analyst rules as the model's baseline: **Workspace → Models → edit →
System Prompt**, paste `skills/system-prompt.md`. Then every chat carries them
without typing anything.

Set **Function Calling: Native** in the model's advanced params. The stack
supports real tool calls, and Native is markedly more reliable than Open WebUI's
prompt-based fallback.

### llama.cpp's built-in UI — `http://localhost:8080`

Its MCP page (`#/mcp-servers`) needs:

```
http://localhost:8001/mcp
```

`localhost`, not a service name — this client runs in **your browser**, so the
URL resolves on your machine. Both ports are loopback-bound, so the browser must
be on this host.

### Command line

```bash
make playbooks                                    # list them
make hunt PLAYBOOK=network-beaconing WINDOW=24h   # run one
python3 scripts/dfir-hunt.py --prompt "..."       # free-form
```

Each run writes a timestamped `.md` and `.json` to `hunts/` with the answer and
the full tool transcript — every query and its raw result.

Exit codes: `0` complete, `2` step budget exhausted with the model still working
(report marked INCOMPLETE; re-run with a larger `--max-steps`).

### Scheduled hunts

```bash
sudo cp scripts/dfir-hunt.py /usr/local/bin/
sudo cp scripts/systemd/ainode-hunt@.* /etc/systemd/system/
sudo install -D scripts/systemd/hunt.env.example /etc/ainode/hunt.env
sudo systemctl daemon-reload
sudo systemctl enable --now ainode-hunt@network-beaconing.timer
```

There is one GPU and `llama-server` is its only consumer, so a long scheduled
hunt competes with analysts in the UI. Keep frequent hunts narrow; run broad
ones off-hours.

---

## 10. The audit trail

Every MCP tool call is recorded in the `ai_audit` table of the queue's sqlite
database, captured at the proxy that both UIs go through.

```bash
make audit N=50
curl -s 'http://127.0.0.1:8001/audit?limit=20' | python3 -m json.tool
```

Per call: server, tool, verbatim arguments, HTTP status, result size, bounded
result digest, duration, caller, and MCP session id where there is one. Failed
calls are logged too, and the record is written before the response returns.

**Scope, stated plainly:** this covers *tool invocations*. Prompts and
completions live in Open WebUI's own database; shell activity needs the
auditd/tlog layer from the full build. Do not treat this table as a complete
record of analyst activity.

**Point tools at 8001, never 8000.** Both work; only 8001 records the call.

---

## 11. Troubleshooting

Symptoms that cost real time, and what they actually mean.

**`permission denied` on the Docker socket.** Not in the `docker` group. See §1.
`sudo` needs a TTY, so it cannot be run from a non-interactive shell.

**`llama-server` restarting, `failed to open GGUF file`.** The bind mount found
no file, and Docker created an empty root-owned `models/` directory. Confirm
`MODEL_FILE` matches a file that is actually in `models/`.

**`llama-server` restarting, CUDA OOM on load.** Model + KV cache exceed VRAM.
Lower `MODEL_CONTEXT_SIZE` before anything else.

**Tool calls fail with `unable to verify the first certificate`.** Self-signed
Elasticsearch. Set `ES_SSL_SKIP_VERIFY=true` or `ES_CA_CERT`. See §4.

**A container exits 0, immediately, repeatedly, with no error.** A stdio MCP
server was started as a service: with nothing on stdin it reads EOF and exits
cleanly. A stdio MCP server is a subprocess, not a service — it belongs inside
mcpo (`docker/mcpo/Containerfile`) or behind the bridge, never on its own.

**Open WebUI shows no tools.** The URL must be the compose service name
`http://mcp-audit-proxy:8001/elasticsearch`. Inside that container `localhost`
is itself, and the host IP will not reach a loopback-bound port.

**llama.cpp's MCP page connects to nothing.** It speaks streamable-HTTP MCP,
which mcpo does not serve. Use `http://localhost:8001/mcp` (§8).

**`curl http://127.0.0.1:8080/` returns 415 `gzip is not supported`.** llama.cpp
serves its UI gzip-only. Use `curl --compressed`. Browsers are unaffected — this
is a curl artefact, not a fault.

**A compose env change had no effect on Open WebUI.** Anything Open WebUI treats
as a `PersistentConfig` is read from env on first boot only; afterwards the
database wins. Use `make seed`, or start from a fresh volume.

**`make seed` cannot sign in.** The instance already has an admin and the
credentials do not match it. Additional signups are refused while
`ENABLE_SIGNUP=False`.

**The model invents field names / queries return zero hits.** The field
reference is missing or stale. Run `make fields`, then `make render`, then
`make seed`. A query on a misspelled field returns zero hits and is
indistinguishable from a genuine clean result — which is why the system prompt
tells the model to verify a field rather than guess it.

**`make test` reports no module named pytest.** The host has no `pip`. Run the
tests in a container:

```bash
docker run --rm -v "$PWD:/w:Z" -w /w python:3.11-slim \
  sh -c 'pip install -q pytest && python -m pytest skills/tests -q'
```

---

## 12. Day-to-day

```bash
make ps          # what is running
make logs        # follow everything
make health      # endpoint reachability
make down        # stop; named volumes (chat, queue, audit) survive
make up          # start again
make fields      # refresh the Elasticsearch field reference from the cluster
make render      # regenerate skills/rendered/ after editing a playbook
make seed ...    # import any newly added playbooks
```

`make down` does **not** delete volumes, so accounts, chat history, the job
queue and the audit trail all persist across a restart. Removing them requires
`docker volume rm` explicitly.

After editing a playbook, `make seed` adds any that are new. It does not
overwrite the text of a prompt that already exists — delete it in the UI first
if you want it re-imported.
