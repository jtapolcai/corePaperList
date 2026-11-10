#!/usr/bin/env python3
"""Quick test: send one paper as email via Resend.com.

Usage:
  RESEND_API_KEY=re_... python3 test_email.py recipient@example.com
"""
import json, os, sys
from pathlib import Path

import requests

recipient = sys.argv[1] if len(sys.argv) > 1 else "janos.tapolcai@gmail.com"
api_key = os.environ.get("RESEND_API_KEY")
if not api_key:
    sys.exit("Add meg: RESEND_API_KEY=re_... python3 test_email.py")

# Pick the first A* paper as a test
papers_file = Path("results/hungarian_papers_coreAstar.json")
papers = json.loads(papers_file.read_text())
key, paper = next(iter(papers.items()))

title_text = paper.get("title", "?")
venue = paper.get("venue", "")
year = paper.get("year", "")
authors = ", ".join(a[0] for a in paper.get("authors", []))
ee = paper.get("ee", "")
link = f'<a href="{ee}">{title_text}</a>' if ee else title_text

html = f"""<html><body style="font-family:Arial,sans-serif;max-width:800px;margin:auto">
<h1>corePaperList — email teszt</h1>
<p>Ez egy teszt email. Az alábbi cikk jelenne meg a heti összefoglalóban:</p>
<h2>🥇 CORE A★</h2>
<ul>
  <li>{link}<br>
  <small>{authors} &nbsp;·&nbsp; {venue} {year}</small></li>
</ul>
<hr>
<p style="color:#888;font-size:.85em">
  <a href="https://jtapolcai.github.io/corePaperList/">corePaperList</a>
</p>
</body></html>"""

resp = requests.post(
    "https://api.resend.com/emails",
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "from": "corePaperList <onboarding@resend.dev>",
        "to": [recipient],
        "subject": "[TEST] corePaperList heti összefoglaló",
        "html": html,
    },
    timeout=30,
)
if resp.ok:
    print(f"✅ Email elküldve → {recipient}  (id: {resp.json().get('id')})")
else:
    print(f"❌ Hiba {resp.status_code}: {resp.text}")
