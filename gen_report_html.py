#!/usr/bin/env python3
"""
Generate report.html — a web summary page for the CS researcher evaluation report.
Embeds Chart.js charts and key statistics from the results JSONs.
Links to downloadable PDFs with timestamps from report_meta.json.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

RESULTS_DIR = "results"
AUTHORS_FILE = "authors.json"
META_FILE = "report_meta.json"
OUT_FILE = "report.html"


def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def classify_category(classified):
    if "theory" in classified:
        return "theory"
    if "applied" in classified:
        return "applied"
    return "unknown"


def papers_by_year_and_category(filename):
    papers = load_json(os.path.join(RESULTS_DIR, filename), {})
    counts = defaultdict(lambda: {"theory": 0, "applied": 0, "unknown": 0})
    for paper in papers.values():
        try:
            year = int(paper.get("year", 0))
        except (ValueError, TypeError):
            continue
        if year < 1970 or year > 2030:
            continue
        cat = classify_category(paper.get("classfiied", []))
        counts[year][cat] += 1
    return counts


def papers_by_year_total(filename):
    papers = load_json(os.path.join(RESULTS_DIR, filename), {})
    counts = defaultdict(int)
    for paper in papers.values():
        try:
            year = int(paper.get("year", 0))
        except (ValueError, TypeError):
            continue
        if year < 1970 or year > 2030:
            continue
        counts[year] += 1
    return counts


def make_year_series(counts):
    years = sorted(counts.keys())
    return {
        "years": years,
        "theory": [counts[y]["theory"] for y in years],
        "applied": [counts[y]["applied"] for y in years],
        "unknown": [counts[y]["unknown"] for y in years],
    }


def make_total_series(counts):
    years = sorted(counts.keys())
    return {"years": years, "total": [counts[y] for y in years]}


# --- Load data ---
print("Loading data …")
authors = load_json(AUTHORS_FILE, [])
meta = load_json(META_FILE, {})

hung_astar_counts = papers_by_year_and_category("hungarian_papers_coreAstar.json")
abroad_astar_counts = papers_by_year_and_category("already_abroad_papers_coreAstar.json")
hung_a_counts = papers_by_year_and_category("hungarian_papers_coreA.json")

hung_astar_series = make_year_series(hung_astar_counts)
abroad_astar_series = make_year_series(abroad_astar_counts)

# Key statistics
total_hung_astar = sum(
    v for counts in hung_astar_counts.values() for v in counts.values()
)
total_hung_astar_theory = sum(v["theory"] for v in hung_astar_counts.values())
total_hung_astar_applied = sum(v["applied"] for v in hung_astar_counts.values())
total_abroad_astar = sum(
    v for counts in abroad_astar_counts.values() for v in counts.values()
)
active_authors = sum(1 for a in authors if a.get("works") == "hungary" and a.get("core_astar", 0) > 0)
all_astar_authors = sum(1 for a in authors if a.get("core_astar", 0) > 0)

gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

hu_pdf_url = meta.get("hu_pdf_url", "")
en_pdf_url = meta.get("en_pdf_url", "")
hu_pdf_date = meta.get("hu_pdf_date", "")
en_pdf_date = meta.get("en_pdf_date", "")
hu_pdf_label = f"Utoljára frissítve: {hu_pdf_date}" if hu_pdf_date else ""
en_pdf_label = f"Last updated: {en_pdf_date}" if en_pdf_date else ""
show_pdf_section = bool(hu_pdf_url or en_pdf_url)

def _pdf_card(title, url, date_label):
    date_html = f'<span class="pdf-date">{date_label}</span>' if date_label else ""
    return f'<div class="pdf-card"><h3>{title}</h3>{date_html}<a href="{url}">{"PDF letöltése" if "hu" in url else "Download PDF"}</a></div>'

if show_pdf_section:
    cards = ""
    if hu_pdf_url:
        cards += _pdf_card("Magyar nyelvű jelentés", hu_pdf_url, hu_pdf_label)
    if en_pdf_url:
        cards += _pdf_card("English Report", en_pdf_url, en_pdf_label)
    pdf_section_html = f"""
<h2>Letölthető jelentések</h2>
<div class="pdf-section">
  <p style="margin:0 0 4px;color:var(--muted);font-size:0.85rem;">A PDF-ek LaTeX-ből fordítva, manuálisan töltve fel.</p>
  <div class="pdf-grid">{cards}</div>
</div>"""
else:
    pdf_section_html = ""

# --- Embed data as JSON ---
chart_data = json.dumps({
    "hung_astar": hung_astar_series,
    "abroad_astar": abroad_astar_series,
}, ensure_ascii=False)

stats = json.dumps({
    "total_hung_astar": total_hung_astar,
    "total_hung_astar_theory": total_hung_astar_theory,
    "total_hung_astar_applied": total_hung_astar_applied,
    "total_abroad_astar": total_abroad_astar,
    "active_authors": active_authors,
    "all_astar_authors": all_astar_authors,
}, ensure_ascii=False)

html = f"""<!doctype html>
<html lang="hu">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Magyar CS kutatók — CORE A* elemzés</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root {{
  --bg: #ffffff;
  --surface: #f8f9fa;
  --border: #dee2e6;
  --text: #212529;
  --muted: #6c757d;
  --accent: #1a73e8;
  --theory: #4e79a7;
  --applied: #f28e2b;
  --unknown: #bab0ac;
  --hungary: #2ca02c;
  --abroad: #9467bd;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #1a1a2e;
    --surface: #16213e;
    --border: #0f3460;
    --text: #e0e0e0;
    --muted: #a0a0b0;
    --accent: #4d9de0;
  }}
}}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0;
  padding: 0;
}}
.container {{ max-width: 960px; margin: 0 auto; padding: 0 16px 48px; }}
header {{
  background: var(--accent);
  color: #fff;
  padding: 28px 16px 20px;
  margin-bottom: 32px;
}}
header .container {{ padding-top: 0; padding-bottom: 0; }}
header h1 {{ margin: 0 0 6px; font-size: 1.5rem; }}
header p {{ margin: 0; opacity: 0.85; font-size: 0.95rem; }}
.lang-switch {{ float: right; font-size: 0.85rem; opacity: 0.9; }}
h2 {{ font-size: 1.2rem; margin: 32px 0 12px; border-bottom: 2px solid var(--border); padding-bottom: 6px; }}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}}
.stat-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}}
.stat-card .value {{ font-size: 2rem; font-weight: 700; color: var(--accent); line-height: 1.1; }}
.stat-card .label {{ font-size: 0.8rem; color: var(--muted); margin-top: 4px; }}
.chart-wrap {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
  position: relative;
}}
.chart-wrap canvas {{ max-height: 320px; }}
.pdf-section {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}}
.pdf-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-top: 12px;
}}
.pdf-card {{
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.pdf-card h3 {{ margin: 0; font-size: 1rem; }}
.pdf-card .pdf-date {{ font-size: 0.8rem; color: var(--muted); }}
.pdf-card a {{
  display: inline-block;
  background: var(--accent);
  color: #fff;
  text-decoration: none;
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 0.9rem;
  text-align: center;
}}
.pdf-card a:hover {{ opacity: 0.88; }}
footer {{
  border-top: 1px solid var(--border);
  padding: 16px 0;
  font-size: 0.8rem;
  color: var(--muted);
  text-align: center;
}}
</style>
</head>
<body>
<header>
  <div class="container">
    <span class="lang-switch">HU | <a href="report_en.html" style="color:#fff">EN</a></span>
    <h1>Magyar CS kutatók — CORE A* konferencia elemzés</h1>
    <p>Generálva: {gen_time} · <a href="https://jtapolcai.github.io/corePaperList/" style="color:#fff">Vissza a főoldalra</a></p>
  </div>
</header>
<div class="container">

<h2>Összefoglalás</h2>
<div class="stats-grid" id="stats-grid">
  <div class="stat-card"><div class="value" id="stat-hung-astar">—</div><div class="label">CORE A* cikk<br>(magyarországi)</div></div>
  <div class="stat-card"><div class="value" id="stat-abroad-astar">—</div><div class="label">CORE A* cikk<br>(külföldre ment)</div></div>
  <div class="stat-card"><div class="value" id="stat-theory">—</div><div class="label">elméleti cikk<br>(MTA III. oszt.)</div></div>
  <div class="stat-card"><div class="value" id="stat-applied">—</div><div class="label">alkalmazott cikk<br>(MTA VI. oszt.)</div></div>
  <div class="stat-card"><div class="value" id="stat-authors">—</div><div class="label">aktív kutató<br>(Magyarországon)</div></div>
</div>

<h2>CORE A* cikkek évente — Magyarországon dolgozók</h2>
<div class="chart-wrap"><canvas id="chart-hung-astar"></canvas></div>

<h2>CORE A* cikkek évente — Külföldre ment kutatók</h2>
<div class="chart-wrap"><canvas id="chart-abroad-astar"></canvas></div>

{pdf_section_html}

</div><!-- /container -->

<footer>
  Adatforrás: DBLP · CORE · Automatikusan frissítve minden hétfőn ·
  <a href="https://github.com/jtapolcai/corePaperList">GitHub</a>
</footer>

<script>
const DATA = {chart_data};
const STATS = {stats};

// Fill stats
document.getElementById("stat-hung-astar").textContent = STATS.total_hung_astar;
document.getElementById("stat-abroad-astar").textContent = STATS.total_abroad_astar;
document.getElementById("stat-theory").textContent = STATS.total_hung_astar_theory;
document.getElementById("stat-applied").textContent = STATS.total_hung_astar_applied;
document.getElementById("stat-authors").textContent = STATS.active_authors;

const darkMode = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
const gridColor = darkMode ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.07)";
const textColor = darkMode ? "#e0e0e0" : "#212529";

function stackedBarChart(canvasId, series, title) {{
  const ctx = document.getElementById(canvasId).getContext("2d");
  new Chart(ctx, {{
    type: "bar",
    data: {{
      labels: series.years,
      datasets: [
        {{ label: "Elméleti (III. oszt.)", data: series.theory, backgroundColor: "#4e79a7", stack: "s" }},
        {{ label: "Alkalmazott (VI. oszt.)", data: series.applied, backgroundColor: "#f28e2b", stack: "s" }},
        {{ label: "Ismeretlen", data: series.unknown, backgroundColor: "#bab0ac", stack: "s" }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ labels: {{ color: textColor }} }},
        title: {{ display: false }},
      }},
      scales: {{
        x: {{ stacked: true, ticks: {{ color: textColor, maxRotation: 45, autoSkipPadding: 8 }}, grid: {{ color: gridColor }} }},
        y: {{ stacked: true, beginAtZero: true, ticks: {{ color: textColor }}, grid: {{ color: gridColor }} }},
      }},
    }}
  }});
}}

stackedBarChart("chart-hung-astar", DATA.hung_astar);
stackedBarChart("chart-abroad-astar", DATA.abroad_astar);
</script>
</body>
</html>
"""

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Written: {OUT_FILE}")
print(f"  Stats: hung_astar={total_hung_astar}, abroad_astar={total_abroad_astar}, active_authors={active_authors}")
