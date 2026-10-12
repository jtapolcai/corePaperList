#!/usr/bin/env python3
"""
Generate authors_profile.html — a single-page app with per-author profiles.
URL routing: authors_profile.html#daniel-marx
Data is embedded inline so it works with file:// and GitHub Pages.

Usage:
  python3 gen_authors_html.py                         # uses authors.json + profiles/
  python3 gen_authors_html.py authors.json profiles/  # explicit paths
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
AUTHORS_JSON = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "authors.json"
PROFILES_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "profiles"
OUT_FILE = BASE / "authors_profile.html"


def load_profiles(profiles_dir: Path) -> dict:
    profiles = {}
    if not profiles_dir.exists():
        return profiles
    for f in profiles_dir.glob("*.json"):
        if f.stem.startswith("_"):
            continue
        try:
            profiles[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: could not parse {f}: {e}")
    return profiles


GITHUB_REPO = "jtapolcai/corePaperList"
GITHUB_BRANCH = "main"

# Fields the user manually edits in profiles/{slug}.json
EDITABLE_FIELDS = [
    "dblp_url", "mtmt_id", "mta_att_id", "mtmt_name",
    "category", "mtmt_status", "works", "affiliations",
    "homepage", "note",
]


def profile_template(author: dict) -> str:
    """Build a JSON template pre-filled with the author's current values."""
    obj = {k: author.get(k) or "" for k in EDITABLE_FIELDS}
    return json.dumps(obj, ensure_ascii=False, indent=2)


def github_edit_url(slug: str, author: dict, has_profile: bool) -> str:
    from urllib.parse import quote
    if has_profile:
        return f"https://github.com/{GITHUB_REPO}/edit/{GITHUB_BRANCH}/profiles/{slug}.json"
    encoded = quote(profile_template(author), safe="")
    return (
        f"https://github.com/{GITHUB_REPO}/new/{GITHUB_BRANCH}"
        f"?filename=profiles/{slug}.json&value={encoded}"
    )


NEW_AUTHOR_TEMPLATE = json.dumps({
    "name": "",
    "slug": "",
    "dblp_url": "",
    "mtmt_id": "",
    "mta_att_id": "",
    "mtmt_name": "",
    "category": "theory",
    "mtmt_status": "",
    "works": "",
    "affiliations": "",
    "homepage": "",
    "note": "",
}, ensure_ascii=False, indent=2)


def new_author_url() -> str:
    from urllib.parse import quote
    encoded = quote(NEW_AUTHOR_TEMPLATE, safe="")
    return (
        f"https://github.com/{GITHUB_REPO}/new/{GITHUB_BRANCH}"
        f"?filename=profiles/_new_author.json&value={encoded}"
    )


def merge(authors: list, profiles: dict) -> list:
    """Apply profile overrides directly onto author fields (no profile_ prefix)."""
    for a in authors:
        slug = a.get("slug", "")
        has_profile = slug in profiles
        a["_has_profile"] = has_profile
        a["_github_edit_url"] = github_edit_url(slug, a, has_profile)
        if has_profile:
            p = profiles[slug]
            for k in EDITABLE_FIELDS:
                if k in p and p[k] not in (None, ""):
                    a[k] = p[k]  # direct override, not prefixed
            # Legacy support: profile_homepage / profile_note from old format
            for k in ("homepage", "note"):
                legacy = p.get(f"profile_{k}") or p.get(k)
                if legacy:
                    a[k] = legacy
    return authors


def generate(authors: list) -> str:
    data_json = json.dumps(authors, ensure_ascii=False)

    new_author_github_url = new_author_url()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Author Profiles — Hungarian CS Research</title>
<style>
:root {{
  --bg: #f9fafb; --card: #fff; --border: #e5e7eb; --text: #111827;
  --muted: #6b7280; --accent: #1d4ed8; --accent-bg: #eff6ff;
  --chip-bg: #f3f4f6; --chip-active: #1d4ed8; --chip-active-text: #fff;
  --sidebar-w: 280px;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #111827; --card: #1f2937; --border: #374151; --text: #f9fafb;
    --muted: #9ca3af; --accent: #60a5fa; --accent-bg: #1e3a5f;
    --chip-bg: #374151; --chip-active: #3b82f6; --chip-active-text: #fff;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui,-apple-system,sans-serif; background: var(--bg); color: var(--text); }}

/* Layout */
#app {{ display: flex; height: 100vh; overflow: hidden; }}
#sidebar {{ width: var(--sidebar-w); flex-shrink: 0; border-right: 1px solid var(--border);
  background: var(--card); display: flex; flex-direction: column; overflow: hidden; }}
#main {{ flex: 1; overflow-y: auto; }}

/* Sidebar */
#sidebar-header {{ padding: 1rem; border-bottom: 1px solid var(--border); }}
#sidebar-header h1 {{ font-size: 1rem; font-weight: 700; margin-bottom: 0.5rem; }}
#search {{ width: 100%; padding: 0.35rem 0.6rem; border: 1px solid var(--border);
  border-radius: 6px; background: var(--bg); color: var(--text); font-size: 0.8rem; }}
#search:focus {{ outline: 2px solid var(--accent); border-color: transparent; }}
.filter-row {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid var(--border);
  display: flex; flex-wrap: wrap; gap: 0.25rem; }}
.chip {{ display: inline-flex; align-items: center; padding: 0.15rem 0.5rem;
  border-radius: 9999px; font-size: 0.72rem; font-weight: 500; cursor: pointer;
  border: 1px solid var(--border); background: var(--chip-bg); color: var(--text);
  transition: background 0.1s; user-select: none; }}
.chip.active {{ background: var(--chip-active); color: var(--chip-active-text); border-color: transparent; }}
#list-count {{ padding: 0.35rem 0.75rem; font-size: 0.72rem; color: var(--muted);
  border-bottom: 1px solid var(--border); }}
#author-list {{ flex: 1; overflow-y: auto; }}
.author-item {{ padding: 0.6rem 0.75rem; cursor: pointer; border-bottom: 1px solid var(--border);
  font-size: 0.82rem; display: flex; flex-direction: column; gap: 0.1rem; }}
.author-item:hover {{ background: var(--accent-bg); }}
.author-item.active {{ background: var(--accent-bg); border-left: 3px solid var(--accent); }}
.author-item .a-name {{ font-weight: 600; }}
.author-item .a-meta {{ color: var(--muted); font-size: 0.72rem; }}

/* Main / profile */
#profile-area {{ padding: 2rem; max-width: 800px; }}
#empty-state {{ padding: 4rem 2rem; text-align: center; color: var(--muted); }}
.profile-header {{ margin-bottom: 1.5rem; }}
.profile-header-inner {{ display: flex; gap: 1rem; align-items: flex-start; }}
.profile-photo {{ width: 72px; height: 72px; object-fit: cover; border-radius: 8px;
  border: 1px solid var(--border); flex-shrink: 0; }}
.profile-name {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 0.25rem; }}
.profile-meta {{ color: var(--muted); font-size: 0.875rem; margin-bottom: 0.5rem; }}
.profile-links {{ display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; font-size: 0.82rem; }}
.profile-links a {{ color: var(--accent); text-decoration: none; }}
.profile-links a:hover {{ text-decoration: underline; }}
.edit-btn {{ display: inline-flex; align-items: center; padding: 0.2rem 0.6rem;
  background: var(--chip-bg); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text) !important; font-size: 0.75rem; font-weight: 500;
  text-decoration: none !important; }}
.edit-btn:hover {{ background: var(--accent-bg); border-color: var(--accent); }}
.profile-note {{ background: var(--accent-bg); border-left: 3px solid var(--accent);
  padding: 0.6rem 0.9rem; border-radius: 0 6px 6px 0; margin-bottom: 1.25rem;
  font-size: 0.875rem; color: var(--text); }}
.section {{ margin-bottom: 1.5rem; }}
.section h3 {{ font-size: 0.8rem; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.6rem; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(130px,1fr)); gap: 0.5rem; }}
.stat-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 0.6rem 0.75rem; }}
.stat-card .val {{ font-size: 1.25rem; font-weight: 700; color: var(--accent); }}
.stat-card .lbl {{ font-size: 0.72rem; color: var(--muted); margin-top: 0.1rem; }}
.kv-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
.kv-table td {{ padding: 0.3rem 0.5rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
.kv-table td:first-child {{ color: var(--muted); width: 38%; white-space: nowrap; font-weight: 500; }}
.badge {{ display: inline-block; padding: 0.1rem 0.45rem; border-radius: 4px; font-size: 0.72rem;
  font-weight: 600; background: var(--chip-bg); color: var(--text); margin-right: 0.25rem; }}

@media (max-width: 640px) {{
  #app {{ flex-direction: column; height: auto; }}
  #sidebar {{ width: 100%; max-height: 50vh; }}
  #main {{ overflow: visible; }}
}}
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div id="sidebar-header">
      <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem">
        <h1 style="flex:1">Hungarian CS Authors</h1>
        <a href="{new_author_github_url}" target="_blank" rel="noopener"
           class="edit-btn" title="Új szerző hozzáadása GitHubon (sablon nyílik meg)">+ Új szerző</a>
      </div>
      <input id="search" type="search" placeholder="Keresés (név, intézmény)…">
    </div>
    <div class="filter-row">
      <span class="chip active" data-group="cat" data-val="">All</span>
      <span class="chip" data-group="cat" data-val="theory">Theory</span>
      <span class="chip" data-group="cat" data-val="applied">Applied</span>
    </div>
    <div class="filter-row">
      <span class="chip active" data-group="works" data-val="">All</span>
      <span class="chip" data-group="works" data-val="abroad">Abroad</span>
      <span class="chip" data-group="works" data-val="hungary">Hungary</span>
    </div>
    <div id="list-count"></div>
    <div id="author-list"></div>
  </div>
  <div id="main">
    <div id="profile-area">
      <div id="empty-state">← Select an author</div>
      <div id="profile" style="display:none"></div>
    </div>
  </div>
</div>
<script>
const AUTHORS = {data_json};

// Index by slug for fast hash-based routing
const BY_SLUG = {{}};
AUTHORS.forEach(a => BY_SLUG[a.slug] = a);

let filterCat = "", filterWorks = "", searchQ = "";
let currentSlug = "";

function esc(s) {{
  return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}}

function fmt(v, digits=0) {{
  if (v === null || v === undefined) return "–";
  return typeof v === "number" ? v.toFixed(digits) : String(v);
}}

function renderList() {{
  const q = searchQ.toLowerCase();
  const filtered = AUTHORS.filter(a => {{
    if (filterCat && a.category !== filterCat) return false;
    if (filterWorks) {{
      const w = (a.works || "").toLowerCase();
      if (filterWorks === "abroad" && !w.includes("abroad")) return false;
      if (filterWorks === "hungary" && w.includes("abroad")) return false;
    }}
    if (q) {{
      const hay = ((a.name||"")+" "+(a.affiliations||"")+" "+(a.mtmt_affiliations||"")+" "+(a.dblp_institutions||"")).toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

  document.getElementById("list-count").textContent = filtered.length + " / " + AUTHORS.length + " author";

  const el = document.getElementById("author-list");
  el.innerHTML = filtered.map(a => {{
    const active = a.slug === currentSlug ? " active" : "";
    const astar = a.core_astar != null ? `${{a.core_astar}} A*` : "";
    const cat = a.category ? `<span class="badge">${{esc(a.category)}}</span>` : "";
    return `<div class="author-item${{active}}" data-slug="${{a.slug}}">
      <span class="a-name">${{esc(a.name)}}</span>
      <span class="a-meta">${{cat}}${{astar}} · ${{esc(a.works||"")}} · ${{esc(a.affiliations||"").slice(0,50)}}</span>
    </div>`;
  }}).join("");

  el.querySelectorAll(".author-item").forEach(el => {{
    el.addEventListener("click", () => selectAuthor(el.dataset.slug));
  }});
}}

function renderProfile(a) {{
  if (!a) {{
    document.getElementById("profile").style.display = "none";
    document.getElementById("empty-state").style.display = "";
    return;
  }}
  document.getElementById("empty-state").style.display = "none";
  document.getElementById("profile").style.display = "";

  const links = [];
  if (a.homepage) links.push(`<a href="${{esc(a.homepage)}}" target="_blank">Homepage</a>`);
  if (a.dblp_url) links.push(`<a href="${{esc(a.dblp_url)}}" target="_blank">DBLP</a>`);
  if (a.mtmt_id) links.push(`<a href="https://m2.mtmt.hu/api/author/${{a.mtmt_id}}" target="_blank">MTMT</a>`);
  if (a.mta_att_id && a.mta_att_id !== "-") links.push(`<a href="${{esc(a.mta_att_id)}}" target="_blank">MTA</a>`);

  const note = a.note ? `<div class="profile-note">${{esc(a.note)}}</div>` : "";

  const statsData = [
    ["Core A*", a.core_astar, ""],
    ["Core A* eq.", a.core_astar_equiv, ".2f"],
    ["1st Author eq.", a.first_author_core_astar_equiv, ".2f"],
    ["HU eq.", a.hungarian_core_astar_equiv, ".2f"],
    ["Core A", a.core_a, ""],
    ["Citations", a.mtmt_citations, ""],
    ["D1 eq.", a.mtmt_d1_equiv, ".1f"],
  ].filter(([,v]) => v != null && v !== 0);

  const stats = statsData.length ? `<div class="section">
    <h3>Metrics</h3>
    <div class="stats-grid">
      ${{statsData.map(([lbl, v, fmt_]) => `<div class="stat-card">
        <div class="val">${{typeof v === "number" && fmt_ ? v.toFixed(parseInt(fmt_)) : fmt(v)}}</div>
        <div class="lbl">${{lbl}}</div>
      </div>`).join("")}}
    </div>
  </div>` : "";

  const kvRows = [
    ["Affiliations", a.affiliations],
    ["Category", a.category],
    ["Works", a.works],
    ["DBLP institutions", a.dblp_institutions],
    ["MTMT affiliations", a.mtmt_affiliations],
    ["Research topic", a.research_topic || a.profile_research_focus],
    ["Degree", a.degree],
    ["PhD year", a.phd_year],
    ["MTA membership", a.mta_membership],
    ["Awards", a.awards],
    ["Born", a.born],
  ].filter(([,v]) => v);

  const kv = kvRows.length ? `<div class="section">
    <h3>Details</h3>
    <table class="kv-table">
      ${{kvRows.map(([k,v]) => `<tr><td>${{k}}</td><td>${{esc(String(v))}}</td></tr>`).join("")}}
    </table>
  </div>` : "";

  const journalRows = [
    ["D1", a.mtmt_d1], ["Q1", a.mtmt_q1], ["Q2", a.mtmt_q2],
    ["Q3", a.mtmt_q3], ["Q4", a.mtmt_q4],
  ].filter(([,v]) => v);

  const journals = journalRows.length ? `<div class="section">
    <h3>Journal Rankings (MTMT)</h3>
    <table class="kv-table">
      ${{journalRows.map(([k,v]) => `<tr><td>${{k}}</td><td>${{v}}</td></tr>`).join("")}}
      <tr><td>All journal pubs</td><td>${{a.mtmt_journals ?? "–"}}</td></tr>
      <tr><td>Conference pubs</td><td>${{a.mtmt_conferences ?? "–"}}</td></tr>
    </table>
  </div>` : "";

  const photo = a.mta_photo
    ? `<img src="${{esc(a.mta_photo)}}" class="profile-photo" alt="MTA photo"
        onerror="this.style.display='none'">`
    : "";

  const editLabel = a._has_profile ? "✏️ Szerkesztés (GitHub)" : "✏️ Adatok javítása (GitHub)";
  const editTitle = a._has_profile
    ? "profiles/" + a.slug + ".json szerkesztése GitHubon — megnyílik előtöltött adatokkal"
    : "Előtöltött sablonnal nyílik meg a GitHub szerkesztő — dblp_url, mtmt_id, kategória stb. módosítható";
  const editBtn = `<a class="edit-btn" href="${{a._github_edit_url}}" target="_blank" rel="noopener" title="${{editTitle}}">${{editLabel}}</a>`;

  document.getElementById("profile").innerHTML = `
    <div class="profile-header">
      <div class="profile-header-inner">
        ${{photo}}
        <div>
          <div class="profile-name">${{esc(a.name)}}</div>
          <div class="profile-meta">${{esc(a.mtmt_name || "")}}</div>
          <div class="profile-links">${{links.join("&ensp;·&ensp;")}}&ensp;${{editBtn}}</div>
        </div>
      </div>
    </div>
    ${{note}}
    ${{stats}}
    ${{kv}}
    ${{journals}}
  `;
}}

function selectAuthor(slug) {{
  currentSlug = slug;
  window.location.hash = slug;
  renderProfile(BY_SLUG[slug]);
  // Update active state in list
  document.querySelectorAll(".author-item").forEach(el => {{
    el.classList.toggle("active", el.dataset.slug === slug);
  }});
  // Scroll selected item into view
  const active = document.querySelector(".author-item.active");
  if (active) active.scrollIntoView({{block: "nearest"}});
}}

// Filters
document.querySelectorAll(".chip").forEach(chip => {{
  chip.addEventListener("click", () => {{
    const group = chip.dataset.group;
    document.querySelectorAll(`.chip[data-group="${{group}}"]`).forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    if (group === "cat") filterCat = chip.dataset.val;
    if (group === "works") filterWorks = chip.dataset.val;
    renderList();
  }});
}});

document.getElementById("search").addEventListener("input", e => {{
  searchQ = e.target.value.trim();
  renderList();
}});

// Hash routing
function handleHash() {{
  const slug = window.location.hash.slice(1);
  if (slug && BY_SLUG[slug]) {{
    currentSlug = slug;
    renderList();
    renderProfile(BY_SLUG[slug]);
    const active = document.querySelector(".author-item.active");
    if (active) active.scrollIntoView({{block: "nearest"}});
  }}
}}

window.addEventListener("hashchange", handleHash);

// Init
renderList();
handleHash();
</script>
</body>
</html>
"""


def main():
    authors = json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))
    profiles = load_profiles(PROFILES_DIR)
    merged = merge(authors, profiles)
    html = generate(merged)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"Generated {OUT_FILE} with {len(merged)} authors ({len(profiles)} profiles)")


if __name__ == "__main__":
    main()
