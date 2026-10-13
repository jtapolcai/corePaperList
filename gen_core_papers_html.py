#!/usr/bin/env python3
"""
Generate core_papers.html from JSON source files instead of BibTeX.
JSON files have proper Unicode author names (no LaTeX encoding).
Author names link to authors_profile.html when the author is in authors.json.
"""
import re
import json
import unicodedata
import sys
from pathlib import Path

BASE = Path(__file__).parent
RESULTS = BASE / "results"
JSON_HUN_ASTAR = RESULTS / "hungarian_papers_coreAstar.json"
JSON_ABR_ASTAR = RESULTS / "already_abroad_papers_coreAstar.json"
JSON_HUN_A     = RESULTS / "hungarian_papers_coreA.json"
JSON_ABR_A     = RESULTS / "already_abroad_papers_coreA.json"
JSON_HUN_B     = RESULTS / "hungarian_papers_coreB.json"
JSON_ABR_B     = RESULTS / "already_abroad_papers_coreB.json"
JSON_HUN_C     = RESULTS / "hungarian_papers_coreC.json"
JSON_ABR_C     = RESULTS / "already_abroad_papers_coreC.json"
JSON_HUN_NR    = RESULTS / "hungarian_papers_coreno_rank.json"
JSON_ABR_NR    = RESULTS / "already_abroad_papers_coreno_rank.json"
AUTHORS_JSON    = BASE / "authors.json"
AUTHOR_PIDS_JSON = RESULTS / "author_pids.json"
OUT_FILE       = BASE / "core_papers.html"

if len(sys.argv) > 1:
    OUT_FILE = Path(sys.argv[1])

GITHUB_REPO   = "jtapolcai/corePaperList"
GITHUB_BRANCH = "main"

_DBLP_SUFFIX = re.compile(r"\s+\d{4}$")  # trailing " 0001", " 0002", etc.


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def github_add_author_url(name: str, slug: str) -> str:
    from urllib.parse import quote
    template = json.dumps({
        "name": name, "slug": slug,
        "dblp_url": "", "mtmt_id": "", "mta_att_id": "", "mtmt_name": "",
        "category": "theory", "mtmt_status": "", "works": "",
        "affiliations": "", "homepage": "", "note": "",
    }, ensure_ascii=False, indent=2)
    encoded = quote(template, safe="")
    return (
        f"https://github.com/{GITHUB_REPO}/new/{GITHUB_BRANCH}"
        f"?filename=profiles/{slug}.json&value={encoded}"
    )


GITHUB_REPO_CONST = GITHUB_REPO
GITHUB_BRANCH_CONST = GITHUB_BRANCH


def normalize(name: str) -> str:
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def clean_name(name: str) -> str:
    """Strip DBLP disambiguation suffix for display."""
    return _DBLP_SUFFIX.sub("", name).strip()


def load_author_data() -> tuple[dict, dict, dict, dict]:
    """
    Returns (name_to_slug, slug_to_category, name_to_dblp_url, pid_to_slug).
    pid_to_slug maps bare DBLP PIDs (e.g. '96/3128') to slugs for exact disambiguation.
    """
    if not AUTHORS_JSON.exists():
        return {}, {}, {}, {}
    authors = json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))
    lookup   = {}
    category = {}
    pid_to_slug: dict = {}
    for a in authors:
        slug = a["slug"]
        name = a["name"]
        lookup[normalize(name)] = slug
        stripped = _DBLP_SUFFIX.sub("", name).strip()
        if stripped != name:
            lookup.setdefault(normalize(stripped), slug)
        if a.get("dblp_alias"):
            for alias in a["dblp_alias"].split(";"):
                alias = alias.strip()
                if alias:
                    lookup.setdefault(normalize(alias), slug)
        category[slug] = a.get("category") or ""
        # Extract bare PID from dblp_url, e.g. 'https://dblp.org/pid/96/3128' → '96/3128'
        dblp_url = a.get("dblp_url", "")
        pid_match = re.search(r"/pid/(.+?)(?:\.html)?$", dblp_url)
        if pid_match:
            pid_to_slug[pid_match.group(1).strip("/")] = slug
    # Build name → DBLP URL from author_pids.json (scraped pids)
    pid_map: dict = {}
    if AUTHOR_PIDS_JSON.exists():
        try:
            pid_map = json.loads(AUTHOR_PIDS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return lookup, category, pid_map, pid_to_slug


def format_authors(authors: list, author_lookup: dict, pid_map: dict | None = None,
                   pid_to_slug: dict | None = None) -> str:
    """Render author list as comma-separated HTML with profile links.
    Known authors link to their profile; unknown authors open the add-author modal.
    When author entry is [name, dblp_pid], uses PID for exact disambiguation."""
    parts = []
    pid_map = pid_map or {}
    pid_to_slug = pid_to_slug or {}
    for entry in authors:
        pid_hint = None
        if isinstance(entry, list):
            name = entry[0] if entry else ""
            pid_hint = entry[1] if len(entry) > 1 else None
        else:
            name = entry
        display = clean_name(name)
        # PID-based lookup first (exact disambiguation), then name-based fallback
        slug = (
            (pid_to_slug.get(pid_hint) if pid_hint else None)
            or author_lookup.get(normalize(name))
            or author_lookup.get(normalize(display))
        )
        if slug:
            parts.append(
                f'<a class="author-link" href="authors_profile.html#{slug}">{esc(display)}</a>'
            )
        else:
            new_slug = slugify(display)
            # Use PID hint to construct DBLP URL when available
            if pid_hint:
                dblp_url = f"https://dblp.org/pid/{pid_hint}"
            else:
                dblp_url = pid_map.get(name) or pid_map.get(display) or ""
            parts.append(
                f'<a class="author-add" href="javascript:void(0)"'
                f' data-name="{esc(display)}" data-slug="{new_slug}"'
                f' data-dblp-url="{esc(dblp_url)}"'
                f' onclick="openAddModal(this)"'
                f' title="{esc(display)} hozzáadása az adatbázishoz">➕ {esc(display)}</a>'
            )
    return ", ".join(parts)


INST_ORDER = ["BME", "ELTE", "SZTE", "SZTAKI", "Rényi", "Ericsson", "Corvinus", "PPKE", "ÓE", "Hungary"]
NAT_ORDER  = ["all_hungarian", "mostly_hungarian", "international"]


def classify(tags: list) -> dict:
    institutions = [i for i in INST_ORDER if i in tags]
    nationality  = next((n for n in NAT_ORDER if n in tags), "")
    return {"institutions": institutions, "nationality": nationality}


def paper_topic(authors: list, author_lookup: dict, slug_category: dict) -> str:
    """Majority vote of known authors' categories → 'theory' | 'applied' | ''."""
    theory = applied = 0
    for name in authors:
        if isinstance(name, list):
            name = name[0] if name else ""
        slug = (
            author_lookup.get(normalize(name))
            or author_lookup.get(normalize(clean_name(name)))
        )
        if slug:
            cat = slug_category.get(slug, "")
            if cat == "theory":
                theory += 1
            elif cat == "applied":
                applied += 1
    if theory == 0 and applied == 0:
        return ""
    return "theory" if theory >= applied else "applied"


def load_papers(json_files: list[Path], label: str, author_lookup: dict, slug_category: dict, pid_map: dict | None = None) -> list[dict]:
    """Load and merge papers from one or more JSON files."""
    merged = {}
    for f in json_files:
        if f.exists():
            merged.update(json.loads(f.read_text(encoding="utf-8")))
    papers = []
    for key, e in merged.items():
        authors = e.get("authors", [])
        kw      = classify(e.get("classfiied", []))
        topic   = paper_topic(authors, author_lookup, slug_category)
        doi = e.get("doi", "").strip()
        ee  = e.get("ee",  "").strip()
        link = doi if doi else ee
        papers.append({
            "key":          key,
            "title":        e.get("title", "").rstrip("."),
            "authors":      authors,
            "venue":        e.get("venue", ""),
            "year":         int(e.get("year", 0) or 0),
            "doi":          link,
            "institutions": kw["institutions"],
            "nationality":  kw["nationality"],
            "topic":        topic,
            "tier":         label,
        })
    papers.sort(key=lambda p: -p["year"])
    return papers


def generate_html(papers_astar: list[dict], papers_a: list[dict], papers_b: list[dict], papers_c: list[dict], papers_norank: list[dict], author_lookup: dict, existing_profiles: set | None = None, pid_map: dict | None = None, pid_to_slug: dict | None = None) -> str:
    def paper_obj(p):
        return {
            "key":          p["key"],
            "title":        p["title"],
            "authors_html": format_authors(p["authors"], author_lookup, pid_map, pid_to_slug),
            "venue":        p["venue"],
            "year":         p["year"],
            "doi":          p["doi"],
            "institutions": p["institutions"],
            "nationality":  p["nationality"],
            "topic":        p["topic"],
            "tier":         p["tier"],
        }

    all_papers = papers_astar + papers_a + papers_b + papers_c + papers_norank
    papers_json = json.dumps([paper_obj(p) for p in all_papers], ensure_ascii=False)

    tier_counts_json = json.dumps({
        "A*": len(papers_astar),
        "A":  len(papers_a),
        "B":  len(papers_b),
        "C":  len(papers_c),
        "NR": len(papers_norank),
    })
    years_all = sorted({p["year"] for p in all_papers if p["year"]})
    min_year  = min(years_all) if years_all else 1975
    max_year  = max(years_all) if years_all else 2026
    existing_profiles_json = json.dumps(sorted(existing_profiles or []))

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
#author-banner {{ display:none; padding: 0.35rem 1.5rem; font-size: 0.82rem; background: var(--accent-bg);
  border-bottom: 1px solid var(--border); color: var(--accent); display: flex; align-items: center; gap: 0.5rem; }}
#author-banner button {{ background: none; border: none; cursor: pointer; color: var(--accent);
  font-size: 1rem; line-height: 1; padding: 0 0.2rem; }}
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
.author-add {{ color: var(--muted); text-decoration: none; border-bottom: 1px dashed var(--muted); }}
.author-add:hover {{ color: var(--accent); border-bottom-color: var(--accent); }}
.paper-tags {{ display: flex; flex-wrap: wrap; gap: 0.2rem; }}
.tag {{ display: inline-block; padding: 0.08rem 0.4rem; border-radius: 4px; font-size: 0.7rem; font-weight: 500; }}
.tag-inst {{ background: var(--chip-bg); color: var(--text); }}
.tag-tier-astar {{ background: #fef2f2; color: #991b1b; }}
.tag-tier-a {{ background: #fff7ed; color: #9a3412; }}
.tag-tier-b {{ background: #eff6ff; color: #1e40af; }}
.tag-tier-c {{ background: #f0fdf4; color: #166534; }}
.tag-tier-nr {{ background: #f5f5f5; color: #6b7280; }}
.tag-theory {{ background: var(--tag-theory); color: var(--tag-theory-text); }}
.tag-applied {{ background: var(--tag-applied); color: var(--tag-applied-text); }}
.tag-intl {{ background: var(--tag-intl); color: var(--tag-intl-text); }}
.tag-allhu {{ background: var(--tag-allhu); color: var(--tag-allhu-text); }}
.tag-mosthu {{ background: var(--tag-mosthu); color: var(--tag-mosthu-text); }}
#empty {{ display: none; text-align: center; padding: 3rem; color: var(--muted); }}
footer {{ text-align: center; padding: 1rem; font-size: 0.75rem; color: var(--muted); border-top: 1px solid var(--border); }}
.section-header {{ display: flex; align-items: center; gap: 0.75rem; margin: 1rem 0 0.4rem;
  font-size: 0.8rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
.section-header::before, .section-header::after {{ content: ''; flex: 1; border-top: 1px solid var(--border); }}
.section-header:first-child {{ margin-top: 0; }}

/* Add-author modal */
#add-modal-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:1000; align-items:center; justify-content:center; }}
#add-modal-overlay.open {{ display:flex; }}
#add-modal {{ background:var(--card); border:1px solid var(--border); border-radius:12px; width:min(600px,95vw);
  max-height:90vh; overflow-y:auto; padding:1.5rem; box-shadow:0 20px 60px rgba(0,0,0,.3); position:relative; }}
#add-modal h2 {{ font-size:1.1rem; font-weight:700; margin-bottom:1rem; }}
.modal-section {{ margin-bottom:1rem; }}
.modal-section h3 {{ font-size:0.78rem; font-weight:700; color:var(--muted); text-transform:uppercase;
  letter-spacing:.05em; margin-bottom:.4rem; }}
.candidate-list {{ display:flex; flex-direction:column; gap:.3rem; max-height:160px; overflow-y:auto; }}
.candidate {{ display:flex; align-items:center; gap:.5rem; padding:.35rem .6rem; border-radius:6px;
  border:1px solid var(--border); cursor:pointer; font-size:.82rem; background:var(--bg); transition:background .1s; }}
.candidate:hover, .candidate.selected {{ background:var(--accent-bg); border-color:var(--accent); color:var(--accent); }}
.candidate-none {{ font-size:.82rem; color:var(--muted); padding:.3rem 0; }}
.modal-field {{ display:flex; flex-direction:column; gap:.25rem; margin-bottom:.6rem; }}
.modal-field label {{ font-size:.8rem; font-weight:600; color:var(--muted); }}
.modal-field input, .modal-field select {{ padding:.35rem .6rem; border:1px solid var(--border); border-radius:6px;
  background:var(--bg); color:var(--text); font-size:.85rem; width:100%; }}
.modal-field input:focus, .modal-field select:focus {{ outline:2px solid var(--accent); border-color:transparent; }}
.modal-hint {{ font-size:.75rem; color:var(--muted); margin-top:.15rem; }}
.modal-hint a {{ color:var(--accent); }}
.modal-actions {{ display:flex; gap:.5rem; justify-content:flex-end; margin-top:1rem; padding-top:1rem;
  border-top:1px solid var(--border); }}
.btn-primary {{ background:var(--accent); color:#fff; border:none; border-radius:6px;
  padding:.45rem 1.1rem; font-size:.85rem; font-weight:600; cursor:pointer; }}
.btn-primary:hover {{ opacity:.9; }}
.btn-secondary {{ background:var(--chip-bg); color:var(--text); border:1px solid var(--border);
  border-radius:6px; padding:.45rem 1.1rem; font-size:.85rem; cursor:pointer; }}
.loading-dots::after {{ content:'.'; animation:dots 1.2s steps(3,end) infinite; }}
@keyframes dots {{ 0%,20%{{content:'.';}} 40%{{content:'..';}} 60%,100%{{content:'...';}} }}
#add-modal-close {{ position:absolute; top:.75rem; right:.75rem; background:none; border:none;
  font-size:1.2rem; cursor:pointer; color:var(--muted); line-height:1; }}
</style>
</head>
<body>
<header>
  <div class="header-row">
    <h1>CORE Rangsorolt Cikkek — Magyar CS Kutatók</h1>
    <div class="tier-toggle">
      <span class="toggle-btn active" id="btn-astar" onclick="setTier('astar')">★ A*</span>
      <span class="toggle-btn" id="btn-a" onclick="setTier('a')">A</span>
      <span class="toggle-btn" id="btn-b" onclick="setTier('b')">B</span>
      <span class="toggle-btn" id="btn-c" onclick="setTier('c')">C</span>
      <span class="toggle-btn" id="btn-nr" onclick="setTier('nr')">Egyéb</span>
      <span class="toggle-btn" id="btn-both" onclick="setTier('both')">Mind</span>
    </div>
  </div>
  <div class="controls">
    <input id="search" type="search" placeholder="Cím, szerző, konferencia…">
    <div id="year-filter">
      Év: <input id="year-from" type="number" value="{min_year}" min="{min_year}" max="2100" placeholder="tól">
      – <input id="year-to" type="number" min="{min_year}" max="2100" placeholder="ig">
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
<div class="filter-row">
  <span class="filter-label">Rendezés</span>
  <span class="chip active" data-group="sort" data-val="year-desc">Év ↓</span>
  <span class="chip" data-group="sort" data-val="year-asc">Év ↑</span>
  <span class="chip" data-group="sort" data-val="venue">Konferencia</span>
</div>
<div id="author-banner" style="display:none">
  <span id="author-banner-text"></span>
  <button onclick="clearAuthorFilter()" title="Szűrő törlése">✕</button>
</div>
<div id="status"></div>
<div id="list"></div>
<div id="empty">Nincs a szűrőknek megfelelő cikk.</div>
<footer>Adatok: <a href="https://dblp.org" style="color:var(--accent)">DBLP</a> ·
  <a href="https://github.com/jtapolcai/corePaperList" style="color:var(--accent)">corePaperList</a></footer>

<!-- Add-author modal -->
<div id="add-modal-overlay">
  <div id="add-modal">
    <button id="add-modal-close" onclick="closeAddModal()" title="Bezárás">✕</button>
    <h2 id="modal-title">Szerző hozzáadása</h2>

    <div class="modal-section">
      <h3>DBLP profil</h3>
      <div id="dblp-status" class="candidate-none loading-dots">Keresés</div>
      <div id="dblp-list" class="candidate-list" style="display:none"></div>
    </div>

    <div class="modal-section">
      <h3>MTMT profil</h3>
      <div id="mtmt-status" class="candidate-none loading-dots">Keresés</div>
      <div id="mtmt-list" class="candidate-list" style="display:none"></div>
    </div>

    <div class="modal-field" id="m-name-row" style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:.5rem .7rem;">
      <label style="font-size:.75rem;color:var(--muted);margin-bottom:.2rem;">Végleges név (DBLP alapján automatikusan töltődik)</label>
      <div id="m-name-display" style="font-weight:700;font-size:1rem;color:var(--text)">—</div>
      <div id="m-slug-display" style="font-size:.72rem;color:var(--muted);margin-top:.1rem;font-family:monospace"></div>
    </div>
    <div class="modal-field">
      <label>DBLP URL</label>
      <input type="text" id="m-dblp-url" placeholder="https://dblp.org/pid/…">
    </div>
    <div class="modal-field">
      <label>MTMT ID</label>
      <input type="text" id="m-mtmt-id" placeholder="pl. 10012955">
    </div>
    <div class="modal-field">
      <label>MTMT Név (MTMT-ben használt)</label>
      <input type="text" id="m-mtmt-name" placeholder="Szerző MTMT neve">
    </div>
    <div class="modal-field">
      <label>MTA köztestületi tag URL</label>
      <input type="text" id="m-mta-att-id" placeholder="https://mta.hu/koztestuleti_tagok?PersonId=…">
      <div class="modal-hint">
        <a href="https://mta.hu/koztestuleti_tagok" target="_blank" rel="noopener">🔍 Keresés az MTA oldalán →</a>
      </div>
    </div>
    <div class="modal-field">
      <label>Kategória</label>
      <select id="m-category">
        <option value="">—</option>
        <option value="theory">Elmélet</option>
        <option value="applied">Alkalmazott</option>
      </select>
    </div>
    <div class="modal-field">
      <label>Munkahely</label>
      <select id="m-works">
        <option value="">—</option>
        <option value="hungary">Hungary</option>
        <option value="abroad">Abroad</option>
        <option value="company_hungary">Company (HU)</option>
        <option value="company_abroad">Company (külföld)</option>
        <option value="inactive">Inaktív</option>
        <option value="retired">Nyugdíjas</option>
      </select>
    </div>
    <div class="modal-field">
      <label>Affiliációk</label>
      <input type="text" id="m-affiliations" placeholder="pl. BME-TMIT">
    </div>
    <div class="modal-field">
      <label>Honlap</label>
      <input type="text" id="m-homepage" placeholder="https://…">
    </div>
    <div class="modal-field">
      <label>LinkedIn URL</label>
      <input type="text" id="m-linkedin" placeholder="https://linkedin.com/in/…">
      <div class="modal-hint" id="m-linkedin-hint"></div>
    </div>
    <div class="modal-field">
      <label>Megjegyzés</label>
      <input type="text" id="m-note" placeholder="">
    </div>

    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeAddModal()">Mégsem</button>
      <button class="btn-primary" onclick="saveAddModal()">💾 Mentés GitHubra →</button>
    </div>
  </div>
</div>

<script>
const GITHUB_REPO = "{GITHUB_REPO}";
const GITHUB_BRANCH = "{GITHUB_BRANCH}";
const EXISTING_PROFILES = new Set({existing_profiles_json});

let _modalSlug = "";
let _modalName = "";

function _updateNameDisplay() {{
  const nameEl = document.getElementById("m-name-display");
  const slugEl = document.getElementById("m-slug-display");
  if (nameEl) nameEl.textContent = _modalName || "—";
  if (slugEl) slugEl.textContent = _modalSlug ? "slug: " + _modalSlug : "";
  document.getElementById("modal-title").textContent = "Hozzáadás: " + (_modalName || "…");
}}

function openAddModal(el) {{
  _modalName = el.dataset.name || el.textContent.replace("➕","").trim();
  _modalSlug = el.dataset.slug || slugifyJS(_modalName);
  const knownDblpUrl = el.dataset.dblpUrl || "";
  _updateNameDisplay();
  // Reset
  ["m-dblp-url","m-mtmt-id","m-mtmt-name","m-mta-att-id","m-affiliations","m-homepage","m-linkedin","m-note"].forEach(id => {{
    document.getElementById(id).value = "";
  }});
  document.getElementById("m-category").value = "";
  document.getElementById("m-works").value = "";
  document.getElementById("dblp-list").innerHTML = "";
  document.getElementById("mtmt-list").innerHTML = "";
  document.getElementById("mtmt-list").style.display = "none";
  document.getElementById("mtmt-status").textContent = "Keresés";
  document.getElementById("mtmt-status").style.display = "";
  // LinkedIn hint
  const hint = document.getElementById("m-linkedin-hint");
  hint.innerHTML = '<a href="https://www.linkedin.com/search/results/people/?keywords=' + encodeURIComponent(_modalName) + '" target="_blank" rel="noopener">🔍 Keresés LinkedIn-en →</a>';
  document.getElementById("add-modal-overlay").classList.add("open");
  // DBLP: use known URL from paper data, no search needed
  const dblpStatus = document.getElementById("dblp-status");
  const dblpList = document.getElementById("dblp-list");
  if (knownDblpUrl) {{
    document.getElementById("m-dblp-url").value = knownDblpUrl;
    dblpStatus.style.display = "none";
    dblpList.innerHTML = '<div class="candidate selected"><span>🔗</span><span><strong>' + _modalName + '</strong> — DBLP azonosító ismert</span><a href="' + knownDblpUrl + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="margin-left:auto;font-size:.75rem;color:var(--accent)">DBLP →</a></div>';
    dblpList.style.display = "flex";
    enrichFromDblp(knownDblpUrl);
  }} else {{
    dblpList.style.display = "none";
    dblpStatus.textContent = "Keresés";
    dblpStatus.style.display = "";
    searchDblp(_modalName);
  }}
  // MTMT: always search
  searchMtmt(_modalName);
}}

function closeAddModal() {{
  document.getElementById("add-modal-overlay").classList.remove("open");
}}

function slugifyJS(name) {{
  return name.toLowerCase()
    .normalize("NFD").replace(/[\\u0300-\\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}}

async function searchDblp(name) {{
  const statusEl = document.getElementById("dblp-status");
  const listEl = document.getElementById("dblp-list");
  try {{
    const url = "https://dblp.org/search/author/api?q=" + encodeURIComponent(name) + "&format=json&h=8";
    const resp = await fetch(url);
    const data = await resp.json();
    const hits = data?.result?.hits?.hit || [];
    statusEl.style.display = "none";
    if (!hits.length) {{
      statusEl.textContent = "Nem található DBLP-n";
      statusEl.style.display = "";
      return;
    }}
    listEl.innerHTML = hits.map(h => {{
      const info = h.info || {{}};
      const authorName = info.author || "";
      const pid = info.url || "";
      const dblpUrl = pid ? "https://dblp.org/pid/" + pid.replace(/^.*pid\\//,"") : "";
      return `<div class="candidate" onclick="selectDblp(${{JSON.stringify(dblpUrl)}}, ${{JSON.stringify(authorName)}}, this)">
        <span>🔗</span>
        <span><strong>${{authorName}}</strong></span>
        ${{dblpUrl ? '<a href="' + dblpUrl + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="margin-left:auto;font-size:.75rem;color:var(--accent)">DBLP →</a>' : ''}}
      </div>`;
    }}).join("");
    listEl.style.display = "flex";
  }} catch(e) {{
    statusEl.textContent = "DBLP keresés sikertelen";
    statusEl.style.display = "";
  }}
}}

function selectDblp(url, name, el) {{
  document.getElementById("m-dblp-url").value = url;
  document.querySelectorAll("#dblp-list .candidate").forEach(c => c.classList.remove("selected"));
  el.classList.add("selected");
  if (name) {{
    _modalName = name;
    _modalSlug = slugifyJS(name);
    _updateNameDisplay();
  }}
}}

async function searchMtmt(name) {{
  const statusEl = document.getElementById("mtmt-status");
  const listEl = document.getElementById("mtmt-list");
  // Try (lastWord=family + firstWord=given) then (firstWord=family + lastWord=given) then family-only fallback
  const parts = name.trim().split(/\\s+/);
  const seen = new Map();
  const queries = parts.length >= 2 ? [
    [parts[parts.length-1], parts[0]],   // Western order: last=family, first=given
    [parts[0], parts[parts.length-1]],   // Hungarian order: first=family, last=given
  ] : [[parts[0], ""]];
  for (const [fam, given] of queries) {{
    try {{
      let url = "https://m2.mtmt.hu/api/author?cond=familyName;eq;" + encodeURIComponent(fam);
      if (given) url += "&cond=givenName;eq;" + encodeURIComponent(given);
      url += "&format=json&size=20";
      const resp = await fetch(url);
      const data = await resp.json();
      for (const c of (data.content || [])) {{
        if (c.mtid && !seen.has(c.mtid)) seen.set(c.mtid, c.label || "");
      }}
    }} catch(e) {{}}
  }}
  statusEl.style.display = "none";
  if (!seen.size) {{
    statusEl.textContent = "Nem található MTMT-n";
    statusEl.style.display = "";
    return;
  }}
  listEl.innerHTML = [...seen.entries()].map(([mtid, label]) => {{
    const safeLabel = label.replace(/&/g,"&amp;").replace(/"/g,"&quot;");
    return `<div class="candidate" data-mtid="${{mtid}}" data-label="${{safeLabel}}" onclick="selectMtmt(this)">
      <span>📖</span>
      <span><strong>${{label}}</strong> <span style="color:var(--muted);font-size:.75rem">(ID: ${{mtid}})</span></span>
      <a href="https://m2.mtmt.hu/api/author/${{mtid}}" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="margin-left:auto;font-size:.75rem;color:var(--accent)">MTMT →</a>
    </div>`;
  }}).join("");
  listEl.style.display = "flex";
}}

function selectMtmt(el) {{
  const mtid  = +el.dataset.mtid;
  const label = el.dataset.label;
  document.getElementById("m-mtmt-id").value = mtid;
  document.getElementById("m-mtmt-name").value = label;
  document.querySelectorAll("#mtmt-list .candidate").forEach(c => c.classList.remove("selected"));
  el.classList.add("selected");
  enrichFromMtmt(mtid, label);
}}

const HU_INST = {{
  "BME": "BME", "Budapest University of Technology": "BME",
  "ELTE": "ELTE", "Eötvös": "ELTE", "Loránd": "ELTE",
  "SZTE": "SZTE", "Szegedi": "SZTE",
  "Rényi": "Rényi", "RAMKI": "Rényi",
  "SZTAKI": "SZTAKI", "HUN-REN": "SZTAKI",
  "Ericsson": "Ericsson",
  "Corvinus": "Corvinus",
  "PPKE": "PPKE", "Pázmány": "PPKE",
  "Miskolci": "ME", "Miskolc": "ME",
  "Óbudai": "ÓE", "ÓE": "ÓE",
  "GAMF": "KE", "Kecskeméti": "KE",
  "Debrecen": "DE",
  "Pécsi": "PTE", "PTE": "PTE",
}};

const THEORY_KEYWORDS = ["Matematika", "Számítástudomány", "Kombinatorika", "Elmélet", "Algebra", "Analízis", "Valószínűség", "Statisztika", "Mathematics", "Combinatorics", "Theory", "Algebra", "Logic"];
const APPLIED_KEYWORDS = ["Villamosmérnöki", "Informatika", "Hálózat", "Távközlés", "Irányítástechnika", "Electrical", "Network", "Telecommunication", "Computer Engineering"];

function instAbbr(label) {{
  for (const [kw, abbr] of Object.entries(HU_INST)) {{
    if (label.includes(kw)) return abbr;
  }}
  return null;
}}

function parseAffiliationLabel(label) {{
  // e.g. "Schwarcz Tamás Bence - Operációkutatási Tanszék ELTE / TTK / Mat_I [2006-]"
  const dash = label.indexOf(" - ");
  if (dash < 0) return null;
  const rest = label.slice(dash + 3);
  const match = rest.match(/\\[(\\d{{4}})-(\\d{{4}})?/);
  const start = match ? match[1] : "";
  const end   = match ? (match[2] || "") : "";
  const abbr  = instAbbr(rest);
  if (!abbr || !start) return null;
  return abbr + " " + start + (end ? "-" + end : "-");
}}

async function enrichFromMtmt(mtid, label) {{
  try {{
    const resp = await fetch("https://m2.mtmt.hu/api/author/" + mtid + "?format=json");
    const data = await resp.json();
    const c = Array.isArray(data.content) ? data.content[0] : data.content;
    if (!c) return;

    // Affiliations → m-affiliations (if not already filled)
    const affs = (c.affiliations || [])
      .map(a => parseAffiliationLabel(a.label || ""))
      .filter(Boolean);
    // Deduplicate keeping first occurrence
    const seen = new Set();
    const unique = affs.filter(a => {{
      const k = a.replace(/\\d{{4}}.*/, "").trim();
      return seen.has(k) ? false : seen.add(k);
    }});
    if (unique.length && !document.getElementById("m-affiliations").value.trim()) {{
      document.getElementById("m-affiliations").value = unique.join("; ");
    }}

    // works: if any affiliation is from a known HU institution → "hungary"
    if (!document.getElementById("m-works").value) {{
      const isHu = affs.some(a => Object.values(HU_INST).some(abbr => a.startsWith(abbr)));
      if (isHu) document.getElementById("m-works").value = "hungary";
    }}

    // category from MTMT label discipline hint, e.g. "(Matematika)"
    if (!document.getElementById("m-category").value) {{
      const disc = (label.match(/\\(([^)]+)\\)/) || [])[1] || "";
      if (THEORY_KEYWORDS.some(k => disc.includes(k))) {{
        document.getElementById("m-category").value = "theory";
      }} else if (APPLIED_KEYWORDS.some(k => disc.includes(k))) {{
        document.getElementById("m-category").value = "applied";
      }}
    }}
  }} catch(e) {{ /* silent */ }}
}}

async function enrichFromDblp(dblpUrl) {{
  // Extract pid from URL: https://dblp.org/pid/238/1161 → 238/1161
  const m = dblpUrl.match(/dblp\\.org\\/pid\\/(.+)/);
  if (!m) return;
  const pid = m[1].replace(/\\/$/, "");
  try {{
    const url = "https://dblp.org/search/author/api?q=pid:" + encodeURIComponent(pid) + "&format=json&h=1";
    const resp = await fetch(url);
    const data = await resp.json();
    const hit = (data?.result?.hits?.hit || [])[0];
    if (!hit) return;
    const dblpName = hit.info?.author || "";
    if (dblpName) {{
      _modalName = dblpName;
      _modalSlug = slugifyJS(dblpName);
      _updateNameDisplay();
    }}
    const notes = hit.info?.notes?.note;
    const noteArr = Array.isArray(notes) ? notes : (notes ? [notes] : []);
    const aff = noteArr.filter(n => n["@type"] === "affiliation").map(n => n["#text"]).join("; ");
    if (aff && !document.getElementById("m-affiliations").value.trim()) {{
      document.getElementById("m-affiliations").value = aff;
    }}
  }} catch(e) {{ /* silent */ }}
}}

function saveAddModal() {{
  const obj = {{}};
  obj.name = _modalName;
  obj.slug = _modalSlug;
  const fields = {{
    dblp_url: "m-dblp-url", mtmt_id: "m-mtmt-id", mtmt_name: "m-mtmt-name",
    mta_att_id: "m-mta-att-id", category: "m-category", works: "m-works",
    affiliations: "m-affiliations", homepage: "m-homepage", linkedin: "m-linkedin", note: "m-note"
  }};
  for (const [key, id] of Object.entries(fields)) {{
    const v = document.getElementById(id).value.trim();
    if (v) obj[key] = v;
  }}
  const json = JSON.stringify(obj, null, 2);
  const encoded = encodeURIComponent(json);
  let url;
  if (EXISTING_PROFILES.has(_modalSlug)) {{
    url = "https://github.com/" + GITHUB_REPO + "/edit/" + GITHUB_BRANCH
      + "/profiles/" + _modalSlug + ".json";
  }} else {{
    url = "https://github.com/" + GITHUB_REPO + "/new/" + GITHUB_BRANCH
      + "?filename=profiles/" + _modalSlug + ".json&value=" + encoded;
  }}
  window.open(url, "_blank");
  closeAddModal();
}}

// Close on overlay click
document.getElementById("add-modal-overlay").addEventListener("click", function(e) {{
  if (e.target === this) closeAddModal();
}});
</script>
<script>
const ALL_PAPERS = {papers_json};
const TIER_COUNTS = {tier_counts_json};

const TIER_SETS = {{
  "astar": new Set(["A*"]),
  "a":     new Set(["A"]),
  "b":     new Set(["B"]),
  "c":     new Set(["C"]),
  "nr":    new Set(["NR"]),
  "both":  new Set(["A*","A","B","C","NR"]),
}};

const TIER_TAG_CLASS = {{ "A*": "astar", "A": "a", "B": "b", "C": "c", "NR": "nr" }};
const TIER_LABEL     = {{ "A*": "★ A*",   "A": "A", "B": "B", "C": "C", "NR": "Egyéb" }};
const TIER_EQ_WEIGHT = {{ "A*": 1, "A": 1/3, "B": 1/6, "C": 1/9, "NR": 1/15 }};
const TIER_RANK      = {{ "A*": 0, "A": 1, "B": 2, "C": 3, "NR": 4 }};

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
let searchQ = "", yearFrom = {min_year}, yearTo = 0;
let tierMode = "astar";
let authorSlugFilter = "";
let sortMode = "year-desc";

function setTier(mode) {{
  tierMode = mode;
  ["astar","a","b","c","nr","both"].forEach(t =>
    document.getElementById("btn-" + t).classList.toggle("active", mode === t)
  );
  render();
}}

function papers() {{
  const tiers = TIER_SETS[tierMode] || TIER_SETS["astar"];
  return ALL_PAPERS.filter(p => tiers.has(p.tier));
}}

function renderPaper(p) {{
  const titleEl = p.doi
    ? `<a href="${{p.doi}}" target="_blank" rel="noopener">${{p.title}}</a>`
    : `<span>${{p.title}}</span>`;
  const showTierTag = tierMode === "both" || !["astar","a","b","c","nr"].includes(tierMode) || TIER_SETS[tierMode].size > 1;
  const tierTag = showTierTag
    ? `<span class="tag tag-tier-${{TIER_TAG_CLASS[p.tier] || ''}}">${{TIER_LABEL[p.tier] || p.tier}}</span>`
    : "";
  const eqWeight = TIER_EQ_WEIGHT[p.tier];
  const eqTag = authorSlugFilter && eqWeight !== undefined
    ? `<span class="tag tag-tier-${{TIER_TAG_CLASS[p.tier] || ''}}" title="A* ekvivalens súly">A* eq: ${{eqWeight % 1 === 0 ? eqWeight : eqWeight.toFixed(4).replace(/\\.?0+$/, "")}}</span>`
    : "";
  const tags = [
    tierTag,
    eqTag,
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
  if (authorSlugFilter && !p.authors_html.includes(`#${{authorSlugFilter}}`)) return false;
  if (filterInst  && !p.institutions.includes(filterInst)) return false;
  if (filterNat   && p.nationality !== filterNat) return false;
  if (filterTopic && p.topic !== filterTopic) return false;
  if (p.year < yearFrom) return false;
  if (yearTo && p.year > yearTo) return false;
  if (searchQ) {{
    const q = searchQ.toLowerCase();
    const hay = (p.title + " " + p.authors_html.replace(/<[^>]+>/g,"") + " " + p.venue).toLowerCase();
    if (!hay.includes(q)) return false;
  }}
  return true;
}}

function render() {{
  const src = papers();
  let visible = src.filter(matches);

  // Sort
  if (sortMode === "year-asc") {{
    visible.sort((a,b) => a.year - b.year || a.venue.localeCompare(b.venue));
  }} else if (sortMode === "venue") {{
    visible.sort((a,b) => a.venue.localeCompare(b.venue) || b.year - a.year);
  }} else if (sortMode === "tier") {{
    visible.sort((a,b) => (TIER_RANK[a.tier]??99) - (TIER_RANK[b.tier]??99) || b.year - a.year || a.venue.localeCompare(b.venue));
  }} else {{
    visible.sort((a,b) => b.year - a.year || a.venue.localeCompare(b.venue));
  }}

  // Build HTML with section dividers
  let html = "";
  let lastGroup = null;
  for (const p of visible) {{
    const group = sortMode === "venue" ? p.venue : sortMode === "tier" ? (TIER_LABEL[p.tier] || p.tier) : String(p.year);
    if (group !== lastGroup) {{
      html += `<div class="section-header"><span>${{group}}</span></div>`;
      lastGroup = group;
    }}
    html += renderPaper(p);
  }}

  document.getElementById("list").innerHTML = html;
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
    if (g === "sort")  sortMode    = chip.dataset.val;
    render();
  }});
}});
document.getElementById("search").addEventListener("input", e => {{ searchQ = e.target.value.trim(); render(); }});
document.getElementById("year-from").addEventListener("input", e => {{ yearFrom = +e.target.value || {min_year}; render(); }});
document.getElementById("year-to").addEventListener("input", e => {{ yearTo = +e.target.value || 0; render(); }});

function clearAuthorFilter() {{
  authorSlugFilter = "";
  document.getElementById("author-banner").style.display = "none";
  history.replaceState(null, "", window.location.pathname);
  render();
}}

(function() {{
  const p = new URLSearchParams(window.location.search);
  const paramTier   = p.get("tier");
  const paramAuthor = p.get("author");
  const paramName   = p.get("name");
  if (paramTier && ["astar","a","b","c","nr","both"].includes(paramTier)) setTier(paramTier);
  const paramSort = p.get("sort");
  if (paramSort && ["year-desc","year-asc","venue","tier"].includes(paramSort)) sortMode = paramSort;
  if (paramAuthor) {{
    authorSlugFilter = paramAuthor;
    const banner = document.getElementById("author-banner");
    banner.style.display = "flex";
    document.getElementById("author-banner-text").textContent =
      "Szűrve: " + (paramName || paramAuthor);
  }}
  render();
}})();
</script>
</body>
</html>
"""


def load_existing_profiles(profiles_dir: Path) -> set:
    """Return slugs that have a real profile .json file (not underscore-prefixed)."""
    if not profiles_dir.exists():
        return set()
    return {f.stem for f in profiles_dir.glob("*.json") if not f.stem.startswith("_")}


def main():
    author_lookup, slug_category, pid_map, pid_to_slug = load_author_data()
    print(f"Loaded {len(author_lookup)} author name entries, {len(pid_to_slug)} DBLP PIDs for linking")

    papers_astar = load_papers([JSON_HUN_ASTAR, JSON_ABR_ASTAR], "A*", author_lookup, slug_category, pid_map)
    print(f"Core A*: {len(papers_astar)} papers")

    papers_a = load_papers([JSON_HUN_A, JSON_ABR_A], "A", author_lookup, slug_category, pid_map)
    print(f"Core A:  {len(papers_a)} papers")

    papers_b = load_papers([JSON_HUN_B, JSON_ABR_B], "B", author_lookup, slug_category, pid_map)
    print(f"Core B:  {len(papers_b)} papers")

    papers_c = load_papers([JSON_HUN_C, JSON_ABR_C], "C", author_lookup, slug_category, pid_map)
    print(f"Core C:  {len(papers_c)} papers")

    papers_norank = load_papers([JSON_HUN_NR, JSON_ABR_NR], "NR", author_lookup, slug_category, pid_map)
    print(f"No rank: {len(papers_norank)} papers")

    existing = load_existing_profiles(BASE / "profiles")
    html_out = generate_html(papers_astar, papers_a, papers_b, papers_c, papers_norank, author_lookup, existing, pid_map, pid_to_slug)
    OUT_FILE.write_text(html_out, encoding="utf-8")
    print(f"Generated {OUT_FILE}")


if __name__ == "__main__":
    main()
