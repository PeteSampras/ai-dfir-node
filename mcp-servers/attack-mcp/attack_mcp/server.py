"""FastMCP server exposing MITRE ATT&CK lookups over a pinned local STIX bundle."""
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DATA_PATH = Path(__file__).parent.parent / "data" / "enterprise-attack.json"

mcp = FastMCP("attack-mcp")


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
        return {"found": False, "technique_id": technique_id}
    return {
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
    return results


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "9001")))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
