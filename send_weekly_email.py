#!/usr/bin/env python3
"""Send weekly digest email for new Hungarian CORE papers.

Compares current results against a snapshot from the previous run,
finds new papers per rank, LLM-verifies each, then sends an HTML email.

Environment variables required:
  ANTHROPIC_API_KEY   – for LLM verification
  GMAIL_APP_PASSWORD  – Gmail App Password for janos.tapolca@gmail.com

Usage:
  python3 send_weekly_email.py                 # normal: only if new papers
  python3 send_weekly_email.py --force-email   # send even if no new papers
  python3 send_weekly_email.py --dry-run       # print email to stdout, no send
"""
import argparse
import json
import os
import smtplib
import sys
import time
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent / "src"))
from llm_verify import verify_paper, load_cache, save_cache

RESULTS_DIR = Path("results")
SNAPSHOT_FILE = RESULTS_DIR / "weekly_snapshot.json"
RANKS = ["A*", "A", "B", "C", "no_rank"]
RANK_LABELS = {"A*": "A★", "A": "A", "B": "B", "C": "C", "no_rank": "Nincs rang"}

RECIPIENT = "janos.tapolca@gmail.com"
SENDER = "janos.tapolca@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def rank_filename(rank: str) -> str:
    return rank.replace("*", "star")


def load_results() -> dict[str, dict]:
    """Load current papers from all rank files. Returns {rank: {key: paper}}."""
    all_papers = {}
    for rank in RANKS:
        path = RESULTS_DIR / f"hungarian_papers_core{rank_filename(rank)}.json"
        if path.exists():
            all_papers[rank] = json.loads(path.read_text(encoding="utf-8"))
        else:
            all_papers[rank] = {}
    return all_papers


def load_snapshot() -> dict[str, list[str]]:
    """Load previous run's paper keys. Returns {rank: [key, ...]}."""
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
    """Return {rank: {key: paper}} for papers not in the previous snapshot."""
    new = {}
    for rank in RANKS:
        prev_keys = set(snapshot.get(rank, []))
        curr = all_papers.get(rank, {})
        new[rank] = {k: v for k, v in curr.items() if k not in prev_keys}
    return new


def llm_check_papers(new_papers: dict, client) -> dict[str, list[dict]]:
    """Run LLM verification on new papers. Returns {rank: [verified_paper, ...]}."""
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


def _paper_row(entry: dict, rank: str) -> str:
    p = entry["paper"]
    title = p.get("title", "N/A")
    venue = p.get("venue", "")
    year = p.get("year", "")
    pages = p.get("pages", "")
    authors = ", ".join(a[0] for a in p.get("authors", []))
    ee = p.get("ee", "")
    link = f'<a href="{ee}" style="color:#1a73e8">{title}</a>' if ee else title

    flag_html = ""
    if entry.get("flagged"):
        conf = entry.get("confidence", "low")[0].upper()
        reason = entry.get("reason", "")
        flag_html = (
            f'<br><span style="color:#c0392b;font-size:.85em">⚠️ [{conf}] {reason}</span>'
        )

    return (
        f"<tr>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #eee'>{link}{flag_html}</td>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #eee;white-space:nowrap'>{venue} {year}</td>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #eee;font-size:.85em;color:#555'>{pages}</td>"
        f"<td style='padding:4px 8px;border-bottom:1px solid #eee;font-size:.85em;color:#444'>{authors}</td>"
        f"</tr>"
    )


RANK_COLORS = {
    "A*": "#1a5276", "A": "#1f618d", "B": "#2471a3", "C": "#5d8aa8", "no_rank": "#888",
}


def build_html(verified: dict[str, list], today: str, total_new: int) -> str:
    sections = []
    for rank in RANKS:
        papers = verified.get(rank, [])
        if not papers:
            continue
        color = RANK_COLORS.get(rank, "#333")
        label = RANK_LABELS.get(rank, rank)
        flagged_count = sum(1 for e in papers if e.get("flagged"))
        flag_note = (
            f' <span style="color:#c0392b;font-size:.85em">({flagged_count} ellenőrzésre szorul)</span>'
            if flagged_count else ""
        )
        rows = "\n".join(_paper_row(e, rank) for e in papers)
        sections.append(f"""
<h2 style="color:{color};margin-top:28px;border-bottom:2px solid {color};padding-bottom:4px">
  CORE {label} — {len(papers)} új cikk{flag_note}
</h2>
<table style="width:100%;border-collapse:collapse;font-size:.93em">
  <thead>
    <tr style="background:#f4f4f4">
      <th style="text-align:left;padding:4px 8px">Cím</th>
      <th style="text-align:left;padding:4px 8px">Helyszín</th>
      <th style="text-align:left;padding:4px 8px">Oldalak</th>
      <th style="text-align:left;padding:4px 8px">Szerzők</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>""")

    body_sections = "\n".join(sections) if sections else "<p>Nincs új cikk.</p>"
    total_flagged = sum(
        1 for rank in RANKS for e in verified.get(rank, []) if e.get("flagged")
    )
    flag_summary = (
        f'<p style="color:#c0392b">⚠️ {total_flagged} cikknél az LLM ellenőrzést javasol '
        f'(short paper / helytelen besorolás gyanúja).</p>'
        if total_flagged else
        '<p style="color:#27ae60">✓ Az LLM szerint minden cikk helyesen van besorolva.</p>'
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{font-family:Arial,sans-serif;max-width:900px;margin:auto;color:#222}}</style>
</head><body>
<h1 style="color:#1a5276">Magyar CORE cikkek — heti összefoglaló ({today})</h1>
<p>Az elmúlt héten <strong>{total_new}</strong> új cikk lett találva.</p>
{flag_summary}
{body_sections}
<hr style="margin-top:40px">
<p style="font-size:.8em;color:#888">
  Automatikusan generált — <a href="https://jtapolcai.github.io/corePaperList/">corePaperList</a>
</p>
</body></html>"""


def send_email(html: str, today: str, dry_run: bool = False) -> None:
    subject = f"[corePaperList] Heti CORE cikk összefoglaló — {today}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER
    msg["To"] = RECIPIENT
    msg.attach(MIMEText(html, "html", "utf-8"))

    if dry_run:
        print("=== DRY RUN — email tartalma ===")
        print(f"To: {RECIPIENT}")
        print(f"Subject: {subject}")
        print(html[:2000])
        return

    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not password:
        sys.exit("GMAIL_APP_PASSWORD environment variable is not set")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER, password)
        server.sendmail(SENDER, [RECIPIENT], msg.as_string())
    print(f"Email elküldve → {RECIPIENT}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-email", action="store_true",
                        help="Send email even if no new papers found")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print email to stdout instead of sending")
    args = parser.parse_args()

    today = date.today().isoformat()
    all_papers = load_results()
    snapshot = load_snapshot()
    new_papers = find_new_papers(all_papers, snapshot)
    total_new = sum(len(v) for v in new_papers.values())

    print(f"Új cikkek: {total_new}")
    for rank in RANKS:
        n = len(new_papers.get(rank, {}))
        if n:
            print(f"  {rank}: {n}")

    if total_new == 0 and not args.force_email and not args.dry_run:
        print("Nincs új cikk, email nem kerül kiküldésre.")
        save_snapshot(all_papers)
        return

    client = anthropic.Anthropic()
    print("LLM ellenőrzés futtatása...")
    verified = llm_check_papers(new_papers, client)

    html = build_html(verified, today, total_new)
    send_email(html, today, dry_run=args.dry_run)

    save_snapshot(all_papers)


if __name__ == "__main__":
    main()
