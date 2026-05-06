#!/usr/bin/env python3
"""Orchestrator — discovers and dispatches pipeline modules.

Usage:
    python3 scripts/fetch.py              # all daily pipelines
    python3 scripts/fetch.py daily        # all daily pipelines
    python3 scripts/fetch.py weekly       # all weekly pipelines
    python3 scripts/fetch.py both         # all pipelines
    python3 scripts/fetch.py <name>       # one specific pipeline by NAME

Each pipeline lives under scripts/pipelines/*.py and must expose:
    NAME: str
    SCHEDULE: "daily" | "weekly"
    def run(today, seen) -> tuple[str, int]   # returns (markdown, new_count)
"""

from __future__ import annotations

import datetime as dt
import importlib
import pkgutil
import sys
from pathlib import Path

# make 'common' and 'pipelines' importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_seen, save_seen, write_output  # noqa: E402
import pipelines as pipelines_pkg  # noqa: E402


def discover() -> list:
    """Return list of valid pipeline modules found under pipelines/."""
    out = []
    for info in pkgutil.iter_modules(pipelines_pkg.__path__):
        mod = importlib.import_module(f"pipelines.{info.name}")
        if not all(hasattr(mod, x) for x in ("NAME", "SCHEDULE", "run")):
            print(f"[warn] {info.name}: missing NAME/SCHEDULE/run; skipping", file=sys.stderr)
            continue
        if mod.SCHEDULE not in ("daily", "weekly"):
            print(f"[warn] {mod.NAME}: bad SCHEDULE={mod.SCHEDULE!r}; skipping", file=sys.stderr)
            continue
        out.append(mod)
    return out


def select(modules: list, arg: str) -> list:
    if arg in ("daily", "weekly"):
        return [m for m in modules if m.SCHEDULE == arg]
    if arg == "both":
        return modules
    # by name
    by_name = [m for m in modules if m.NAME == arg]
    if not by_name:
        print(f"[error] no pipeline matches {arg!r}. Available:", file=sys.stderr)
        for m in modules:
            print(f"  - {m.NAME} ({m.SCHEDULE})", file=sys.stderr)
        sys.exit(2)
    return by_name


def run_one(mod, today: str) -> int:
    seen = load_seen(mod.NAME)
    try:
        md, new_count = mod.run(today, seen)
    except Exception as e:
        print(f"[error] {mod.NAME} failed: {e}", file=sys.stderr)
        return 1
    path = write_output(mod.SCHEDULE, mod.NAME, today, md)
    save_seen(mod.NAME, seen)
    rel = path.relative_to(Path(__file__).resolve().parent.parent)
    print(f"[{mod.SCHEDULE}] {mod.NAME}: wrote {rel} (new={new_count}, seen-total={len(seen)})")
    return 0


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "daily"
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    modules = discover()
    if not modules:
        print("[error] no pipelines found under scripts/pipelines/", file=sys.stderr)
        return 2

    targets = select(modules, arg)
    rc = 0
    for mod in targets:
        rc |= run_one(mod, today)
    return rc


if __name__ == "__main__":
    sys.exit(main())
