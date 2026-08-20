"""Renders the shared DFIR skill library (system prompt + playbooks) into
Open WebUI's prompt-import format and opencode's AGENTS.md format, so both
frontends carry the same content from one source."""
import json
import pathlib


def render_open_webui(system_prompt: str, playbooks: dict[str, str]) -> list[dict]:
    return [
        {"title": title, "content": f"{system_prompt}\n\n---\n\n{body}"}
        for title, body in playbooks.items()
    ]


def render_agents_md(system_prompt: str, playbooks: dict[str, str]) -> str:
    sections = [system_prompt.strip(), ""]
    for title, body in playbooks.items():
        sections.append(f"## {title}\n")
        sections.append(body.strip())
        sections.append("")
    return "\n".join(sections)


def _load_markdown_dir(path: pathlib.Path) -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(path.glob("*.md"))}


def main() -> None:
    base = pathlib.Path(__file__).parent
    system_prompt = (base / "system-prompt.md").read_text(encoding="utf-8")
    playbooks = _load_markdown_dir(base / "playbooks")

    out_dir = base / "rendered"
    out_dir.mkdir(exist_ok=True)

    (out_dir / "open-webui-prompts.json").write_text(
        json.dumps(render_open_webui(system_prompt, playbooks), indent=2), encoding="utf-8"
    )
    (out_dir / "AGENTS.md").write_text(render_agents_md(system_prompt, playbooks), encoding="utf-8")
    print(f"Rendered {len(playbooks)} playbooks to {out_dir}")


if __name__ == "__main__":
    main()
