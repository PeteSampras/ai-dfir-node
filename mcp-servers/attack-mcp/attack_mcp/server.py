"""FastMCP server exposing MITRE ATT&CK lookups over a pinned local STIX bundle."""
import datetime
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DATA_PATH = Path(__file__).parent.parent / "data" / "enterprise-attack.json"
AUDIT_LOG = os.environ.get("MCP_AUDIT_LOG", "/srv/ainode/audit/mcp-calls.jsonl")

mcp = FastMCP("attack-mcp")


def _audit(tool: str, args: dict, result_summary: str) -> None:
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "server": "attack-mcp",
                "tool": tool,
                "args": args,
                "result_summary": result_summary,
            }) + "\n")
    except OSError:
        pass  # audit logging must never crash the tool call


def _load_bundle(path: Path = None) -> dict:
    with (path or DATA_PATH).open("r", encoding="utf-8") as f:
        return json.load(f)


def _index_techniques(bundle: dict) -> dict:
    index = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                index[ref["external_id"]] = obj
    return index


@mcp.tool()
def lookup_technique(technique_id: str) -> dict:
    """Look up a MITRE ATT&CK technique by ID, e.g. T1059.001."""
    bundle = _load_bundle(DATA_PATH)
    index = _index_techniques(bundle)
    obj = index.get(technique_id.upper())
    if obj is None:
        result = {"found": False, "technique_id": technique_id}
    else:
        result = {
            "found": True,
            "technique_id": technique_id.upper(),
            "name": obj.get("name"),
            "description": obj.get("description"),
            "tactics": [
                phase["phase_name"]
                for phase in obj.get("kill_chain_phases", [])
                if phase.get("kill_chain_name") == "mitre-attack"
            ],
        }
    _audit("lookup_technique", {"technique_id": technique_id}, f"found={result['found']}")
    return result


@mcp.tool()
def search_techniques(keyword: str) -> list[dict]:
    """Search ATT&CK technique names/descriptions for a keyword."""
    bundle = _load_bundle(DATA_PATH)
    keyword_lower = keyword.lower()
    results = []
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        name = obj.get("name", "")
        desc = obj.get("description", "")
        if keyword_lower in name.lower() or keyword_lower in desc.lower():
            ext_id = next(
                (r["external_id"] for r in obj.get("external_references", [])
                 if r.get("source_name") == "mitre-attack"),
                None,
            )
            results.append({"technique_id": ext_id, "name": name})
    _audit("search_techniques", {"keyword": keyword}, f"matches={len(results)}")
    return results


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "9001")))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
