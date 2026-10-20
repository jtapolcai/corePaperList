#!/usr/bin/env python3
"""Weekly digest of new Hungarian CORE papers, posted as a GitHub Issue.

Compares current results against a snapshot from the previous run,
finds new papers per rank, LLM-verifies each, then creates a GitHub Issue.
GitHub automatically emails the issue to all repository watchers.

Recipients are read from email_recipients.json (list of email strings);
they are listed in the issue body so they can subscribe if not already watching.

Environment variables required:
  ANTHROPIC_API_KEY  – for LLM verification
  GITHUB_TOKEN       – automatically provided by GitHub Actions (no setup needed)
  GITHUB_REPOSITORY  – automatically provided by GitHub Actions (e.g. "owner/repo")

Usage:
  python3 send_weekly_email.py                 # normal: only if new papers
  python3 send_weekly_email.py --force-post    # post even if no new papers
  python3 send_weekly_email.py --dry-run       # print to stdout, no GitHub issue
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent / "src"))
from llm_verify import verify_paper, load_cache, save_cache

RESULTS_DIR = Path("results")
SNAPSHOT_FILE = RESULTS_DIR / "weekly_snapshot.json"
RECIPIENTS_FILE = Path("email_recipients.json")
RANKS = ["A*", "A", "B", "C", "no_rank"]
RANK_LABELS = {"A*": "A★", "A": "A", "B": "B", "C": "C", "no_rank": "Nincs rang"}
RANK_EMOJI = {"A*": "🥇", "A": "🥈", "B": "🥉", "C": "📄", "no_rank": "📋"}


def load_recipients() -> list[str]:
    if RECIPIENTS_FILE.exists():
        try:
            return json.loads(RECIPIENTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def rank_filename(rank: str) -> str:
    return rank.replace("*", "star")


def load_results() -> dict[str, dict]:
    all_papers = {}
    for rank in RANKS:
        path = RESULTS_DIR / f"hungarian_papers_core{rank_filename(rank)}.json"
        if path.exists():
            all_papers[rank] = json.loads(path.read_text(encoding="utf-8"))
        else:
            all_papers[rank] = {}
    return all_papers


def load_snapshot() -> dict[str, list[str]]:
    if SNAPSHOT_FILE.exists():
        try:
            return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {rank: [] for rank in RANKS}


def save_snapshot(all_papers: dict[str, dict]) -> None:
    snapshot = {rank: list(papers.keys()) for rank, papers in all_papers.items()}
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, indent=2))


def find_new_papers(all_papers: dict, snapshot: dict) -> dict[str, dict]:
    new = {}
    for rank in RANKS:
        prev_keys = set(snapshot.get(rank, []))
        curr = all_papers.get(rank, {})
        new[rank] = {k: v for k, v in curr.items() if k not in prev_keys}
    return new


def llm_check_papers(new_papers: dict, client) -> dict[str, list[dict]]:
    cache = load_cache()
    verified: dict[str, list] = {rank: [] for rank in RANKS}

    for rank in RANKS:
        for key, paper in new_papers.get(rank, {}).items():
            if key not in cache:
                result = verify_paper(paper, rank, client)
                result["rank"] = rank
                cache[key] = result
                save_cache(cache)
                time.sleep(0.12)
            else:
                result = cache[key]

            verified[rank].append({
                "key": key,
                "paper": paper,
                "flagged": result.get("flagged", False),
                "confidence": result.get("confidence", "low"),
                "reason": result.get("reason", ""),
            })

    return verified


def _paper_line(entry: dict) -> str:
    p = entry["paper"]
    title = p.get("title", "N/A")
    venue = p.get("venue", "")
    year = p.get("year", "")
    pages = p.get("pages", "")
    authors = ", ".join(a[0] for a in p.get("authors", []))
    ee = p.get("ee", "")

    link = f"[{title}]({ee})" if ee else title
    meta = " · ".join(x for x in [venue, str(year), pages] if x)
    flag = ""
    if entry.get("flagged"):
        conf = entry.get("confidence", "low")[0].upper()
        reason = entry.get("reason", "")
        flag = f"\n  > ⚠️ [{conf}] {reason}"

    return f"- {link}  \n  {authors}  \n  _{meta}_{flag}"


def build_markdown(verified: dict[str, list], today: str, total_new: int,
                   recipients: list[str]) -> str:
    sections = []
    for rank in RANKS:
        papers = verified.get(rank, [])
        if not papers:
            continue
        emoji = RANK_EMOJI.get(rank, "")
        label = RANK_LABELS.get(rank, rank)
        flagged_count = sum(1 for e in papers if e.get("flagged"))
        flag_note = f" · ⚠️ {flagged_count} ellenőrzésre szorul" if flagged_count else ""
        lines = "\n".join(_paper_line(e) for e in papers)
        sections.append(
            f"## {emoji} CORE {label} — {len(papers)} új cikk{flag_note}\n\n{lines}"
        )

    body_sections = "\n\n---\n\n".join(sections) if sections else "_Nincs új cikk._"

    total_flagged = sum(
        1 for rank in RANKS for e in verified.get(rank, []) if e.get("flagged")
    )
    flag_summary = (
        f"⚠️ **{total_flagged} cikknél az LLM ellenőrzést javasol** "
        f"(short paper / helytelen besorolás gyanúja)."
        if total_flagged else
        "✅ Az LLM szerint minden cikk helyesen van besorolva."
    )

    recipients_note = ""
    if recipients:
        mentions = ", ".join(recipients)
        recipients_note = f"\n\n_Értesítési lista: {mentions}_"

    return f"""# Magyar CORE cikkek — heti összefoglaló ({today})

Az elmúlt héten **{total_new}** új cikk lett találva.

{flag_summary}

---

{body_sections}

---

_Automatikusan generált — [corePaperList](https://jtapolcai.github.io/corePaperList/)_{recipients_note}
"""


def post_github_issue(title: str, body: str, dry_run: bool = False) -> None:
    if dry_run:
        print("=== DRY RUN — GitHub Issue tartalma ===")
        print(f"Title: {title}")
        print(body[:3000])
        return

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")

    if not token:
        sys.exit("GITHUB_TOKEN environment variable is not set")
    if not repo:
        sys.exit("GITHUB_REPOSITORY environment variable is not set")

    url = f"https://api.github.com/repos/{repo}/issues"
    payload = json.dumps({
        "title": title,
        "body": body,
        "labels": ["weekly-digest"],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            issue = json.loads(resp.read())
            print(f"GitHub Issue létrehozva → {issue['html_url']}")
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()
        sys.exit(f"GitHub API hiba {e.code}: {body_err}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-post", action="store_true",
                        help="Post issue even if no new papers found")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print to stdout instead of creating GitHub Issue")
    args = parser.parse_args()

    today = date.today().isoformat()
    recipients = load_recipients()
    all_papers = load_results()
    snapshot = load_snapshot()
    new_papers = find_new_papers(all_papers, snapshot)
    total_new = sum(len(v) for v in new_papers.values())

    print(f"Új cikkek: {total_new}")
    for rank in RANKS:
        n = len(new_papers.get(rank, {}))
        if n:
            print(f"  {rank}: {n}")

    if total_new == 0 and not args.force_post and not args.dry_run:
        print("Nincs új cikk, GitHub Issue nem jön létre.")
        save_snapshot(all_papers)
        return

    client = anthropic.Anthropic()
    print("LLM ellenőrzés futtatása...")
    verified = llm_check_papers(new_papers, client)

    body = build_markdown(verified, today, total_new, recipients)
    title = f"[Weekly] Magyar CORE cikkek — {today}"
    post_github_issue(title, body, dry_run=args.dry_run)

    save_snapshot(all_papers)


if __name__ == "__main__":
    main()
