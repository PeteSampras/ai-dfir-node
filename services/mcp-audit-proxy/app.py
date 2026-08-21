"""Audit-logging reverse proxy in front of mcpo.

Design spec section 5 requires a Tools row: "each MCP server logs every
invocation -- query text, target, result digest, timestamp". Nothing implemented
it. auditd sees execve, tlog sees terminal I/O, Open WebUI's chat DB sees
prompts -- none of them see an MCP tool call, so a model querying the SOC
cluster left no trace at all.

mcpo is the one chokepoint every tool call crosses (Open WebUI's tool servers
and scripts/dfir-hunt.py both), so logging here is structural: a new caller
cannot forget to opt in, and a caller cannot suppress its own record.

Records land in the same sqlite file the job queue uses, in a separate
`ai_audit` table. Writes use WAL so the queue's worker and this proxy can hold
the file at once.

DELIBERATE: a tool call is logged even when it fails, and the record is written
BEFORE the response is returned to the caller. An audit trail that only records
successes is not an audit trail.
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

DB_PATH = os.environ.get("AUDIT_DB_PATH", "/data/queue.db")
MCPO_BASE_URL = os.environ.get("MCPO_BASE_URL", "http://mcpo:8000")
UPSTREAM_TIMEOUT_S = float(os.environ.get("UPSTREAM_TIMEOUT_S", "300"))
# Full result text can be megabytes of ES documents. The spec asks for a
# "result digest", not the payload -- keep a bounded prefix plus the true size.
DIGEST_CHARS = int(os.environ.get("AUDIT_DIGEST_CHARS", "2000"))
# The streamable-HTTP MCP bridge (llama.cpp's WebUI talks this, not OpenAPI).
MCP_BRIDGE_URL = os.environ.get("MCP_BRIDGE_URL", "http://mcp-bridge:8080/mcp")
MCP_SERVER_LABEL = os.environ.get("MCP_SERVER_LABEL", "elasticsearch")
CORS_ORIGINS = [o for o in os.environ.get("MCP_CORS_ORIGINS", "*").split(",") if o]

# JSON-RPC methods that are protocol handshake/discovery, not data access. Everything
# NOT in this set is treated as a command and audited -- an allowlist rather than a
# denylist, so a method added by a future MCP revision is recorded by default rather
# than silently escaping the trail.
MCP_PROTOCOL_NOISE = {
    "initialize", "ping", "tools/list", "resources/list", "resources/templates/list",
    "prompts/list", "completion/complete", "logging/setLevel",
}

app = FastAPI(title="mcp-audit-proxy", description="Audit-logging proxy in front of mcpo")

# The llama.cpp WebUI is a browser client on a different origin, so the MCP route needs
# CORS -- including Mcp-Session-Id, which the client must both send and read back.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id", "mcp-session-id"],
)


@contextmanager
def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_audit (
                id TEXT PRIMARY KEY,
                ts REAL NOT NULL,
                server TEXT NOT NULL,        -- mcp server name (e.g. elasticsearch)
                tool TEXT NOT NULL,          -- tool invoked (e.g. search)
                arguments TEXT,              -- query text / target, verbatim
                status INTEGER,              -- upstream HTTP status
                error TEXT,
                result_bytes INTEGER,        -- true size before digesting
                result_digest TEXT,          -- bounded prefix of the result
                duration_ms INTEGER,
                caller TEXT                  -- client host + user-agent, best effort
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ai_audit_ts ON ai_audit (ts)")


@app.on_event("startup")
def startup():
    _init_db()


def _record(**kw):
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO ai_audit (id, ts, server, tool, arguments, status, error, "
                "result_bytes, result_digest, duration_ms, caller) "
                "VALUES (:id,:ts,:server,:tool,:arguments,:status,:error,"
                ":result_bytes,:result_digest,:duration_ms,:caller)", kw)
    except Exception as exc:  # noqa: BLE001
        # Never let an audit failure take the tool call down with it, but make the
        # loss loud -- a silently missing audit record is the worst outcome here.
        print("AUDIT WRITE FAILED for %s/%s: %s" % (kw.get("server"), kw.get("tool"), exc), flush=True)


@app.get("/healthz")
def healthz():
    with _db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM ai_audit").fetchone()[0]
    return {"ok": True, "audited_calls": n}


@app.get("/audit")
def audit(limit: int = 50, server: str = "", tool: str = ""):
    """Read back the trail. Local-only retrieval, per the spec's no-shipping rule."""
    q = "SELECT * FROM ai_audit"
    where, params = [], []
    if server:
        where.append("server=?"); params.append(server)
    if tool:
        where.append("tool=?"); params.append(tool)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY ts DESC LIMIT ?"
    params.append(min(limit, 1000))
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return {"count": len(rows), "calls": rows}


def _audit_jsonrpc(body, status, text, started, request, session):
    """Record the auditable JSON-RPC messages in one MCP POST body.

    A body may be a single request or a batch array, so this walks whatever it is
    given. A message that cannot be parsed is still recorded -- an unparseable
    command reaching the SOC cluster is exactly what an audit trail must not drop.
    """
    try:
        msgs = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        _record(id=str(uuid.uuid4()), ts=started, server=MCP_SERVER_LABEL, tool="<unparseable>",
                arguments=body[:8000].decode("utf-8", "replace"), status=status,
                error="request body was not valid JSON", result_bytes=len(text or ""),
                result_digest=(text or "")[:DIGEST_CHARS],
                duration_ms=int((time.time() - started) * 1000),
                caller=_caller(request, session))
        return
    for m in (msgs if isinstance(msgs, list) else [msgs]):
        if not isinstance(m, dict):
            continue
        method = m.get("method") or ""
        if not method or method in MCP_PROTOCOL_NOISE or method.startswith("notifications/"):
            continue
        params = m.get("params") or {}
        if method == "tools/call":
            tool = params.get("name") or "<unnamed>"
            args = json.dumps(params.get("arguments", {}))
        else:
            tool = method
            args = json.dumps(params)
        _record(id=str(uuid.uuid4()), ts=started, server=MCP_SERVER_LABEL, tool=tool,
                arguments=args[:8000], status=status, error=None,
                result_bytes=len(text or ""), result_digest=(text or "")[:DIGEST_CHARS],
                duration_ms=int((time.time() - started) * 1000),
                caller=_caller(request, session))


def _caller(request, session=""):
    return "%s %s%s" % (request.client.host if request.client else "?",
                        request.headers.get("user-agent", "")[:100],
                        (" session=%s" % session) if session else "")


def _fwd_headers(request):
    """Forward only what the MCP transport needs. Hop-by-hop headers and Host must not
    be copied through or the upstream request is malformed."""
    keep = {"content-type", "accept", "mcp-session-id", "mcp-protocol-version",
            "last-event-id", "authorization"}
    return {k: v for k, v in request.headers.items() if k.lower() in keep}


@app.post("/mcp")
async def mcp_post(request: Request):
    """Audited streamable-HTTP MCP endpoint.

    Every tools/call the browser makes crosses this. Buffering the POST response is
    safe -- a JSON-RPC request/response exchange completes and closes, unlike the GET
    stream below -- and it is what lets the result digest be recorded.
    """
    body = await request.body()
    started = time.time()
    session = request.headers.get("mcp-session-id", "")
    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_S) as client:
            r = await client.post(MCP_BRIDGE_URL, content=body, headers=_fwd_headers(request))
        status, text = r.status_code, r.text
        media = r.headers.get("content-type", "application/json")
        out_headers = {}
        if r.headers.get("mcp-session-id"):
            out_headers["mcp-session-id"] = r.headers["mcp-session-id"]
    except Exception as exc:  # noqa: BLE001
        status, media, out_headers = 502, "application/json", {}
        text = json.dumps({"jsonrpc": "2.0", "error": {"code": -32603,
                           "message": "bridge unreachable: %s" % exc}})

    _audit_jsonrpc(body, status, text, started, request,
                   out_headers.get("mcp-session-id", session))
    return Response(content=text, status_code=status, media_type=media, headers=out_headers)


@app.get("/mcp")
async def mcp_get(request: Request):
    """Server->client notification stream. Long-lived SSE, so it must be streamed
    through rather than buffered -- buffering would hang the client forever. Carries no
    tool calls, so there is nothing to audit here."""
    async def relay():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", MCP_BRIDGE_URL, headers=_fwd_headers(request)) as r:
                async for chunk in r.aiter_raw():
                    yield chunk
    return StreamingResponse(relay(), media_type="text/event-stream")


@app.delete("/mcp")
async def mcp_delete(request: Request):
    """Session termination."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.delete(MCP_BRIDGE_URL, headers=_fwd_headers(request))
    return Response(content=r.text, status_code=r.status_code)


@app.api_route("/{server}/{tool:path}", methods=["GET", "POST"])
async def proxy(server: str, tool: str, request: Request):
    body = await request.body()
    started = time.time()
    status, err, text = None, None, ""
    url = "%s/%s/%s" % (MCPO_BASE_URL, server, tool)
    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_S) as client:
            r = await client.request(
                request.method, url, content=body,
                headers={"Content-Type": request.headers.get("content-type", "application/json")})
        status, text = r.status_code, r.text
        media = r.headers.get("content-type", "application/json")
    except Exception as exc:  # noqa: BLE001
        err, media = str(exc), "application/json"
        text = json.dumps({"detail": "upstream error: %s" % err})
        status = 502

    # Only tool invocations are auditable events; spec/openapi fetches are not.
    if not tool.endswith("openapi.json") and tool not in ("docs", "healthz"):
        try:
            args = body.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            args = "<undecodable>"
        _record(id=str(uuid.uuid4()), ts=started, server=server, tool=tool,
                arguments=args[:8000], status=status, error=err,
                result_bytes=len(text or ""), result_digest=(text or "")[:DIGEST_CHARS],
                duration_ms=int((time.time() - started) * 1000),
                caller="%s %s" % (request.client.host if request.client else "?",
                                  request.headers.get("user-agent", "")[:120]))
    return Response(content=text, status_code=status, media_type=media)
