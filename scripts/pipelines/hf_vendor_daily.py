"""Pipeline: HF Vendor Daily.

Scans a fixed list of HuggingFace vendor orgs for papers published OR
submitted-to-daily today (UTC). No filtering — vendors are always included.
"""

from __future__ import annotations

import urllib.parse

from common import http_get_json, mark_new

NAME = "hf-vendor-daily"
SCHEDULE = "daily"

# (label, hf_org_slug) — order = render order
ORGS: list[tuple[str, str]] = [
    ("DeepSeek",         "deepseek-ai"),
    ("Qwen (Alibaba)",   "Qwen"),
    ("Kimi (Moonshot)",  "moonshotai"),
    ("Zhipu / GLM",      "zai-org"),
    ("Zhipu / THUDM",    "THUDM"),
    ("MiniMax",          "MiniMaxAI"),
    ("ByteDance Seed",   "ByteDance-Seed"),
]


def fetch_org(org: str, today: str) -> list[dict]:
    url = f"https://huggingface.co/api/papers?author={urllib.parse.quote(org)}"
    try:
        data = http_get_json(url)
    except Exception as e:
        print(f"[warn] {NAME}: fetch {org} failed: {e}")
        return []
    if not isinstance(data, list):
        return []
    items = []
    for p in data:
        published = (p.get("publishedAt") or "")[:10]
        submitted = (p.get("submittedOnDailyAt") or "")[:10]
        if today not in (published, submitted):
            continue
        arxiv_id = p.get("id", "")
        items.append({
            "title": (p.get("title") or "").strip(),
            "arxiv_id": arxiv_id,
            "url": f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else "",
            "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
            "published": published,
            "submitted": submitted,
            "upvotes": p.get("upvotes", 0),
            "ai_summary": (p.get("ai_summary") or "").strip(),
        })
    items.sort(key=lambda x: (x.get("upvotes") or 0), reverse=True)
    return items


def render(today: str, results: list[tuple[str, list[dict]]], seen: dict) -> str:
    def is_new(aid: str) -> bool:
        first = seen.get(aid)
        return (not first) or first.startswith(today)

    total = sum(len(items) for _, items in results)
    lines = [f"# Vendor Daily — {today}", "", f"_{total} papers across {len(results)} vendors_", ""]

    for label, items in results:
        lines.append(f"## {label} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("_(no new papers today)_")
        else:
            for it in items:
                tag = f" 👍{it['upvotes']}" if it.get("upvotes") else ""
                new = " 🆕" if is_new(it["arxiv_id"]) else ""
                lines.append(f"- **[{it['title']}]({it['url']})**{tag}{new}")
                if it.get("arxiv_url"):
                    lines.append(f"  - arXiv: {it['arxiv_url']}")
                if it.get("ai_summary"):
                    lines.append(f"  - {it['ai_summary']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_🆕 = first-seen today; no marker = seen before_")
    return "\n".join(lines) + "\n"


def run(today: str, seen: dict) -> tuple[str, int]:
    results: list[tuple[str, list[dict]]] = []
    for label, slug in ORGS:
        results.append((label, fetch_org(slug, today)))

    md = render(today, results, seen)
    flat = [it for _, items in results for it in items]
    new_count = mark_new(seen, flat, today)
    return md, new_count
