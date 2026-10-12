#!/usr/bin/env python3
"""
Parse coreAstar.bib (and optionally coreA.bib) and generate core_astar.html.
Both Core A* and Core A can live on the same page with a toggle switch.
Author names link to authors_profile.html when the author is in authors.json.
"""
import re
import json
import unicodedata
import sys
from pathlib import Path

BASE = Path(__file__).parent
BIB_ASTAR = BASE / "results" / "coreAstar.bib"
BIB_A     = BASE / "results" / "coreA.bib"
AUTHORS_JSON = BASE / "authors.json"
OUT_FILE  = BASE / "core_astar.html"

if len(sys.argv) > 1:
    OUT_FILE = Path(sys.argv[1])


# ── LaTeX → Unicode ──────────────────────────────────────────────────────────
# Keys are regular Python strings (NOT raw strings): "\\'a" = backslash+'a
LATEX_MAP = {
    "\\'a": "á", "\\'A": "Á", "\\`a": "à", "\\^a": "â", '\\"a': "ä", '\\"A': "Ä",
    "\\'e": "é", "\\'E": "É", "\\`e": "è", "\\^e": "ê", '\\"e': "ë",
    "\\'i": "í", "\\'I": "Í", "\\`i": "ì", "\\^i": "î", '\\"i': "ï",
    "\\'o": "ó", "\\'O": "Ó", "\\`o": "ò", "\\^o": "ô", '\\"o': "ö", '\\"O': "Ö",
    "\\Ho": "ő", "\\HO": "Ő", "\\H{o}": "ő", "\\H{O}": "Ő",
    "\\'u": "ú", "\\'U": "Ú", "\\`u": "ù", "\\^u": "û", '\\"u': "ü", '\\"U': "Ü",
    "\\Hu": "ű", "\\HU": "Ű", "\\H{u}": "ű", "\\H{U}": "Ű",
    "\\'c": "ć", "\\'C": "Ć", "\\vc": "č", "\\vC": "Č",
    "\\vz": "ž", "\\vs": "š", "\\vS": "Š",
    "\\ss": "ß", "\\~n": "ñ", "\\~N": "Ñ",
    "\\l": "ł", "\\L": "Ł",
    "\\'{a}": "á", "\\'{e}": "é", "\\'{i}": "í", "\\'{o}": "ó", "\\'{u}": "ú",
    "\\'{A}": "Á", "\\'{E}": "É", "\\'{I}": "Í", "\\'{O}": "Ó", "\\'{U}": "Ú",
    '\\"{a}': "ä", '\\"{o}': "ö", '\\"{u}': "ü",
    '\\"{A}': "Ä", '\\"{O}': "Ö", '\\"{U}': "Ü",
    "\\v{c}": "č", "\\v{C}": "Č", "\\v{s}": "š", "\\v{S}": "Š",
    "\\v{z}": "ž", "\\v{Z}": "Ž",
    "\\~{n}": "ñ", "\\~{N}": "Ñ",
}

def fix_latex(s: str) -> str:
    """Convert LaTeX escape sequences to Unicode characters."""
    # Longest-match first: sort by key length descending
    for latex, uni in sorted(LATEX_MAP.items(), key=lambda x: -len(x[0])):
        s = s.replace(latex, uni)
    # Remaining {cmd letter} patterns e.g. {\'a} or {\H o}
    s = re.sub(r"\{\\[^}]+\}", lambda m: fix_latex(m.group(0)[1:-1]), s)
    # cmd{letter} remaining e.g. \'{a}
    s = re.sub(r"\\[^{}\s]+\{[^}]+\}", lambda m: fix_latex(m.group(0)), s)
    # Remove remaining braces
    s = re.sub(r"[{}]", "", s)
    return s.strip().rstrip(".")


def format_authors(raw: str, author_lookup: dict) -> str:
    """Split 'A and B and C' → comma-separated, with links for known authors."""
    authors = [a.strip() for a in raw.split(" and ") if a.strip()]
    parts = []
    for name in authors:
        slug = author_lookup.get(normalize(name))
        if slug:
            parts.append(
                f'<a class="author-link" href="authors_profile.html#{slug}">{esc(name)}</a>'
            )
        else:
            parts.append(esc(name))
    return ", ".join(parts)


def normalize(name: str) -> str:
    """Accent-strip + lowercase for fuzzy matching."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── BibTeX parser ─────────────────────────────────────────────────────────────
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
        # Braced values
        for field, val in re.findall(r"(\w+)\s*=\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", block):
            entry[field.lower()] = fix_latex(val)
        # Bare numeric values (year = 2004)
        for field, val in re.findall(r"(\w+)\s*=\s*(\d+)\s*[,}]", block):
            if field.lower() not in entry:
                entry[field.lower()] = val
        entries.append(entry)
    return entries


def classify_keywords(kw_str: str) -> dict:
    tokens = {t.strip() for t in kw_str.replace(" and ", ",").split(",")}
    INST_ORDER = ["BME", "ELTE", "SZTE", "SZTAKI", "Rényi", "Ericsson", "Corvinus", "PPKE", "ÓE", "Hungary"]
    institutions = [i for i in INST_ORDER if i in tokens]
    nationality = next((n for n in ["all_hungarian", "mostly_hungarian", "international"] if n in tokens), "")
    topic = next((t for t in ["theory", "applied"] if t in tokens), "")
    return {"institutions": institutions, "nationality": nationality, "topic": topic}


def build_papers(entries: list[dict], label: str) -> list[dict]:
    papers = []
    for e in entries:
        kw = classify_keywords(e.get("keywords", ""))
        doi = e.get("doi", "").strip()
        papers.append({
            "key": e["key"],
            "title": e.get("title", ""),
            "author_raw": e.get("author", ""),
            "venue": e.get("booktitle", e.get("journal", "")),
            "year": int(e.get("year", 0) or 0),
            "doi": doi if doi.startswith("http") else ("https://doi.org/" + doi if doi else ""),
            "institutions": kw["institutions"],
            "nationality": kw["nationality"],
            "topic": kw["topic"],
            "tier": label,
        })
    papers.sort(key=lambda p: -p["year"])
    return papers


def load_author_lookup() -> dict:
    """Build {normalized_name: slug} from authors.json."""
    if not AUTHORS_JSON.exists():
        return {}
    authors = json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))
    lookup = {}
    for a in authors:
        lookup[normalize(a["name"])] = a["slug"]
        # Also add DBLP alias names
        if a.get("dblp_alias"):
            for alias in a["dblp_alias"].split(";"):
                alias = alias.strip()
                if alias:
                    lookup[normalize(alias)] = a["slug"]
    return lookup


def generate_html(papers_astar: list[dict], papers_a: list[dict], author_lookup: dict) -> str:
    # Pre-render author HTML for each paper
    def render_authors(p):
        return format_authors(p["author_raw"], author_lookup)

    def paper_obj(p):
        return {
            "key": p["key"],
            "title": p["title"],
            "authors_html": render_authors(p),
            "venue": p["venue"],
            "year": p["year"],
            "doi": p["doi"],
            "institutions": p["institutions"],
            "nationality": p["nationality"],
            "topic": p["topic"],
            "tier": p["tier"],
        }

    papers_json = json.dumps(
        [paper_obj(p) for p in papers_astar] + [paper_obj(p) for p in papers_a],
        ensure_ascii=False
    )

    n_astar = len(papers_astar)
    years_all = sorted({p["year"] for p in papers_astar + papers_a if p["year"]})
    min_year = min(years_all) if years_all else 1975
    max_year = max(years_all) if years_all else 2026

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Core A* / Core A Papers — Hungarian CS Research</title>
<style>
:root {{
  --bg: #f9fafb; --card: #fff; --border: #e5e7eb; --text: #111827;
  --muted: #6b7280; --accent: #1d4ed8; --accent-bg: #eff6ff;
  --chip-bg: #f3f4f6; --chip-active: #1d4ed8; --chip-active-text: #fff;
  --tag-theory: #d1fae5; --tag-theory-text: #065f46;
  --tag-applied: #fef3c7; --tag-applied-text: #92400e;
  --tag-intl: #e0e7ff; --tag-intl-text: #3730a3;
  --tag-allhu: #fce7f3; --tag-allhu-text: #9d174d;
  --tag-mosthu: #f3e8ff; --tag-mosthu-text: #6b21a8;
  --toggle-off: #e5e7eb; --toggle-on: #1d4ed8;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #111827; --card: #1f2937; --border: #374151; --text: #f9fafb;
    --muted: #9ca3af; --accent: #60a5fa; --accent-bg: #1e3a5f;
    --chip-bg: #374151; --chip-active: #3b82f6; --chip-active-text: #fff;
    --tag-theory: #064e3b; --tag-theory-text: #6ee7b7;
    --tag-applied: #78350f; --tag-applied-text: #fcd34d;
    --tag-intl: #1e1b4b; --tag-intl-text: #a5b4fc;
    --tag-allhu: #500724; --tag-allhu-text: #f9a8d4;
    --tag-mosthu: #3b0764; --tag-mosthu-text: #d8b4fe;
    --toggle-off: #374151; --toggle-on: #3b82f6;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui,-apple-system,sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
header {{ background: var(--card); border-bottom: 1px solid var(--border); padding: 1rem 1.5rem; position: sticky; top: 0; z-index: 10; }}
.header-row {{ display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; margin-bottom: 0.6rem; }}
header h1 {{ font-size: 1.15rem; font-weight: 700; }}
/* Toggle switch */
.tier-toggle {{ display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; font-weight: 600; margin-left: auto; }}
.toggle-btn {{ display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.75rem;
  border: 1px solid var(--border); border-radius: 6px; cursor: pointer; font-size: 0.82rem;
  background: var(--chip-bg); color: var(--muted); transition: all 0.15s; user-select: none; }}
.toggle-btn.active {{ background: var(--chip-active); color: var(--chip-active-text); border-color: transparent; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }}
#search {{ flex: 1 1 180px; padding: 0.35rem 0.7rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--bg); color: var(--text); font-size: 0.85rem; }}
#search:focus {{ outline: 2px solid var(--accent); border-color: transparent; }}
#year-filter {{ display: flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; }}
#year-from, #year-to {{ width: 60px; padding: 0.2rem 0.4rem; border: 1px solid var(--border);
  border-radius: 5px; background: var(--bg); color: var(--text); font-size: 0.8rem; }}
.filter-row {{ display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center;
  padding: 0.4rem 1.5rem; border-bottom: 1px solid var(--border); background: var(--bg); }}
.filter-label {{ font-size: 0.72rem; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.05em; margin-right: 0.2rem; }}
.chip {{ display: inline-flex; align-items: center; padding: 0.15rem 0.55rem;
  border-radius: 9999px; font-size: 0.75rem; font-weight: 500; cursor: pointer;
  border: 1px solid var(--border); background: var(--chip-bg); color: var(--text);
  transition: background 0.1s; user-select: none; }}
.chip.active {{ background: var(--chip-active); color: var(--chip-active-text); border-color: transparent; }}
#status {{ padding: 0.3rem 1.5rem; font-size: 0.78rem; color: var(--muted); border-bottom: 1px solid var(--border); }}
#list {{ padding: 0.75rem 1.5rem 2rem; max-width: 920px; margin: 0 auto; }}
.paper {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 0.8rem 1rem; margin-bottom: 0.5rem; }}
.paper-title {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 0.25rem; }}
.paper-title a {{ color: var(--accent); text-decoration: none; }}
.paper-title a:hover {{ text-decoration: underline; }}
.paper-title span {{ color: var(--text); }}
.paper-meta {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 0.35rem; }}
.author-link {{ color: var(--accent); text-decoration: none; }}
.author-link:hover {{ text-decoration: underline; }}
.paper-tags {{ display: flex; flex-wrap: wrap; gap: 0.2rem; }}
.tag {{ display: inline-block; padding: 0.08rem 0.4rem; border-radius: 4px; font-size: 0.7rem; font-weight: 500; }}
.tag-inst {{ background: var(--chip-bg); color: var(--text); }}
.tag-tier-astar {{ background: #fef2f2; color: #991b1b; }}
.tag-tier-a {{ background: #fff7ed; color: #9a3412; }}
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
  <div class="header-row">
    <h1>Core A* / Core A Papers — Hungarian CS Research</h1>
    <div class="tier-toggle">
      <span class="toggle-btn active" id="btn-astar" onclick="setTier('astar')">★ Core A*</span>
      <span class="toggle-btn" id="btn-a" onclick="setTier('a')">Core A</span>
      <span class="toggle-btn" id="btn-both" onclick="setTier('both')">Mindkettő</span>
    </div>
  </div>
  <div class="controls">
    <input id="search" type="search" placeholder="Cím, szerző, konferencia…">
    <div id="year-filter">
      Év: <input id="year-from" type="number" value="{min_year}" min="{min_year}" max="{max_year}">
      – <input id="year-to" type="number" value="{max_year}" min="{min_year}" max="{max_year}">
    </div>
  </div>
</header>
<div class="filter-row">
  <span class="filter-label">Intézmény</span>
  <span class="chip active" data-group="inst" data-val="">Mind</span>
  <span class="chip" data-group="inst" data-val="BME">BME</span>
  <span class="chip" data-group="inst" data-val="ELTE">ELTE</span>
  <span class="chip" data-group="inst" data-val="SZTE">SZTE</span>
  <span class="chip" data-group="inst" data-val="SZTAKI">SZTAKI</span>
  <span class="chip" data-group="inst" data-val="Rényi">Rényi</span>
  <span class="chip" data-group="inst" data-val="Ericsson">Ericsson</span>
</div>
<div class="filter-row">
  <span class="filter-label">Csapat</span>
  <span class="chip active" data-group="nat" data-val="">Mind</span>
  <span class="chip" data-group="nat" data-val="all_hungarian">Teljesen magyar</span>
  <span class="chip" data-group="nat" data-val="mostly_hungarian">Főleg magyar</span>
  <span class="chip" data-group="nat" data-val="international">Nemzetközi</span>
</div>
<div class="filter-row">
  <span class="filter-label">Téma</span>
  <span class="chip active" data-group="topic" data-val="">Mind</span>
  <span class="chip" data-group="topic" data-val="theory">Elmélet</span>
  <span class="chip" data-group="topic" data-val="applied">Alkalmazott</span>
</div>
<div id="status"></div>
<div id="list"></div>
<div id="empty">Nincs a szűrőknek megfelelő cikk.</div>
<footer>Adatok: <a href="https://dblp.org" style="color:var(--accent)">DBLP</a> ·
  <a href="https://github.com/jtapolcai/corePaperList" style="color:var(--accent)">corePaperList</a></footer>
<script>
const ALL_PAPERS = {papers_json};
const N_ASTAR = {n_astar};

const NAT_LABEL = {{
  all_hungarian: "Teljesen magyar",
  mostly_hungarian: "Főleg magyar",
  international: "Nemzetközi"
}};
const NAT_CLASS = {{
  all_hungarian: "tag-allhu",
  mostly_hungarian: "tag-mosthu",
  international: "tag-intl"
}};

let filterInst = "", filterNat = "", filterTopic = "";
let searchQ = "", yearFrom = {min_year}, yearTo = {max_year};
let tierMode = "astar"; // "astar" | "a" | "both"

function setTier(mode) {{
  tierMode = mode;
  document.getElementById("btn-astar").classList.toggle("active", mode === "astar");
  document.getElementById("btn-a").classList.toggle("active", mode === "a");
  document.getElementById("btn-both").classList.toggle("active", mode === "both");
  render();
}}

function papers() {{
  if (tierMode === "astar") return ALL_PAPERS.slice(0, N_ASTAR);
  if (tierMode === "a")     return ALL_PAPERS.slice(N_ASTAR);
  return ALL_PAPERS;
}}

function renderPaper(p) {{
  const titleEl = p.doi
    ? `<a href="${{p.doi}}" target="_blank" rel="noopener">${{p.title}}</a>`
    : `<span>${{p.title}}</span>`;
  const tierTag = tierMode === "both"
    ? `<span class="tag tag-tier-${{p.tier === "A*" ? "astar" : "a"}}">${{p.tier === "A*" ? "★ A*" : "A"}}</span>`
    : "";
  const tags = [
    tierTag,
    ...p.institutions.map(i => `<span class="tag tag-inst">${{i}}</span>`),
    p.nationality ? `<span class="tag ${{NAT_CLASS[p.nationality] || ''}}">${{NAT_LABEL[p.nationality] || p.nationality}}</span>` : "",
    p.topic ? `<span class="tag tag-${{p.topic}}">${{p.topic === "theory" ? "Elmélet" : "Alkalmazott"}}</span>` : "",
  ].filter(Boolean).join("");
  return `<div class="paper">
    <div class="paper-title">${{titleEl}}</div>
    <div class="paper-meta">${{p.authors_html}} · <em>${{p.venue}}</em> ${{p.year}}</div>
    <div class="paper-tags">${{tags}}</div>
  </div>`;
}}

function matches(p) {{
  if (filterInst && !p.institutions.includes(filterInst)) return false;
  if (filterNat && p.nationality !== filterNat) return false;
  if (filterTopic && p.topic !== filterTopic) return false;
  if (p.year < yearFrom || p.year > yearTo) return false;
  if (searchQ) {{
    const q = searchQ.toLowerCase();
    const hay = (p.title + " " + p.authors_html.replace(/<[^>]+>/g,"") + " " + p.venue).toLowerCase();
    if (!hay.includes(q)) return false;
  }}
  return true;
}}

function render() {{
  const src = papers();
  const visible = src.filter(matches);
  document.getElementById("list").innerHTML = visible.map(renderPaper).join("");
  document.getElementById("empty").style.display = visible.length ? "none" : "block";
  document.getElementById("status").textContent =
    visible.length + " / " + src.length + " cikk";
}}

document.querySelectorAll(".chip").forEach(chip => {{
  chip.addEventListener("click", () => {{
    const g = chip.dataset.group;
    document.querySelectorAll(`.chip[data-group="${{g}}"]`).forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    if (g === "inst")  filterInst  = chip.dataset.val;
    if (g === "nat")   filterNat   = chip.dataset.val;
    if (g === "topic") filterTopic = chip.dataset.val;
    render();
  }});
}});
document.getElementById("search").addEventListener("input", e => {{ searchQ = e.target.value.trim(); render(); }});
document.getElementById("year-from").addEventListener("input", e => {{ yearFrom = +e.target.value || {min_year}; render(); }});
document.getElementById("year-to").addEventListener("input", e => {{ yearTo = +e.target.value || {max_year}; render(); }});

render();
</script>
</body>
</html>
"""


def main():
    author_lookup = load_author_lookup()
    print(f"Loaded {len(author_lookup)} author name entries for linking")

    entries_astar = parse_bib(BIB_ASTAR)
    papers_astar = build_papers(entries_astar, "A*")
    print(f"Core A*: {len(papers_astar)} papers")

    papers_a = []
    if BIB_A.exists():
        entries_a = parse_bib(BIB_A)
        papers_a = build_papers(entries_a, "A")
        print(f"Core A:  {len(papers_a)} papers")

    html_out = generate_html(papers_astar, papers_a, author_lookup)
    OUT_FILE.write_text(html_out, encoding="utf-8")
    print(f"Generated {OUT_FILE}")


if __name__ == "__main__":
    main()
