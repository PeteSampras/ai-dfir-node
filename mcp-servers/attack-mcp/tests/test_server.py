from pathlib import Path
import pytest
from attack_mcp import server

FIXTURE = Path(__file__).parent / "fixtures" / "mini-attack.json"


@pytest.fixture(autouse=True)
def patch_data_path(monkeypatch):
    monkeypatch.setattr(server, "DATA_PATH", FIXTURE)


def test_lookup_technique_found():
    result = server.lookup_technique("T1059.001")
    assert result["found"] is True
    assert result["name"] == "PowerShell"
    assert "execution" in result["tactics"]


def test_lookup_technique_case_insensitive():
    result = server.lookup_technique("t1059.001")
    assert result["found"] is True


def test_lookup_technique_not_found():
    result = server.lookup_technique("T9999")
    assert result["found"] is False
    assert result["technique_id"] == "T9999"


def test_search_techniques_matches_keyword():
    results = server.search_techniques("powershell")
    assert any(r["technique_id"] == "T1059.001" for r in results)


def test_search_techniques_no_match():
    results = server.search_techniques("nonexistent-keyword-xyz")
    assert results == []
