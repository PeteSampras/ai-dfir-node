from skills import render


def test_render_open_webui_returns_one_entry_per_playbook():
    system_prompt = "SYSTEM"
    playbooks = {"zeek-triage": "STEP1", "suricata-review": "STEP2"}
    entries = render.render_open_webui(system_prompt, playbooks)
    assert len(entries) == 2
    names = {e["name"] for e in entries}
    assert names == {"zeek-triage", "suricata-review"}
    for e in entries:
        assert system_prompt in e["content"]


def test_render_open_webui_entries_satisfy_open_webui_prompt_form():
    """Open WebUI's PromptForm requires command + name + content; an entry with
    only title/content is rejected at import."""
    entries = render.render_open_webui("SYS", {"zeek-triage": "BODY"})
    e = entries[0]
    assert {"command", "name", "content"} <= set(e)
    assert e["command"] == "/zeek-triage"
    assert e["command"].startswith("/")


def test_render_agents_md_includes_system_prompt_and_all_playbooks():
    system_prompt = "SYSTEM PROMPT TEXT"
    playbooks = {"zeek-triage": "ZEEK STEPS", "attack-mapping": "MAP STEPS"}
    result = render.render_agents_md(system_prompt, playbooks)
    assert "SYSTEM PROMPT TEXT" in result
    assert "ZEEK STEPS" in result
    assert "MAP STEPS" in result
    assert result.index("SYSTEM PROMPT TEXT") < result.index("ZEEK STEPS")


def test_render_agents_md_playbooks_are_headed_sections():
    result = render.render_agents_md("SYS", {"zeek-triage": "BODY"})
    assert "## zeek-triage" in result
