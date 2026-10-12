#!/usr/bin/env python3
"""Parse coreAstar.bib and generate core_astar.html for GitHub Pages."""
import re
import json
import html
import sys
from pathlib import Path

BIB_FILE = Path(__file__).parent / "results" / "coreAstar.bib"
OUT_FILE = Path(__file__).parent / "core_astar.html"


LATEX_MAP = {
    r"\\'a": "á", r"\\'A": "Á", r"\\`a": "à", r"\\^a": "â",
    r'\\"a': "ä", r'\\"A': "Ä", r"\\'e": "é", r"\\'E": "É",
    r"\\`e": "è", r"\\^e": "ê", r'\\"e': "ë", r"\\'i": "í",
    r"\\'I": "Í", r"\\`i": "ì", r"\\^i": "î", r'\\"i': "ï",
    r"\\'o": "ó", r"\\'O": "Ó", r"\\`o": "ò", r"\\^o": "ô",
    r'\\"o': "ö", r'\\"O': "Ö", r"\\Ho": "ő", r"\\HO": "Ő",
    r"\\'u": "ú", r"\\'U": "Ú", r"\\`u": "ù", r"\\^u": "û",
    r'\\"u': "ü", r'\\"U': "Ü", r"\\Hu": "ű", r"\\HU": "Ű",
    r"\\'c": "ć", r"\\'C": "Ć", r"\\vc": "č", r"\\vC": "Č",
    r"\\vz": "ž", r"\\vs": "š", r"\\vS": "Š",
    r"\\ss": "ß", r"\\~n": "ñ", r"\\~N": "Ñ",
    r"\\l": "ł", r"\\L": "Ł",
}


def fix_latex(s: str) -> str:
    """Convert LaTeX escape sequences to Unicode."""
    for latex, uni in LATEX_MAP.items():
        s = s.replace(latex, uni)
    # Handle {X} patterns (remove braces around single char)
    s = re.sub(r"\{\\['`\"^~Hvl]([A-Za-z])\}", lambda m: fix_latex(m.group(0)[1:-1]), s)
    s = re.sub(r"\\['`\"^~Hvl]\{([A-Za-z])\}", lambda m: fix_latex(m.group(0).replace("{", "").replace("}", "")), s)
    # Remove remaining braces
    s = s.replace("{", "").replace("}", "")
    # Remove trailing dot added by DBLP
    return s.strip().rstrip(".")


def parse_bib(bib_path: Path) -> list[dict]:
    text = bib_path.read_text(encoding="utf-8")
    entries = []
    for block in re.split(r"(?=@\w+\{)", text):
        block = block.strip()
        if not block.startswith("@"):
            continue
        m = re.match(r"@(\w+)\{([^,]+),", block)
        if not m:
            continue
        entry = {"type": m.group(1).lower(), "key": m.group(2).strip()}
        for field, val in re.findall(r"(\w+)\s*=\s*\{([^}]*)\}", block):
            entry[field.lower()] = fix_latex(val)
        entries.append(entry)
    return entries


def classify_keywords(kw_str: str) -> dict:
    tokens = {t.strip() for t in kw_str.replace(" and ", ",").split(",")}
    institutions = []
    INST_ORDER = ["BME", "ELTE", "SZTE", "SZTAKI", "Rényi", "Ericsson", "Corvinus", "PPKE", "ÓE", "Hungary"]
    for inst in INST_ORDER:
        if inst in tokens:
            institutions.append(inst)
    nationality = ""
    if "all_hungarian" in tokens:
        nationality = "all_hungarian"
    elif "mostly_hungarian" in tokens:
        nationality = "mostly_hungarian"
    elif "international" in tokens:
        nationality = "international"
    topic = ""
    if "theory" in tokens:
        topic = "theory"
    elif "applied" in tokens:
        topic = "applied"
    return {"institutions": institutions, "nationality": nationality, "topic": topic}


def build_papers(entries: list[dict]) -> list[dict]:
    papers = []
    for e in entries:
        kw = classify_keywords(e.get("keywords", ""))
        doi = e.get("doi", "").strip()
        papers.append({
            "key": e["key"],
            "title": e.get("title", ""),
            "author": e.get("author", ""),
            "venue": e.get("booktitle", e.get("journal", "")),
            "year": int(e.get("year", 0) or 0),
            "doi": doi if doi.startswith("http") else ("https://doi.org/" + doi if doi else ""),
            "institutions": kw["institutions"],
            "nationality": kw["nationality"],
            "topic": kw["topic"],
        })
    papers.sort(key=lambda p: -p["year"])
    return papers


def generate_html(papers: list[dict]) -> str:
    papers_json = json.dumps(papers, ensure_ascii=False)
    years = sorted({p["year"] for p in papers if p["year"]}, reverse=True)
    min_year = min(years) if years else 1990
    max_year = max(years) if years else 2026

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Core A* Papers — Hungarian CS Research</title>
<style>
:root {{
  --bg: #f9fafb;
  --card: #ffffff;
  --border: #e5e7eb;
  --text: #111827;
  --muted: #6b7280;
  --accent: #1d4ed8;
  --accent-bg: #eff6ff;
  --chip-bg: #f3f4f6;
  --chip-active: #1d4ed8;
  --chip-active-text: #ffffff;
  --tag-theory: #d1fae5;
  --tag-theory-text: #065f46;
  --tag-applied: #fef3c7;
  --tag-applied-text: #92400e;
  --tag-intl: #e0e7ff;
  --tag-intl-text: #3730a3;
  --tag-allhu: #fce7f3;
  --tag-allhu-text: #9d174d;
  --tag-mosthu: #f3e8ff;
  --tag-mosthu-text: #6b21a8;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #111827;
    --card: #1f2937;
    --border: #374151;
    --text: #f9fafb;
    --muted: #9ca3af;
    --accent: #60a5fa;
    --accent-bg: #1e3a5f;
    --chip-bg: #374151;
    --chip-active: #3b82f6;
    --chip-active-text: #ffffff;
    --tag-theory: #064e3b;
    --tag-theory-text: #6ee7b7;
    --tag-applied: #78350f;
    --tag-applied-text: #fcd34d;
    --tag-intl: #1e1b4b;
    --tag-intl-text: #a5b4fc;
    --tag-allhu: #500724;
    --tag-allhu-text: #f9a8d4;
    --tag-mosthu: #3b0764;
    --tag-mosthu-text: #d8b4fe;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
header {{ background: var(--card); border-bottom: 1px solid var(--border); padding: 1.25rem 1.5rem; position: sticky; top: 0; z-index: 10; }}
header h1 {{ font-size: 1.25rem; font-weight: 700; margin-bottom: 0.75rem; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }}
#search {{ flex: 1 1 200px; padding: 0.4rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text); font-size: 0.875rem; }}
#search:focus {{ outline: 2px solid var(--accent); border-color: transparent; }}
.filter-row {{ display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; padding: 0.5rem 1.5rem; border-bottom: 1px solid var(--border); background: var(--bg); }}
.filter-label {{ font-size: 0.75rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-right: 0.25rem; }}
.chip {{ display: inline-flex; align-items: center; padding: 0.2rem 0.6rem; border-radius: 9999px; font-size: 0.78rem; font-weight: 500; cursor: pointer; border: 1px solid var(--border); background: var(--chip-bg); color: var(--text); transition: background 0.1s, color 0.1s; user-select: none; }}
.chip:hover {{ background: var(--accent-bg); }}
.chip.active {{ background: var(--chip-active); color: var(--chip-active-text); border-color: transparent; }}
.chip.all-chip {{ font-weight: 600; }}
#year-filter {{ display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; }}
#year-from, #year-to {{ width: 62px; padding: 0.2rem 0.4rem; border: 1px solid var(--border); border-radius: 5px; background: var(--bg); color: var(--text); font-size: 0.8rem; }}
#status {{ padding: 0.4rem 1.5rem; font-size: 0.8rem; color: var(--muted); border-bottom: 1px solid var(--border); }}
#list {{ padding: 0.75rem 1.5rem 2rem; max-width: 900px; margin: 0 auto; }}
.paper {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 0.9rem 1rem; margin-bottom: 0.6rem; }}
.paper-title {{ font-size: 0.97rem; font-weight: 600; margin-bottom: 0.3rem; }}
.paper-title a {{ color: var(--accent); text-decoration: none; }}
.paper-title a:hover {{ text-decoration: underline; }}
.paper-title span {{ color: var(--text); }}
.paper-meta {{ font-size: 0.82rem; color: var(--muted); margin-bottom: 0.4rem; }}
.paper-tags {{ display: flex; flex-wrap: wrap; gap: 0.25rem; }}
.tag {{ display: inline-block; padding: 0.1rem 0.45rem; border-radius: 4px; font-size: 0.72rem; font-weight: 500; }}
.tag-inst {{ background: var(--chip-bg); color: var(--text); }}
.tag-theory {{ background: var(--tag-theory); color: var(--tag-theory-text); }}
.tag-applied {{ background: var(--tag-applied); color: var(--tag-applied-text); }}
.tag-intl {{ background: var(--tag-intl); color: var(--tag-intl-text); }}
.tag-allhu {{ background: var(--tag-allhu); color: var(--tag-allhu-text); }}
.tag-mosthu {{ background: var(--tag-mosthu); color: var(--tag-mosthu-text); }}
#empty {{ display: none; text-align: center; padding: 3rem; color: var(--muted); }}
footer {{ text-align: center; padding: 1rem; font-size: 0.75rem; color: var(--muted); border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <h1>Core A* Papers — Hungarian CS Research</h1>
  <div class="controls">
    <input id="search" type="search" placeholder="Search title, author, venue…">
    <div id="year-filter">
      Year: <input id="year-from" type="number" value="{min_year}" min="{min_year}" max="{max_year}">
      – <input id="year-to" type="number" value="{max_year}" min="{min_year}" max="{max_year}">
    </div>
  </div>
</header>
<div class="filter-row" id="filters-inst">
  <span class="filter-label">Institution</span>
  <span class="chip all-chip active" data-group="inst" data-val="">All</span>
  <span class="chip" data-group="inst" data-val="BME">BME</span>
  <span class="chip" data-group="inst" data-val="ELTE">ELTE</span>
  <span class="chip" data-group="inst" data-val="SZTE">SZTE</span>
  <span class="chip" data-group="inst" data-val="SZTAKI">SZTAKI</span>
  <span class="chip" data-group="inst" data-val="Rényi">Rényi</span>
  <span class="chip" data-group="inst" data-val="Ericsson">Ericsson</span>
  <span class="chip" data-group="inst" data-val="Corvinus">Corvinus</span>
  <span class="chip" data-group="inst" data-val="Hungary">Hungary</span>
</div>
<div class="filter-row" id="filters-nat">
  <span class="filter-label">Team</span>
  <span class="chip all-chip active" data-group="nat" data-val="">All</span>
  <span class="chip" data-group="nat" data-val="all_hungarian">All Hungarian</span>
  <span class="chip" data-group="nat" data-val="mostly_hungarian">Mostly Hungarian</span>
  <span class="chip" data-group="nat" data-val="international">International</span>
</div>
<div class="filter-row" id="filters-topic">
  <span class="filter-label">Topic</span>
  <span class="chip all-chip active" data-group="topic" data-val="">All</span>
  <span class="chip" data-group="topic" data-val="theory">Theory</span>
  <span class="chip" data-group="topic" data-val="applied">Applied</span>
</div>
<div id="status"></div>
<div id="list"></div>
<div id="empty">No papers match the current filters.</div>
<footer>Data from <a href="https://dblp.org" style="color:var(--accent)">DBLP</a> ·
  Generated by <a href="https://github.com/jtapolcai/corePaperList" style="color:var(--accent)">corePaperList</a></footer>
<script>
const PAPERS = {papers_json};

const NAT_LABEL = {{
  all_hungarian: "All Hungarian",
  mostly_hungarian: "Mostly Hungarian",
  international: "International"
}};
const NAT_CLASS = {{
  all_hungarian: "tag-allhu",
  mostly_hungarian: "tag-mosthu",
  international: "tag-intl"
}};

let filterInst = "", filterNat = "", filterTopic = "";
let searchQ = "", yearFrom = {min_year}, yearTo = {max_year};

function renderPaper(p) {{
  const titleEl = p.doi
    ? `<a href="${{p.doi}}" target="_blank" rel="noopener">${{esc(p.title)}}</a>`
    : `<span>${{esc(p.title)}}</span>`;
  const tags = [
    ...p.institutions.map(i => `<span class="tag tag-inst">${{esc(i)}}</span>`),
    p.nationality ? `<span class="tag ${{NAT_CLASS[p.nationality] || ''}}">${{NAT_LABEL[p.nationality] || p.nationality}}</span>` : "",
    p.topic ? `<span class="tag tag-${{p.topic}}">${{p.topic}}</span>` : "",
  ].filter(Boolean).join("");
  return `<div class="paper">
    <div class="paper-title">${{titleEl}}</div>
    <div class="paper-meta">${{esc(p.author)}} · ${{esc(p.venue)}} ${{p.year}}</div>
    <div class="paper-tags">${{tags}}</div>
  </div>`;
}}

function esc(s) {{
  return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}}

function matches(p) {{
  if (filterInst && !p.institutions.includes(filterInst)) return false;
  if (filterNat && p.nationality !== filterNat) return false;
  if (filterTopic && p.topic !== filterTopic) return false;
  if (p.year < yearFrom || p.year > yearTo) return false;
  if (searchQ) {{
    const q = searchQ.toLowerCase();
    const haystack = (p.title + " " + p.author + " " + p.venue).toLowerCase();
    if (!haystack.includes(q)) return false;
  }}
  return true;
}}

function render() {{
  const visible = PAPERS.filter(matches);
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  const status = document.getElementById("status");
  list.innerHTML = visible.map(renderPaper).join("");
  empty.style.display = visible.length ? "none" : "block";
  status.textContent = `${{visible.length}} of ${{PAPERS.length}} papers`;
}}

document.querySelectorAll(".chip").forEach(chip => {{
  chip.addEventListener("click", () => {{
    const group = chip.dataset.group;
    const val = chip.dataset.val;
    document.querySelectorAll(`.chip[data-group="${{group}}"]`).forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    if (group === "inst") filterInst = val;
    else if (group === "nat") filterNat = val;
    else if (group === "topic") filterTopic = val;
    render();
  }});
}});

document.getElementById("search").addEventListener("input", e => {{
  searchQ = e.target.value.trim();
  render();
}});
document.getElementById("year-from").addEventListener("input", e => {{
  yearFrom = parseInt(e.target.value) || {min_year};
  render();
}});
document.getElementById("year-to").addEventListener("input", e => {{
  yearTo = parseInt(e.target.value) || {max_year};
  render();
}});

render();
</script>
</body>
</html>
"""


def main():
    bib = sys.argv[1] if len(sys.argv) > 1 else str(BIB_FILE)
    out = sys.argv[2] if len(sys.argv) > 2 else str(OUT_FILE)
    entries = parse_bib(Path(bib))
    papers = build_papers(entries)
    html_content = generate_html(papers)
    Path(out).write_text(html_content, encoding="utf-8")
    print(f"Generated {out} with {len(papers)} papers")


if __name__ == "__main__":
    main()
