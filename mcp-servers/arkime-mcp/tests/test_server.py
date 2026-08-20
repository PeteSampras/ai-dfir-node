import json
import httpx
from arkime_mcp import server


def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://arkime.test")


def test_search_sessions_returns_data(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/sessions"
        assert request.url.params["expression"] == "ip.src==10.0.0.5"
        return httpx.Response(200, json={"data": [{"id": "abc123"}]})

    monkeypatch.setattr(server, "_client", lambda: _mock_client(handler))
    result = server.search_sessions("ip.src==10.0.0.5", "2026-08-20T00:00:00Z", "2026-08-20T23:59:59Z")
    assert result == [{"id": "abc123"}]


def test_search_sessions_respects_limit(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["length"] = request.url.params["length"]
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(server, "_client", lambda: _mock_client(handler))
    server.search_sessions("ip.src==10.0.0.5", "t0", "t1", limit=25)
    assert seen["length"] == "25"


def test_get_spi_data_extracts_values(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/spiview"
        return httpx.Response(200, json={"spi": {"ip.dst": {"values": [{"key": "8.8.8.8", "count": 3}]}}})

    monkeypatch.setattr(server, "_client", lambda: _mock_client(handler))
    result = server.get_spi_data("port.dst==53", "ip.dst", "t0", "t1")
    assert result == [{"key": "8.8.8.8", "count": 3}]


def test_unique_values_splits_lines(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/unique"
        return httpx.Response(200, text="10.0.0.5\n10.0.0.9\n")

    monkeypatch.setattr(server, "_client", lambda: _mock_client(handler))
    result = server.unique_values("ip.src")
    assert result == ["10.0.0.5", "10.0.0.9"]


def test_fetch_pcap_slice_writes_file(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"FAKEPCAPBYTES")

    monkeypatch.setattr(server, "_client", lambda: _mock_client(handler))
    result = server.fetch_pcap_slice("sess-1", dest_dir=str(tmp_path))
    assert result["bytes"] == len(b"FAKEPCAPBYTES")
    assert (tmp_path / "sess-1.pcap").read_bytes() == b"FAKEPCAPBYTES"


def test_search_sessions_writes_audit_log(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "abc123"}]})

    log_path = tmp_path / "mcp-calls.jsonl"
    monkeypatch.setattr(server, "AUDIT_LOG", str(log_path))
    monkeypatch.setattr(server, "_client", lambda: _mock_client(handler))
    server.search_sessions("ip.src==10.0.0.5", "t0", "t1")
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tool"] == "search_sessions"
    assert entry["server"] == "arkime-mcp"
