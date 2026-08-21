#!/usr/bin/env python3
"""gen-field-reference.py -- build a compact Elasticsearch field reference for the model.

THE PROBLEM THIS SOLVES: the Elasticsearch MCP server's only schema tool is
get_mappings, and a single index mapping here is ~44 KB across 412 fields. Any
sane tool-result truncation cuts that to a fraction, and because mappings
serialise alphabetically the surviving fraction is agent.*/container.*/
data_stream.* boilerplate -- the model never sees process.* or winlog.*. So it
guesses field names and writes queries that match nothing.

Mapping alone is also misleading: an index template declares hundreds of ECS
fields that are never populated. Sampling real documents shows which fields
actually carry data, which is what an analyst needs to know.

Output is a per-dataset markdown reference of fields that are genuinely present,
ordered by how often they occur, small enough to sit in the system prompt.

The result is environment-specific (your index names, your populated fields), so
it is gitignored and regenerated with `make fields`.
"""
import collections
import json
import os
import pathlib
import sys
import urllib.request

ES_URL = os.environ.get("ES_URL", "").rstrip("/")
ES_API_KEY = os.environ.get("ES_API_KEY", "")
SKIP_VERIFY = os.environ.get("ES_SSL_SKIP_VERIFY", "").lower() in ("1", "true")
SAMPLE = int(os.environ.get("FIELD_SAMPLE", "80"))
MAX_FIELDS = int(os.environ.get("FIELD_MAX_PER_DATASET", "25"))
MIN_RATIO = float(os.environ.get("FIELD_MIN_RATIO", "0.05"))
# The whole reference has to fit in the model's context alongside the playbook, tool
# schemas and results. A 32k window cannot afford every dataset, so default to the ones
# carrying real volume -- raise/lower MIN_DOCS if your cluster is shaped differently.
MIN_DOCS = int(os.environ.get("FIELD_MIN_DOCS", "1000"))
OUT = pathlib.Path(os.environ.get("FIELD_REFERENCE_OUT",
                                 pathlib.Path(__file__).parent.parent / "skills" / "reference" / "elastic-fields.md"))

# Plumbing that tells an analyst nothing about the event itself.
NOISE_PREFIXES = (
    "agent.", "elastic_agent.", "ecs.", "input.", "data_stream.", "metadata.",
    "event.agent_id_status", "event.ingested", "host.containerized", "host.os.build",
    "log.offset", "log.file.inode", "log.file.device_id", "container.",
)

# Frequency alone is a bad ranking: @timestamp/tags/host.os.* appear in every document
# and crowd out the fields an analyst actually pivots on. Rank by family first, then by
# how common the field is, so process.command_line survives the cut and @version does not.
PRIORITY_PREFIXES = (
    "process.", "user.", "source.", "destination.", "network.", "dns.", "http.",
    "tls.", "url.", "file.", "registry.", "winlog.event_id", "winlog.event_data.",
    "winlog.logon.", "event.code", "event.action", "event.category", "event.dataset",
    "rule.", "threat.", "client.", "server.", "related.", "host.name", "host.ip",
    "service.", "powershell.", "email.",
)


def rank(field, ratio):
    return (0 if field.startswith(PRIORITY_PREFIXES) else 1, -ratio, field)


if SKIP_VERIFY:
    import ssl
    _CTX = ssl._create_unverified_context()
else:
    _CTX = None


def es(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": "ApiKey %s" % ES_API_KEY}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(ES_URL + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60, context=_CTX) as r:
        return json.loads(r.read())


def leaf_paths(obj, prefix=""):
    """Flatten a document to dotted leaf paths, collapsing array indices -- an
    analyst queries process.args, never process.args.3."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaf_paths(v, "%s.%s" % (prefix, k) if prefix else k)
    elif isinstance(obj, list):
        for v in obj[:1]:
            yield from leaf_paths(v, prefix)
    elif prefix:
        yield prefix


def datasets():
    """Group concrete indices back into the datasets analysts think in."""
    out = collections.defaultdict(int)
    for line in es("/_cat/indices?h=index,docs.count&format=json"):
        idx, cnt = line.get("index", ""), int(line.get("docs.count") or 0)
        if idx.startswith(".") and not idx.startswith(".ds-"):
            continue
        name = idx[4:] if idx.startswith(".ds-") else idx
        for suffix in ("-default", ):
            name = name.replace(suffix, "")
        parts = name.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            name = parts[0]
        name = name.rsplit("-20", 1)[0]
        out[name] += cnt
    return {k: v for k, v in out.items() if v >= MIN_DOCS}


def main():
    if not (ES_URL and ES_API_KEY):
        sys.exit("ES_URL and ES_API_KEY must be set (source .env.minimal)")
    ds = datasets()
    print("found %d datasets with >= %d docs" % (len(ds), MIN_DOCS))
    sections = []
    for name, count in sorted(ds.items(), key=lambda kv: -kv[1]):
        try:
            hits = es("/%s*/_search" % name,
                      {"size": SAMPLE, "query": {"match_all": {}},
                       "sort": [{"@timestamp": {"order": "desc"}}]})["hits"]["hits"]
        except Exception:
            try:
                hits = es("/%s*/_search" % name, {"size": SAMPLE, "query": {"match_all": {}}})["hits"]["hits"]
            except Exception as exc:  # noqa: BLE001
                print("  skip %s (%s)" % (name, exc))
                continue
        if not hits:
            continue
        freq = collections.Counter()
        for h in hits:
            for p in set(leaf_paths(h.get("_source", {}))):
                if not p.startswith(NOISE_PREFIXES):
                    freq[p] += 1
        candidates = [(f, c / len(hits)) for f, c in freq.items() if c / len(hits) >= MIN_RATIO]
        keep = sorted(candidates, key=lambda fc: rank(*fc))[:MAX_FIELDS]
        if not keep:
            continue
        sections.append((name, count, len(hits), keep))
        print("  %-46s %8d docs  %3d fields" % (name, count, len(keep)))

    lines = [
        "# Elasticsearch field reference (generated)",
        "",
        "Fields observed in **real sampled documents** from this cluster, not just",
        "declared in the mappings — a template declares hundreds of ECS fields that are",
        "never populated. `always` means the field appeared in every sampled document.",
        "",
        "Query the dataset pattern (e.g. `logs-zeek-so*`), not a dated concrete index.",
        "Regenerate with `make fields` when the environment changes.",
        "",
    ]
    for name, count, sampled, keep in sections:
        lines.append("## `%s*` — %s docs" % (name, "{:,}".format(count)))
        lines.append("")
        for f, ratio in keep:
            lines.append("- `%s`%s" % (f, "" if ratio >= 0.999 else "  _(%d%%)_" % round(ratio * 100)))
        lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote %s (%d datasets, %d bytes)" % (OUT, len(sections), OUT.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
