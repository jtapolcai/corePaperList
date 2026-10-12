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
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
AUTHORS_JSON = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "authors.json"
PROFILES_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "profiles"
OUT_FILE = BASE / "authors_profile.html"


def load_profiles(profiles_dir: Path) -> tuple[dict, set]:
    """Returns (profiles_dict, file_backed_slugs).
    file_backed_slugs contains only slugs with actual per-author JSON files
    (not bulk overrides), used to determine has_profile in the UI.
    """
    profiles = {}
    file_backed: set = set()
    if not profiles_dir.exists():
        return profiles, file_backed
    # Load bulk overrides first (lowest priority)
    bulk_file = profiles_dir / "_works_overrides.json"
    if bulk_file.exists():
        try:
            for slug, fields in json.loads(bulk_file.read_text(encoding="utf-8")).items():
                profiles.setdefault(slug, {}).update(fields)
        except Exception as e:
            print(f"Warning: could not parse {bulk_file}: {e}")
    # Per-author profiles override bulk (highest priority)
    for f in profiles_dir.glob("*.json"):
        if f.stem.startswith("_"):
            continue
        try:
            profiles[f.stem] = {**profiles.get(f.stem, {}), **json.loads(f.read_text(encoding="utf-8"))}
            file_backed.add(f.stem)
        except Exception as e:
            print(f"Warning: could not parse {f}: {e}")
    return profiles, file_backed


GITHUB_REPO = "jtapolcai/corePaperList"
GITHUB_BRANCH = "main"

# Fields the user manually edits in profiles/{slug}.json
EDITABLE_FIELDS = [
    "dblp_url", "mtmt_id", "mtmt_name", "mta_att_id", "mta_photo",
    "category", "mtmt_status", "works", "affiliations", "age_group",
    "linkedin", "homepage", "note",
]


def profile_template(author: dict) -> str:
    """Build a JSON template pre-filled with the author's current non-empty values."""
    obj = {k: v for k in EDITABLE_FIELDS if (v := author.get(k) or "")}
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
    "mtmt_name": "",
    "mta_att_id": "",
    "mta_photo": "",
    "category": "theory",
    "mtmt_status": "",
    "works": "",
    "affiliations": "",
    "linkedin": "",
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


def merge(authors: list, profiles: dict, file_backed: set | None = None) -> list:
    """Apply profile overrides directly onto author fields (no profile_ prefix)."""
    for a in authors:
        slug = a.get("slug", "")
        has_profile = slug in (file_backed if file_backed is not None else profiles)
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


def enrich_mta_photos(authors: list, profiles_dir: Path) -> list:
    """Apply MTA photo URLs from profiles/_mta_photos.json cache (no HTTP)."""
    cache_file = profiles_dir / "_mta_photos.json"
    if not cache_file.exists():
        return authors
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return authors
    for a in authors:
        if a.get("mta_photo"):
            continue
        photo = cache.get(a.get("slug", ""), "")
        if photo:
            a["mta_photo"] = photo
    return authors


def compute_ranks(authors: list) -> list:
    """Add hung_astar_rank / hung_astar_total to each Hungarian author."""
    hung = sorted(
        [a for a in authors if a.get("works") == "hungary" and a.get("core_astar_equiv", 0) > 0],
        key=lambda x: -x.get("core_astar_equiv", 0),
    )
    total = len(hung)
    rank_map = {a["slug"]: i for i, a in enumerate(hung, 1)}
    for a in authors:
        r = rank_map.get(a.get("slug", ""))
        if r is not None:
            a["hung_astar_rank"] = r
            a["hung_astar_total"] = total
    return authors


def generate(authors: list) -> str:
    authors = compute_ranks(authors)
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
a.stat-link {{ text-decoration: none; cursor: pointer; display: block; transition: border-color 0.15s, background 0.15s; }}
a.stat-link:hover {{ border-color: var(--accent); background: var(--accent-bg); }}
.kv-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
.kv-table td {{ padding: 0.3rem 0.5rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
.kv-table td:first-child {{ color: var(--muted); width: 38%; white-space: nowrap; font-weight: 500; }}
.badge {{ display: inline-block; padding: 0.1rem 0.45rem; border-radius: 4px; font-size: 0.72rem;
  font-weight: 600; background: var(--chip-bg); color: var(--text); margin-right: 0.25rem; }}
.pencil-btn {{ background: none; border: none; cursor: pointer; font-size: 0.72rem; padding: 0 0.2rem;
  opacity: 0.4; line-height: 1; vertical-align: middle; }}
.pencil-btn:hover {{ opacity: 1; }}
.edit-ctrl {{ font-size: 0.82rem; border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg); color: var(--text); padding: 0.15rem 0.3rem; width: 100%; box-sizing: border-box; }}
.edit-ctrl:disabled {{ border-color: transparent; background: transparent; cursor: default; }}
.edit-ctrl:not(:disabled) {{ border-color: var(--accent); background: var(--card); }}
#edit-save-bar {{ display: none; position: sticky; bottom: 0; left: 0; right: 0; z-index: 50;
  background: var(--accent); color: #fff; padding: 0.6rem 1rem; gap: 0.75rem; align-items: center; }}
#edit-save-bar button {{ background: #fff; color: var(--accent); border: none; border-radius: 6px;
  padding: 0.3rem 0.9rem; font-weight: 700; cursor: pointer; font-size: 0.82rem; }}
#edit-save-bar .cancel-btn {{ background: transparent; color: #fff; text-decoration: underline;
  border: none; cursor: pointer; font-size: 0.82rem; }}
#json-modal {{ display:none; position:fixed; inset:0; z-index:200; background:rgba(0,0,0,0.5);
  align-items:center; justify-content:center; }}
#json-modal-inner {{ background:var(--card); border-radius:10px; padding:1.25rem; max-width:540px;
  width:90%; display:flex; flex-direction:column; gap:0.75rem; }}
#json-modal h3 {{ font-size:0.95rem; margin:0; }}
#json-modal textarea {{ font-family:monospace; font-size:0.78rem; border:1px solid var(--border);
  border-radius:6px; padding:0.5rem; resize:vertical; min-height:180px; background:var(--bg);
  color:var(--text); }}
#json-modal .modal-actions {{ display:flex; gap:0.5rem; flex-wrap:wrap; }}
#json-modal .modal-actions button, #json-modal .modal-actions a {{
  padding:0.3rem 0.8rem; border-radius:6px; font-size:0.82rem; cursor:pointer;
  border:1px solid var(--border); text-decoration:none; background:var(--chip-bg); color:var(--text); }}
#json-modal .modal-actions .primary {{ background:var(--accent); color:#fff; border-color:transparent; }}
.mtmt-results {{ margin-top:0.4rem; border:1px solid var(--border); border-radius:6px; overflow:hidden; }}
.mtmt-results-label {{ padding:0.3rem 0.6rem; font-size:0.72rem; color:var(--muted); background:var(--chip-bg); }}
.mtmt-option {{ padding:0.4rem 0.6rem; cursor:pointer; font-size:0.8rem; border-top:1px solid var(--border); }}
.mtmt-option:hover {{ background:var(--accent-bg); }}
.mtmt-option.selected {{ background:var(--accent-bg); border-left:3px solid var(--accent); font-weight:600; }}
.mtmt-loading, .mtmt-no-results {{ padding:0.4rem 0.6rem; font-size:0.8rem; color:var(--muted); }}
.mta-hint, .linkedin-hint {{ font-size:0.78rem; margin-top:0.25rem; }}
.mta-hint a, .linkedin-hint a {{ color:var(--accent); text-decoration:none; }}
.mta-hint a:hover, .linkedin-hint a:hover {{ text-decoration:underline; }}

@media (max-width: 640px) {{
  #app {{ flex-direction: column; height: auto; }}
  #sidebar {{ width: 100%; max-height: 50vh; }}
  #main {{ overflow: visible; }}
}}
</style>
</head>
<body>
<div id="json-modal">
  <div id="json-modal-inner">
    <h3>Frissített profil — másold be a GitHub szerkesztőbe</h3>
    <textarea id="json-modal-text" readonly rows="10"></textarea>
    <div class="modal-actions">
      <button class="primary" onclick="navigator.clipboard.writeText(document.getElementById('json-modal-text').value).then(()=>this.textContent='✓ Másolva!')">📋 Másolás</button>
      <a id="json-modal-gh-link" href="#" target="_blank" rel="noopener">GitHub szerkesztő →</a>
      <button onclick="document.getElementById('json-modal').style.display='none'">Bezárás</button>
    </div>
  </div>
</div>
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
      <div id="edit-save-bar">
        <span style="flex:1;font-size:0.85rem">Módosítások elmentése GitHubra</span>
        <button onclick="saveEdits()">💾 Mentés →</button>
        <button class="cancel-btn" onclick="cancelEdits()">Mégse</button>
      </div>
    </div>
  </div>
</div>
<script>
const AUTHORS = {data_json};
const GITHUB_REPO   = "{GITHUB_REPO}";
const GITHUB_BRANCH = "{GITHUB_BRANCH}";

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

function editField(key) {{
  const el = document.querySelector(`[data-edit="${{key}}"]`);
  if (!el) return;
  el.disabled = false;
  el.focus();
  document.getElementById("edit-save-bar").style.display = "flex";

  if (key === "mtmt_id") {{
    const a = BY_SLUG[currentSlug];
    if (a) searchMTMT(a.name || "");
  }}
  if (key === "mta_att_id") {{
    const a = BY_SLUG[currentSlug];
    if (a) {{
      const name = (a.name || "").replace(/\\s+\\d{{4}}$/, "").trim();
      const hint = document.getElementById("mta-hint");
      if (hint) {{
        hint.style.display = "";
        hint.innerHTML = `<a href="https://mta.hu/koztestuleti_tagok?kereses=${{encodeURIComponent(name)}}" target="_blank" rel="noopener">🔍 Keresés az MTA adatbázisában →</a>`;
      }}
    }}
  }}
  if (key === "linkedin") {{
    const a = BY_SLUG[currentSlug];
    if (a) {{
      const name = (a.name || "").replace(/\\s+\\d{{4}}$/, "").trim();
      const hint = document.getElementById("linkedin-hint");
      if (hint) {{
        hint.style.display = "";
        hint.innerHTML = `<a href="https://www.linkedin.com/search/results/people/?keywords=${{encodeURIComponent(name)}}" target="_blank" rel="noopener">🔍 Keresés LinkedIn-en →</a>`;
      }}
    }}
  }}
}}

async function searchMTMT(fullName) {{
  const container = document.getElementById("mtmt-results");
  if (!container) return;
  const cleanName = fullName.replace(/\\s+\\d{{4}}$/, "").trim();
  const parts = cleanName.split(/\\s+/);
  if (parts.length < 2) return;

  container.style.display = "";
  container.innerHTML = `<div class="mtmt-loading">Keresés az MTMT-ben…</div>`;

  // Try last word (Western name order) then first word (Hungarian order)
  const candidates = [...new Set([parts[parts.length - 1], parts[0]])];
  const seen = new Map();
  for (const fam of candidates) {{
    try {{
      const url = `https://m2.mtmt.hu/api/author?cond=familyName;eq;${{encodeURIComponent(fam)}}&format=json&size=25`;
      const resp = await fetch(url, {{credentials: "omit"}});
      const data = await resp.json();
      for (const c of (data.content || [])) {{
        if (!seen.has(c.mtid)) seen.set(c.mtid, c);
      }}
    }} catch(e) {{ /* ignore */ }}
  }}

  if (seen.size === 0) {{
    container.innerHTML = `<div class="mtmt-no-results">Nem található az MTMT-ben.</div>`;
    return;
  }}
  const items = [...seen.values()].map(c => {{
    const safeLabel = esc(c.label || "");
    return `<div class="mtmt-option" onclick="selectMTMT(${{c.mtid}}, ${{JSON.stringify(c.label||'')}}, this)"><strong>${{c.mtid}}</strong> — ${{safeLabel}}</div>`;
  }}).join("");
  container.innerHTML = `<div class="mtmt-results-label">Kattints a megfelelő szerzőre:</div>${{items}}`;
}}

function selectMTMT(mtid, label, el) {{
  const idInput = document.querySelector('[data-edit="mtmt_id"]');
  if (idInput) {{ idInput.value = String(mtid); idInput.disabled = false; }}
  const nameInput = document.querySelector('[data-edit="mtmt_name"]');
  if (nameInput) {{ nameInput.value = label; }}
  const nameDisplay = document.getElementById("mtmt-name-display");
  if (nameDisplay) nameDisplay.textContent = label;
  document.querySelectorAll(".mtmt-option").forEach(o => o.classList.remove("selected"));
  el.classList.add("selected");
  document.getElementById("edit-save-bar").style.display = "flex";
}}

function cancelEdits() {{
  document.querySelectorAll("[data-edit]").forEach(el => {{
    el.disabled = true;
    const a = BY_SLUG[currentSlug];
    if (a) el.value = a[el.dataset.edit] || "";
  }});
  ["mta-hint","mtmt-results","linkedin-hint"].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  }});
  document.getElementById("edit-save-bar").style.display = "none";
}}

function saveEdits() {{
  const tbl = document.getElementById("edit-kv-table");
  if (!tbl) return;
  const slug = tbl.dataset.slug;
  const hasProfile = tbl.dataset.hasProfile === "1";
  const editUrl = tbl.dataset.editUrl;

  const updated = {{}};
  document.querySelectorAll("[data-edit]").forEach(el => {{
    const v = el.value.trim();
    if (v) updated[el.dataset.edit] = v;
  }});

  const json = JSON.stringify(updated, null, 2);
  const encoded = encodeURIComponent(json);

  if (hasProfile) {{
    // Existing profile: show modal with JSON to copy + link to editor
    document.getElementById("json-modal-text").value = json;
    document.getElementById("json-modal-gh-link").href = editUrl;
    document.getElementById("json-modal").style.display = "flex";
  }} else {{
    // New profile: open GitHub new-file form pre-filled
    const url = `https://github.com/${{GITHUB_REPO}}/new/${{GITHUB_BRANCH}}?filename=profiles/${{slug}}.json&value=${{encoded}}`;
    window.open(url, "_blank");
  }}
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
  if (a.linkedin) links.push(`<a href="${{esc(a.linkedin)}}" target="_blank">LinkedIn</a>`);
  if (a.dblp_url) links.push(`<a href="${{esc(a.dblp_url)}}" target="_blank">DBLP</a>`);
  if (a.mtmt_id) links.push(`<a href="https://m2.mtmt.hu/api/author/${{a.mtmt_id}}" target="_blank">MTMT</a>`);
  if (a.mta_att_id && a.mta_att_id !== "-") links.push(`<a href="${{esc(a.mta_att_id)}}" target="_blank">MTA</a>`);

  const note = a.note ? `<div class="profile-note">${{esc(a.note)}}</div>` : "";

  const astarUrl = `core_astar.html?author=${{a.slug}}&tier=astar&name=${{encodeURIComponent(a.name.replace(/\\s+\\d{{4}}$/,""))}}`;
  const aUrl     = `core_astar.html?author=${{a.slug}}&tier=a&name=${{encodeURIComponent(a.name.replace(/\\s+\\d{{4}}$/,""))}}`;
  const cleanName     = (a.name || "").replace(/\s+\d{{4}}$/, "").trim();
  const hungTableUrl  = a.works === "hungary" ? `authors_table.html?munkahely=hungary&highlight=${{encodeURIComponent(cleanName)}}` : "";
  const catTableUrl   = a.works === "hungary" && a.category ? `authors_table.html?munkahely=hungary&tema=${{encodeURIComponent(a.category)}}&highlight=${{encodeURIComponent(cleanName)}}` : "";
  const ageTableUrl   = a.works === "hungary" && a.age_group ? `authors_table.html?munkahely=hungary&karrier=${{encodeURIComponent(a.age_group)}}&highlight=${{encodeURIComponent(cleanName)}}` : "";
  const hungRankStr   = a.hung_astar_rank != null ? `${{a.hung_astar_rank}}/${{a.hung_astar_total}}` : null;
  const statsData = [
    ["Core A*",        a.core_astar,                    0,    a.core_astar_papers > 0 ? astarUrl : ""],
    ["Core A* eq.",    a.core_astar_equiv,              2,    a.core_astar_papers > 0 ? astarUrl : ""],
    ["1st Author eq.", a.first_author_core_astar_equiv, 2,    a.core_astar_papers > 0 ? astarUrl : ""],
    ["HU eq.",         a.hungarian_core_astar_equiv,    2,    a.core_astar_papers > 0 ? astarUrl : ""],
    ["Core A",         a.core_a,                        0, a.core_a_papers > 0 ? aUrl : ""],
    ["Citations",      a.mtmt_citations,                0, ""],
    ["D1 eq.",         a.mtmt_d1_equiv,                 1, ""],
    ["Magyar rang",    hungRankStr,                     null, hungTableUrl],
    ["Kat. rang",      a.category_astar_rank,           0,    catTableUrl],
    ["Életkor rang",   a.age_astar_rank,                0,    ageTableUrl],
  ].filter(([,v]) => v != null && v !== 0);

  const stats = statsData.length ? `<div class="section">
    <h3>Metrics</h3>
    <div class="stats-grid">
      ${{statsData.map(([lbl, v, fmt_, url]) => {{
        const valStr = typeof v === "number" && fmt_ != null ? v.toFixed(fmt_) : fmt(v);
        const inner  = `<div class="val">${{valStr}}</div><div class="lbl">${{lbl}}</div>`;
        return url
          ? `<a class="stat-card stat-link" href="${{url}}" title="${{lbl}} cikkek listája">${{inner}}</a>`
          : `<div class="stat-card">${{inner}}</div>`;
      }}).join("")}}
    </div>
  </div>` : "";

  // Editable fields with pencil buttons (mtmt_name is auto-filled by MTMT search)
  const EDIT_FIELDS = [
    {{key:"dblp_url",    label:"DBLP URL",      type:"text"}},
    {{key:"mta_att_id",  label:"MTA URL",        type:"text"}},
    {{key:"mta_photo",   label:"Fotó URL",        type:"text"}},
    {{key:"mtmt_id",     label:"MTMT ID",        type:"text"}},
    {{key:"category",    label:"Kategória",      type:"select", opts:["","theory","applied"]}},
    {{key:"works",       label:"Munkahely",      type:"select", opts:["","hungary","abroad","company_hungary","company_abroad","inactive","retired"]}},
    {{key:"mtmt_status", label:"MTMT státusz",   type:"select", opts:["","active","inactive"]}},
    {{key:"affiliations",label:"Affiliációk",    type:"text"}},
    {{key:"linkedin",    label:"LinkedIn URL",   type:"text"}},
    {{key:"homepage",    label:"Honlap",         type:"text"}},
    {{key:"note",        label:"Megjegyzés",     type:"text"}},
  ];
  const editRows = EDIT_FIELDS.map(f => {{
    const val = String(a[f.key] || "");
    const pencil = `<button class="pencil-btn" onclick="editField('${{f.key}}')" title="${{f.label}} szerkesztése">✏</button>`;
    let ctrl;
    if (f.type === "select") {{
      const opts = f.opts.map(o => `<option value="${{o}}"${{o===val?" selected":""}}>${{o||"—"}}</option>`).join("");
      ctrl = `<select data-edit="${{f.key}}" disabled class="edit-ctrl">${{opts}}</select>`;
    }} else {{
      ctrl = `<input type="text" data-edit="${{f.key}}" value="${{esc(val)}}" disabled class="edit-ctrl">`;
    }}
    let extra = "";
    if (f.key === "mtmt_id") extra = `
      <input type="hidden" data-edit="mtmt_name" id="mtmt-name-hidden" value="${{esc(a.mtmt_name||"")}}">
      <div id="mtmt-name-display" style="font-size:12px;color:var(--text-secondary);margin-top:2px">${{esc(a.mtmt_name||"")}}</div>
      <div id="mtmt-results" class="mtmt-results" style="display:none"></div>`;
    if (f.key === "mta_att_id") extra = `<div id="mta-hint" class="mta-hint" style="display:none"></div>`;
    if (f.key === "linkedin")   extra = `<div id="linkedin-hint" class="linkedin-hint" style="display:none"></div>`;
    return `<tr><td>${{pencil}} ${{f.label}}</td><td>${{ctrl}}${{extra}}</td></tr>`;
  }}).join("");

  // Read-only fields
  const roRows = [
    ["DBLP intézmények", a.dblp_institutions],
    ["MTMT affiliációk", a.mtmt_affiliations],
    ["Kutatási téma",    a.research_topic],
    ["Fokozat",          a.degree],
    ["PhD év",           a.phd_year],
    ["Díjak",            a.awards],
    ["Született",        a.born],
  ].filter(([,v]) => v)
   .map(([k,v]) => `<tr><td>${{k}}</td><td>${{esc(String(v))}}</td></tr>`).join("");

  const kv = `<div class="section">
    <h3>Details</h3>
    <table class="kv-table" id="edit-kv-table" data-slug="${{a.slug}}" data-has-profile="${{a._has_profile ? "1" : "0"}}"
           data-edit-url="${{esc(a._github_edit_url)}}">
      ${{editRows}}${{roRows}}
    </table>
  </div>`;

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


def load_new_authors(profiles_dir: Path, existing_slugs: set) -> list:
    """Profiles whose slug is NOT in authors.json are treated as new authors."""
    new_authors = []
    if not profiles_dir.exists():
        return new_authors
    for f in profiles_dir.glob("*.json"):
        if f.stem.startswith("_") or f.stem in existing_slugs:
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: {f}: {e}")
            continue
        if not p.get("name"):
            continue
        slug = f.stem
        a = {k: None for k in [
            "core_astar", "core_a", "core_astar_equiv", "first_author_core_astar_equiv",
            "hungarian_core_astar_equiv", "core_b", "core_c", "mtmt_citations",
            "mtmt_d1_equiv", "mtmt_d1", "mtmt_q1", "mtmt_q2", "mtmt_q3", "mtmt_q4",
            "mtmt_journals", "mtmt_conferences", "dblp_institutions", "mtmt_affiliations",
        ]}
        a["slug"] = slug
        for k in EDITABLE_FIELDS:
            a[k] = p.get(k, "")
        a["name"] = p.get("name", slug)
        a["_has_profile"] = True
        a["_github_edit_url"] = (
            f"https://github.com/{GITHUB_REPO}/edit/{GITHUB_BRANCH}/profiles/{slug}.json"
        )
        new_authors.append(a)
        print(f"  New author from profile: {a['name']} ({slug})")
    return new_authors


def main():
    authors = json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))
    profiles, file_backed = load_profiles(PROFILES_DIR)
    merged = merge(authors, profiles, file_backed)

    existing_slugs = {a["slug"] for a in authors}
    new_authors = load_new_authors(PROFILES_DIR, existing_slugs)
    merged.extend(new_authors)

    enrich_mta_photos(merged, PROFILES_DIR)

    html = generate(merged)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"Generated {OUT_FILE} with {len(merged)} authors ({len(profiles)} profiles, {len(new_authors)} new)")


if __name__ == "__main__":
    main()
