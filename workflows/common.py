"""Shared helpers: paths, demo date, CSV loading, and an optional Claude API call.

Every workflow runs without any API key using rule-based logic. If ANTHROPIC_API_KEY
is set (and the `anthropic` package is installed), the AI steps use Claude instead.
"""
import csv
import json
import os
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"


def today() -> date:
    """Fixed demo date so outputs are reproducible. Override with DEMO_DATE=YYYY-MM-DD."""
    return date.fromisoformat(os.environ.get("DEMO_DATE", "2026-10-15"))


def out_dir(name: str) -> Path:
    path = OUTPUT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_csv(name: str) -> list[dict]:
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_json(name: str):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.2f}"


def ai_enabled() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def ask_claude_json(prompt: str, max_tokens: int = 800):
    """Ask Claude for a JSON answer. Returns parsed JSON, or None if AI is off or the call fails."""
    if not ai_enabled():
        return None
    import anthropic

    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt + "\n\nRespond with JSON only."}],
        )
        text = msg.content[0].text
        match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        return json.loads(match.group(1)) if match else None
    except Exception as exc:  # fall back to rules on any API problem
        print(f"  (AI call failed, using rules instead: {exc})")
        return None


def mode_label() -> str:
    return "Claude API" if ai_enabled() else "rule-based (set ANTHROPIC_API_KEY to use Claude)"
