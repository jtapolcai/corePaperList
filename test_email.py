#!/usr/bin/env python3
"""Test: send one A* paper through the same code path as the weekly update.

Usage:
  RESEND_API_KEY=re_... python3 test_email.py recipient@example.com
"""
import json, os, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

recipient = sys.argv[1] if len(sys.argv) > 1 else "janos.tapolcai@gmail.com"

import send_weekly_email as swe

# Initialise the global author slug map (normally done in swe.main())
swe._author_slugs = swe.load_author_slugs()

# Pick the first A* paper as a fake "new" paper
papers_file = Path("results/hungarian_papers_coreAstar.json")
papers = json.loads(papers_file.read_text())
key, paper = next(iter(papers.items()))

verified = {
    rank: [] for rank in swe.RANKS
}
verified["A*"] = [{"key": key, "paper": paper, "flagged": False, "confidence": "high", "reason": ""}]

today = date.today().isoformat()
body = swe.build_markdown(verified, today, total_new=1, recipients=[recipient])
title = f"[TEST] corePaperList heti összefoglaló — {today}"

swe.send_emails([recipient], title, body)
