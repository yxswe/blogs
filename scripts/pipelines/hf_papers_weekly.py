"""Pipeline: HF Papers Weekly.

Scans the past N days of HuggingFace Daily Papers, applies filters.json,
keeps papers passing the upvote threshold (or VIP-org bypass).
Dedups by arxiv_id, sorts by upvotes desc.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from common import http_get_json, mark_new

NAME = "hf-papers-weekly"
SCHEDULE = "weekly"

LOOKBACK_DAYS = 7
MIN_UPVOTES = 50

FILTERS_PATH = Path(__file__).resolve().parent.parent / "filters.json"


def load_filters() -> dict:
    if not FILTERS_PATH.exists():
        return {}
    try:
        cfg = json.loads(FILTERS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[warn] {NAME}: cannot parse filters.json: {e}", file=sys.stderr)
        return {}
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def parse_entry(entry: dict) -> dict | None:
    if not isinstance(entry, dict):
        return None
    p = entry.get("paper", {}) or {}
    arxiv_id = p.get("id") or entry.get("id", "")
    org = p.get("organization") or entry.get("organization") or {}
    org_name = org.get("name") if isinstance(org, dict) else ""
    org_full = org.get("fullname") if isinstance(org, dict) else ""
    submitter = p.get("submittedOnDailyBy") or entry.get("submittedBy") or {}
    submitter_user = submitter.get("user") if isinstance(submitter, dict) else ""
    authors = [a.get("name", "") for a in (p.get("authors") or []) if isinstance(a, dict)]
    summary = (p.get("summary") or entry.get("summary") or "").strip().replace("\n", " ")
    return {
        "title": (p.get("title") or entry.get("title") or "").strip(),
        "arxiv_id": arxiv_id,
        "url": f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else "",
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
        "summary": summary,
        "ai_summary": (p.get("ai_summary") or "").strip(),
        "ai_keywords": p.get("ai_keywords") or [],
        "upvotes": entry.get("upvotes") or p.get("upvotes") or 0,
        "submitted": (p.get("submittedOnDailyAt") or entry.get("publishedAt") or "")[:10],
        "org_name": org_name or "",
        "org_full": org_full or "",
        "submitter": submitter_user or "",
        "authors": authors,
        "github": p.get("githubRepo") or "",
        "project": p.get("projectPage") or "",
    }


def matches_filters(item: dict, cfg: dict) -> tuple[bool, list[str]]:
    """OR-combined org/submitter/author/keyword whitelist; AND min_upvotes."""
    if not cfg:
        return True, []

    reasons: list[str] = []
    org_blob = f"{item.get('org_name','')} {item.get('org_full','')}".lower()
    title = (item.get("title") or "").lower()
    summary = (item.get("summary") or "").lower()
    ai_kw_blob = " ".join(item.get("ai_keywords") or []).lower()
    submitter = (item.get("submitter") or "").lower()
    authors_blob = " ".join(item.get("authors") or []).lower()

    # VIP orgs bypass thresholds
    for o in cfg.get("always_include_orgs", []) or []:
        if o.lower() in org_blob:
            return True, [f"org:{o}*"]

    matched = False
    for o in cfg.get("organizations", []) or []:
        if o.lower() in org_blob:
            reasons.append(f"org:{o}"); matched = True; break
    for s in cfg.get("submitters", []) or []:
        if s.lower() == submitter:
            reasons.append(f"submitter:{s}"); matched = True; break
    for a in cfg.get("authors", []) or []:
        if a.lower() in authors_blob:
            reasons.append(f"author:{a}"); matched = True; break
    for kw in cfg.get("keywords", []) or []:
        kwl = kw.lower()
        if kwl in ai_kw_blob or kwl in title or kwl in summary:
            reasons.append(f"kw:{kw}"); matched = True; break

    has_any_or = any(cfg.get(k) for k in ("organizations", "submitters", "authors", "keywords"))
    if not has_any_or:
        matched = True

    if not matched:
        return False, []

    return True, reasons


def fetch_top(today: str, cfg: dict, lookback: int, min_upvotes: int) -> list[dict]:
    today_dt = dt.date.fromisoformat(today)
    by_id: dict[str, dict] = {}
    for i in range(lookback):
        d = (today_dt - dt.timedelta(days=i)).isoformat()
        url = f"https://huggingface.co/api/daily_papers?date={d}"
        try:
            data = http_get_json(url)
        except Exception as e:
            print(f"[warn] {NAME}: fetch {d} failed: {e}", file=sys.stderr)
            continue
        for entry in data:
            item = parse_entry(entry)
            if not item or not item["arxiv_id"]:
                continue
            keep, reasons = matches_filters(item, cfg)
            if not keep:
                if (item.get("upvotes") or 0) < min_upvotes:
                    continue
                reasons = [f"upvotes>={min_upvotes}"]
            else:
                is_vip = bool(reasons) and reasons[0].endswith("*")
                if not is_vip and (item.get("upvotes") or 0) < min_upvotes:
                    continue
            item["match_reasons"] = reasons
            existing = by_id.get(item["arxiv_id"])
            if not existing or (item["upvotes"] or 0) > (existing["upvotes"] or 0):
                by_id[item["arxiv_id"]] = item
    out = list(by_id.values())
    out.sort(key=lambda x: (x.get("upvotes") or 0), reverse=True)
    return out


def render(end_date: str, lookback: int, min_upvotes: int, papers: list[dict], seen: dict) -> str:
    start_date = (dt.date.fromisoformat(end_date) - dt.timedelta(days=lookback - 1)).isoformat()
    lines = [
        f"# HF Papers Weekly — {start_date} → {end_date}",
        "",
        f"_HuggingFace Daily Papers, past {lookback} days, upvotes ≥ {min_upvotes} (or VIP-org bypass)_",
        f"_{len(papers)} papers_",
        "",
    ]

    def is_new(aid: str) -> bool:
        first = seen.get(aid)
        return (not first) or first >= start_date

    if not papers:
        lines.append("_(no papers crossed the threshold this week)_")
    else:
        for it in papers:
            tag = f"👍{it['upvotes']}"
            org = it.get("org_name") or ""
            org_str = f" · {org}" if org else ""
            new = " 🆕" if is_new(it["arxiv_id"]) else ""
            submitted = it.get("submitted") or ""
            date_str = f" · {submitted}" if submitted else ""
            lines.append(f"- **[{it['title']}]({it['url']})** {tag}{new}{org_str}{date_str}")
            if it.get("arxiv_url"):
                lines.append(f"  - arXiv: {it['arxiv_url']}")
            ai = it.get("ai_summary") or it.get("summary", "")[:300]
            if ai:
                lines.append(f"  - {ai}")
            extras = []
            if it.get("github"):
                extras.append(f"[code]({it['github']})")
            if it.get("project"):
                extras.append(f"[project]({it['project']})")
            if extras:
                lines.append(f"  - {' · '.join(extras)}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_🆕 = first-seen within this week_")
    return "\n".join(lines) + "\n"


def run(today: str, seen: dict) -> tuple[str, int]:
    cfg = load_filters()
    papers = fetch_top(today, cfg, LOOKBACK_DAYS, MIN_UPVOTES)
    md = render(today, LOOKBACK_DAYS, MIN_UPVOTES, papers, seen)
    new_count = mark_new(seen, papers, today)
    return md, new_count
