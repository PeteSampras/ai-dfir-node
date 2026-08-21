#!/usr/bin/env python3
"""dfir-hunt.py -- run a DFIR analysis pass against the local model with live
Elasticsearch tools, either interactively or on a timer.

The model does the reasoning; this script owns the tool loop: it discovers the
tools mcpo exposes, hands their schemas to llama-server, executes whatever the
model calls, feeds the raw results back, and repeats until the model answers or
hits the step budget.

Design notes:
  * stdlib only. The node is offline and has no pip; this must run on a stock
    python3 with nothing installed.
  * Every tool call and its raw result is recorded in the report. The skill
    library requires analysts be shown the query behind a claim, so the
    transcript is a deliverable, not debug output.
  * Tool results are truncated before going back to the model. An unbounded ES
    response will silently blow the context window and the model will start
    losing the earlier evidence rather than erroring.

Usage:
  dfir-hunt.py --prompt "Any beaconing from 192.0.2.0/24 in the last 24h?"
  dfir-hunt.py --playbook network-beaconing --window 24h
  dfir-hunt.py --playbook host-baseline --out /var/log/ainode/hunts --json
"""
import argparse
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

LLAMA_BASE_URL = os.environ.get("LLAMA_BASE_URL", "http://127.0.0.1:8080/v1")
# Defaults to the audit proxy (8001), NOT mcpo (8000): tool calls made by the model
# must land in the ai_audit trail. Pointing this at 8000 silently disables that.
MCPO_BASE_URL = os.environ.get("MCPO_BASE_URL", "http://127.0.0.1:8001")
SKILLS_DIR = pathlib.Path(os.environ.get("SKILLS_DIR", pathlib.Path(__file__).parent.parent / "skills"))
MCPO_CONFIG = pathlib.Path(os.environ.get("MCPO_CONFIG", pathlib.Path(__file__).parent.parent / "docker" / "mcpo-config.json"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "900"))
MAX_TOOL_CHARS = int(os.environ.get("MAX_TOOL_CHARS", "6000"))


def _req(url, payload=None, timeout=HTTP_TIMEOUT):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def discover_tools(servers):
    """Build OpenAI tool schemas from the OpenAPI specs mcpo publishes.

    mcpo mounts each MCP server at /<server>/<tool>. OpenAI function names
    cannot contain '/', so they are flattened to '<server>__<tool>' and mapped
    back at call time.
    """
    tools, route = [], {}
    for server in servers:
        try:
            spec = _req("%s/%s/openapi.json" % (MCPO_BASE_URL, server), timeout=30)
        except Exception as exc:
            print("warn: cannot read tools for %r: %s" % (server, exc), file=sys.stderr)
            continue
        for path, methods in spec.get("paths", {}).items():
            post = methods.get("post")
            if not post:
                continue
            tool = path.strip("/")
            fname = "%s__%s" % (server, tool)
            schema = {"type": "object", "properties": {}}
            body = post.get("requestBody", {}).get("content", {}).get("application/json", {})
            ref = body.get("schema", {})
            if "$ref" in ref:
                name = ref["$ref"].rsplit("/", 1)[-1]
                schema = spec.get("components", {}).get("schemas", {}).get(name, schema)
            elif ref:
                schema = ref
            tools.append({"type": "function", "function": {
                "name": fname,
                "description": post.get("description") or post.get("summary") or tool,
                "parameters": schema}})
            route[fname] = "%s/%s/%s" % (MCPO_BASE_URL, server, tool)
    return tools, route


def call_tool(url, args):
    try:
        return _req(url, args), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:400])
    except Exception as e:
        return None, str(e)


def truncate(text):
    if len(text) <= MAX_TOOL_CHARS:
        return text
    return text[:MAX_TOOL_CHARS] + (
        "\n...[truncated %d chars. Narrow the query -- add filters, reduce size, "
        "or aggregate -- rather than assuming the omitted rows resemble these.]"
        % (len(text) - MAX_TOOL_CHARS))


def build_task(args):
    sys.path.insert(0, str(SKILLS_DIR.parent))
    from skills import render as _render
    system = _render.load_system_prompt(SKILLS_DIR)
    if args.playbook:
        pb = SKILLS_DIR / "playbooks" / ("%s.md" % args.playbook)
        if not pb.exists():
            avail = sorted(p.stem for p in (SKILLS_DIR / "playbooks").glob("*.md"))
            sys.exit("no such playbook %r. available: %s" % (args.playbook, ", ".join(avail)))
        task = ("Work through the following playbook against the live data.\n\n%s\n\n"
                "Time window for this run: %s. Report findings, or state plainly "
                "that you found nothing and what you checked." % (pb.read_text(encoding="utf-8"), args.window))
    else:
        task = args.prompt
    return system, task


def run(args):
    servers = list(json.loads(MCPO_CONFIG.read_text()).get("mcpServers", {}))
    tools, route = discover_tools(servers)
    if not tools:
        sys.exit("no tools discovered from mcpo at %s -- is it running?" % MCPO_BASE_URL)
    system, task = build_task(args)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    transcript, steps = [], 0

    while steps < args.max_steps:
        steps += 1
        try:
            resp = _req(LLAMA_BASE_URL + "/chat/completions", {
                "messages": messages, "tools": tools, "tool_choice": "auto",
                "max_tokens": args.max_tokens, "temperature": args.temperature})
        except Exception as exc:
            sys.exit("model request failed: %s" % exc)
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls} if calls else
                        {"role": "assistant", "content": msg.get("content") or ""})
        if not calls:
            return msg.get("content") or "", transcript, steps, False
        for c in calls:
            fn = c["function"]["name"]
            raw = c["function"].get("arguments") or "{}"
            try:
                cargs = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                cargs = {}
            if args.verbose:
                print("  [step %d] %s %s" % (steps, fn, json.dumps(cargs)[:160]), file=sys.stderr)
            if fn not in route:
                out, err = None, "unknown tool %r" % fn
            else:
                out, err = call_tool(route[fn], cargs)
            body = err if err else json.dumps(out, indent=2)
            transcript.append({"step": steps, "tool": fn, "arguments": cargs,
                               "error": err, "result": body})
            messages.append({"role": "tool", "tool_call_id": c.get("id", ""),
                             "name": fn, "content": truncate(body)})
    return ("", transcript, steps, True)


def write_report(args, answer, transcript, steps, exhausted, started):
    label = args.playbook or "adhoc"
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / ("hunt-%s-%s" % (label, stamp))
    payload = {"playbook": args.playbook, "prompt": args.prompt, "window": args.window,
               "started": started.isoformat() + "Z", "steps": steps,
               "step_budget_exhausted": exhausted, "answer": answer, "transcript": transcript}
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = ["# DFIR hunt: %s" % label, "",
             "- started: %sZ" % started.isoformat(),
             "- window: %s" % args.window,
             "- tool calls: %d over %d step(s)" % (len(transcript), steps)]
    if exhausted:
        lines.append("- **step budget exhausted after %d steps -- this report is INCOMPLETE.** "
                     "The model was still working when it was cut off; treat the findings as "
                     "partial and re-run with a larger --max-steps." % steps)
    lines += ["", "## Findings", "", answer or "_No answer produced._", "",
              "## Tool transcript", ""]
    for t in transcript:
        lines.append("### step %d — `%s`" % (t["step"], t["tool"]))
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(t["arguments"], indent=2))
        lines.append("```")
        lines.append("")
        if t["error"]:
            lines.append("**tool error:** %s" % t["error"])
        else:
            lines.append("```")
            lines.append(t["result"][:MAX_TOOL_CHARS])
            lines.append("```")
        lines.append("")
    base.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    return base


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--prompt", help="free-form question to investigate")
    g.add_argument("--playbook", help="playbook name from skills/playbooks (without .md)")
    p.add_argument("--window", default="24h", help="time window given to the model (default: 24h)")
    p.add_argument("--max-steps", type=int, default=8, help="tool-calling rounds before giving up (default: 8)")
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--out", default=os.environ.get("HUNT_OUT", "./hunts"), help="report directory")
    p.add_argument("--json", action="store_true", help="print the JSON report path only")
    p.add_argument("--verbose", action="store_true", help="log each tool call to stderr")
    p.add_argument("--list-playbooks", action="store_true")
    args = p.parse_args()

    if args.list_playbooks:
        for pb in sorted((SKILLS_DIR / "playbooks").glob("*.md")):
            print(pb.stem)
        return 0
    if not (args.prompt or args.playbook):
        p.error("one of --prompt, --playbook, or --list-playbooks is required")

    started = datetime.datetime.utcnow()
    answer, transcript, steps, exhausted = run(args)
    base = write_report(args, answer, transcript, steps, exhausted, started)

    if args.json:
        print(base.with_suffix(".json"))
    else:
        print(answer or "(no answer produced)")
        print("\n-- %d tool call(s); report: %s" % (len(transcript), base.with_suffix(".md")), file=sys.stderr)
    # Exit 2 signals an incomplete run so a timer/monitor can distinguish it
    # from a clean "nothing found".
    return 2 if exhausted else 0


if __name__ == "__main__":
    sys.exit(main())
