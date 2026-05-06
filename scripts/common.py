"""Shared utilities for all pipelines.

Public API:
- ROOT, DAILY_DIR, WEEKLY_DIR, STATE_DIR
- http_get_json(url)
- load_seen(name) / save_seen(name, seen)
- mark_new(seen, items, today, key="arxiv_id")
- write_output(schedule, name, today, content)

Pipeline contract (each module under pipelines/):
    NAME: str
    SCHEDULE: "daily" | "weekly"
    def run(today: str, seen: dict) -> tuple[str, int]
        # returns (markdown_content, new_count)
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "daily"
WEEKLY_DIR = ROOT / "weekly"
STATE_DIR = ROOT / ".state"
UA = "Mozilla/5.0 (compatible; daily-papers-bot/1.0)"
TIMEOUT = 30


def http_get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _seen_path(name: str) -> Path:
    return STATE_DIR / f"{name}.json"


def load_seen(name: str) -> dict:
    """Per-pipeline seen state: { item_key: 'YYYY-MM-DD first-seen' }."""
    path = _seen_path(name)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[warn] cannot parse {path.name}: {e}", file=sys.stderr)
        return {}


def save_seen(name: str, seen: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _seen_path(name).write_text(
        json.dumps(seen, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def mark_new(seen: dict, items: list[dict], today: str, key: str = "arxiv_id") -> int:
    """Record first-seen date for new items. Returns count of newly-added entries."""
    n = 0
    for it in items:
        k = it.get(key)
        if k and k not in seen:
            seen[k] = today
            n += 1
    return n


def write_output(schedule: str, name: str, today: str, content: str) -> Path:
    """Write to daily/<name>/<date>.md or weekly/<name>/<date>.md."""
    base = DAILY_DIR if schedule == "daily" else WEEKLY_DIR
    out_dir = base / name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today}.md"
    path.write_text(content, encoding="utf-8")
    return path
