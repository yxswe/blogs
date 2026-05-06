"""Pipeline package — auto-discovered by scripts/fetch.py.

Each module here MUST define:
    NAME: str             — unique slug, used as output dir + state file name
    SCHEDULE: str         — "daily" | "weekly"
    def run(today, seen) -> tuple[str, int]   # returns (markdown, new_count)
"""
