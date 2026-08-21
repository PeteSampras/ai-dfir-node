#!/usr/bin/env python3
"""seed-openwebui.py -- make a fresh clone a working node with no GUI clicking.

Creates the admin account if there isn't one, registers the audited tool server,
and imports every playbook as a slash-command prompt.

Idempotent by design: re-running adds only what is missing and reports what it
skipped, so it is safe to run after every `make up` and safe to wire into a
first-boot unit.

WHY A SCRIPT AND NOT JUST ENV VARS: Open WebUI's TOOL_SERVER_CONNECTIONS is a
PersistentConfig -- with ENABLE_PERSISTENT_CONFIG=True (the default) it seeds the
database on FIRST boot only, and after that the stored value wins and the env var
is ignored. So compose alone configures a brand-new volume but cannot fix an
instance that has already started. This does both.

Prompts have no env-var path at all; they only exist through the API.

Usage:
  SEED_EMAIL=you@example.com SEED_PASSWORD=... python3 scripts/seed-openwebui.py
"""
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

URL = os.environ.get("OPENWEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
EMAIL = os.environ.get("SEED_EMAIL", "")
PASSWORD = os.environ.get("SEED_PASSWORD", "")
NAME = os.environ.get("SEED_NAME", "DFIR Admin")
TOOL_URL = os.environ.get("SEED_TOOL_SERVER_URL", "http://mcp-audit-proxy:8001/elasticsearch")
TOOL_ID = os.environ.get("SEED_TOOL_SERVER_ID", "elasticsearch")
TOOL_NAME = os.environ.get("SEED_TOOL_SERVER_NAME", "Elasticsearch (audited)")


def req(path, payload=None, token=None, method=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {}
    if data:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer %s" % token
    r = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def wait_for_ui(seconds=120):
    for _ in range(seconds):
        try:
            urllib.request.urlopen(URL + "/health", timeout=3).read()
            return True
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return False


def authenticate():
    """Sign in, or create the first admin if the instance is empty.

    Open WebUI deliberately does not gate the FIRST admin on ENABLE_SIGNUP (its
    own comment: that flag auto-disables and can persist stale across a DB
    reset), so a locked-down instance can still be bootstrapped here. Any
    subsequent account would be refused, which is why a wrong password against
    an existing instance is reported as such rather than retried as a signup.
    """
    try:
        return req("/api/v1/auths/signin", {"email": EMAIL, "password": PASSWORD})["token"]
    except urllib.error.HTTPError as e:
        if e.code not in (400, 401, 403):
            raise
    try:
        tok = req("/api/v1/auths/signup",
                  {"name": NAME, "email": EMAIL, "password": PASSWORD})["token"]
        print("  created admin account %s" % EMAIL)
        return tok
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        sys.exit("could not sign in or sign up as %s (HTTP %s: %s).\n"
                 "If this instance already has an admin, set SEED_EMAIL/SEED_PASSWORD "
                 "to those credentials -- Open WebUI refuses additional signups when "
                 "ENABLE_SIGNUP is False." % (EMAIL, e.code, detail))


def seed_tool_server(token):
    cfg = req("/api/v1/configs/tool_servers", token=token)
    servers = cfg.get("TOOL_SERVER_CONNECTIONS", cfg.get("tool_server_connections", [])) or []
    if any((s or {}).get("url") == TOOL_URL for s in servers):
        print("  tool server already registered: %s" % TOOL_URL)
        return
    servers.append({
        "url": TOOL_URL,
        "path": "/openapi.json",
        "type": "openapi",
        "auth_type": "bearer",
        "key": "",
        "enabled": True,
        "info": {"id": TOOL_ID, "name": TOOL_NAME},
        "config": {"enable": True},
    })
    req("/api/v1/configs/tool_servers", {"TOOL_SERVER_CONNECTIONS": servers}, token=token)
    print("  registered tool server: %s" % TOOL_URL)


def seed_prompts(token):
    from skills import render  # rendered fresh so seeding can never ship stale text

    base = pathlib.Path(__file__).parent.parent / "skills"
    system_prompt = (base / "system-prompt.md").read_text(encoding="utf-8")
    playbooks = {p.stem: p.read_text(encoding="utf-8")
                 for p in sorted((base / "playbooks").glob("*.md"))}
    entries = render.render_open_webui(system_prompt, playbooks)

    existing = {p.get("command") for p in (req("/api/v1/prompts/", token=token) or [])}
    added = skipped = 0
    for e in entries:
        if e["command"] in existing:
            skipped += 1
            continue
        try:
            req("/api/v1/prompts/create",
                {"command": e["command"], "name": e["name"], "content": e["content"]},
                token=token)
            added += 1
        except urllib.error.HTTPError as exc:
            print("  ! %s failed: HTTP %s %s"
                  % (e["command"], exc.code, exc.read().decode("utf-8", "replace")[:120]))
    print("  prompts: %d added, %d already present" % (added, skipped))


def main():
    if not (EMAIL and PASSWORD):
        sys.exit("set SEED_EMAIL and SEED_PASSWORD (see README). Refusing to invent "
                 "credentials for an analyst-facing system.")
    print("seeding %s" % URL)
    if not wait_for_ui():
        sys.exit("Open WebUI did not become reachable at %s" % URL)
    token = authenticate()
    seed_tool_server(token)
    seed_prompts(token)
    print("done. Open %s and type / in a chat to use a playbook." % URL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
