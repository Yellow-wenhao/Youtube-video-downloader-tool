from __future__ import annotations

from pathlib import Path
from typing import Mapping


PROMPTS_DIR = Path(__file__).with_name("prompts")


def load_prompt_template(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def render_prompt_template(name: str, replacements: Mapping[str, str] | None = None) -> str:
    content = load_prompt_template(name)
    for key, value in (replacements or {}).items():
        content = content.replace("{{" + key + "}}", str(value))
    return content
