"""FastMCP server wrapping Arkime's REST API: search, SPI, unique-values, PCAP-slice.

Exactly four tools by design (spec cap) — do not add a fifth without updating
docs/specs/2026-08-20-ai-dfir-node-design.md first.
"""
import os
import pathlib
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("arkime-mcp")


def _client() -> httpx.Client:
    base_url = os.environ["ARKIME_BASE_URL"]
    token = os.environ["ARKIME_API_TOKEN"]
    verify = os.environ.get("ARKIME_VERIFY_TLS", "true").lower() != "false"
    return httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, verify=verify, timeout=30.0)


@mcp.tool()
def search_sessions(expression: str, start_time: str, end_time: str, limit: int = 100) -> list[dict]:
    """Search Arkime sessions by Arkime search expression within a time range."""
    with _client() as client:
        resp = client.get(
            "/api/sessions",
            params={"expression": expression, "startTime": start_time, "stopTime": end_time, "length": limit},
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


@mcp.tool()
def get_spi_data(expression: str, field: str, start_time: str, end_time: str) -> list[dict]:
    """Get SPI aggregation for a field over sessions matching an expression."""
    with _client() as client:
        resp = client.get(
            "/api/spiview",
            params={"expression": expression, "spi": field, "startTime": start_time, "stopTime": end_time},
        )
        resp.raise_for_status()
        return resp.json().get("spi", {}).get(field, {}).get("values", [])


@mcp.tool()
def unique_values(field: str, expression: str = "") -> list[str]:
    """Get unique values for a field, optionally filtered by an Arkime expression."""
    with _client() as client:
        params: dict[str, Any] = {"field": field}
        if expression:
            params["expression"] = expression
        resp = client.get("/api/unique", params=params)
        resp.raise_for_status()
        return [line for line in resp.text.splitlines() if line]


@mcp.tool()
def fetch_pcap_slice(session_id: str, dest_dir: str = "/srv/ainode/scratch") -> dict:
    """Fetch the raw PCAP for one session ID into the node's scratch directory."""
    with _client() as client:
        resp = client.get(f"/api/{session_id}/pcap", params={"session": session_id})
        resp.raise_for_status()
        dest = pathlib.Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"{session_id}.pcap"
        out_path.write_bytes(resp.content)
        return {"session_id": session_id, "path": str(out_path), "bytes": len(resp.content)}


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "9002")))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
