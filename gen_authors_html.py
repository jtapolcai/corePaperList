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
ANON_AUTHORS_JSON = BASE / "anon_authors.json"
IGNORE_AUTHORS_JSON = BASE / "ignore_authors.json"
OUT_FILE = BASE / "authors_profile.html"


def _slugs_from_file(path) -> set:
    from pathlib import Path as _P
    p = _P(path)
    if not p.exists():
        return set()
    try:
        return {e["slug"] for e in json.loads(p.read_text(encoding="utf-8")) if e.get("slug")}
    except Exception:
        return set()


def load_anon_slugs() -> set:
    """Slugs from anon_authors.json (appear in profile with metrics hidden)."""
    return _slugs_from_file(ANON_AUTHORS_JSON)


def load_ignore_slugs() -> set:
    """Slugs from ignore_authors.json (completely excluded from profile list)."""
    return _slugs_from_file(IGNORE_AUTHORS_JSON)


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
    "category", "mtmt_status", "works", "affiliations",
    "linkedin", "homepage", "note", "phd_year",
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
        [a for a in authors if a.get("works") == "hungary" and (a.get("core_astar_equiv") or 0) > 0],
        key=lambda x: -(x.get("core_astar_equiv") or 0),
    )
    total = len(hung)
    rank_map = {a["slug"]: i for i, a in enumerate(hung, 1)}
    for a in authors:
        r = rank_map.get(a.get("slug", ""))
        if r is not None:
            a["hung_astar_rank"] = r
            a["hung_astar_total"] = total
    return authors


_ANON_HIDDEN_FIELDS = [
    "core_astar", "core_a", "core_b", "core_c", "no_core",
    "core_astar_equiv", "first_author_core_astar_equiv", "hungarian_core_astar_equiv",
    "hung_core_astar", "hung_core_a", "hung_core_b", "hung_core_c", "hung_no_core",
    "first_author_core_astar", "first_author_core_a", "first_author_core_b",
    "first_author_core_c", "first_author_no_core",
    "hung_astar_rank", "hung_astar_total", "category_astar_rank", "age_astar_rank",
    "core_astar_papers",
]


def generate(authors: list, anon_slugs: set | None = None, ignore_slugs: set | None = None) -> str:
    anon_slugs = anon_slugs or set()
    ignore_slugs = ignore_slugs or set()
    authors = compute_ranks(authors)
    # ignore_authors: completely excluded from profile list
    # anon_authors: appear in list but metrics are hidden
    masked = []
    ignored_count = 0
    for a in authors:
        slug = a.get("slug")
        if slug in ignore_slugs:
            ignored_count += 1
            continue
        if slug in anon_slugs:
            a = dict(a)
            for f in _ANON_HIDDEN_FIELDS:
                a.pop(f, None)
            a["_anon"] = True
        masked.append(a)
    anon_count = len(anon_slugs) + ignored_count
    data_json = json.dumps(masked, ensure_ascii=False)
    anon_count_js = anon_count

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
.sort-row {{ align-items: center; gap: 0.5rem; }}
.sort-row label {{ font-size: 0.72rem; color: var(--muted); white-space: nowrap; }}
.sort-row select {{ font-size: 0.72rem; padding: 0.15rem 0.3rem; border: 1px solid var(--border);
  border-radius: 4px; background: var(--chip-bg); color: var(--text); cursor: pointer; }}
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
.stat-card .src {{ font-size: 0.65rem; color: var(--muted); opacity: 0.7; margin-top: 0.25rem; }}
.stat-card .src a, .stat-card .src .src-link {{ color: inherit; text-decoration: underline dotted; cursor: pointer; }}
.stat-card .src a:hover, .stat-card .src .src-link:hover {{ opacity: 1; }}
a.stat-link {{ text-decoration: none; cursor: pointer; display: block; transition: border-color 0.15s, background 0.15s; }}
a.stat-link:hover {{ border-color: var(--accent); background: var(--accent-bg); }}
.topics-section {{ margin: 0.75rem 0 0; }}
.topics-section h4 {{ font-size: 0.72rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.4rem; }}
.topic-chips {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
.topic-chip {{ display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.2rem 0.55rem; border-radius: 999px;
  font-size: 0.72rem; background: var(--chip-bg); border: 1px solid var(--border); color: var(--text);
  text-decoration: none; transition: background 0.12s; }}
.topic-chip:hover {{ background: var(--chip-active); color: var(--chip-active-text); border-color: transparent; }}
.topic-chip .tc-count {{ font-size: 0.65rem; color: var(--muted); }}
.topic-chip:hover .tc-count {{ color: inherit; opacity: 0.75; }}
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
#clipboard-toast {{ display:none; position:fixed; bottom:1.5rem; left:50%; transform:translateX(-50%);
  background:#1d4ed8; color:#fff; padding:.65rem 1.3rem; border-radius:10px; font-size:.84rem;
  z-index:300; box-shadow:0 4px 16px rgba(0,0,0,.35); white-space:nowrap; pointer-events:none; }}
#clipboard-toast.fallback {{ background:var(--card); color:var(--text); border:1px solid var(--border);
  max-width:92vw; white-space:normal; pointer-events:all; }}
#clipboard-toast textarea {{ font-family:monospace; font-size:.75rem; width:100%; min-height:120px;
  border:1px solid var(--border); border-radius:6px; padding:.4rem; background:var(--bg);
  color:var(--text); margin-top:.5rem; resize:vertical; }}
#clipboard-toast .toast-actions {{ display:flex; gap:.5rem; margin-top:.5rem; flex-wrap:wrap; }}
#clipboard-toast .toast-actions button, #clipboard-toast .toast-actions a {{
  padding:.3rem .8rem; border-radius:6px; font-size:.8rem; cursor:pointer;
  border:1px solid var(--border); text-decoration:none; background:var(--chip-bg); color:var(--text); }}
#clipboard-toast .toast-actions .primary {{ background:var(--accent); color:#fff; border-color:transparent; }}
.mtmt-results {{ margin-top:0.4rem; border:1px solid var(--border); border-radius:6px; overflow:hidden; }}
.mtmt-results-label {{ padding:0.3rem 0.6rem; font-size:0.72rem; color:var(--muted); background:var(--chip-bg); }}
.mtmt-option {{ padding:0.4rem 0.6rem; cursor:pointer; font-size:0.8rem; border-top:1px solid var(--border); }}
.mtmt-option:hover {{ background:var(--accent-bg); }}
.mtmt-option.selected {{ background:var(--accent-bg); border-left:3px solid var(--accent); font-weight:600; }}
.mtmt-loading, .mtmt-no-results {{ padding:0.4rem 0.6rem; font-size:0.8rem; color:var(--muted); }}
.mta-hint, .linkedin-hint {{ font-size:0.78rem; margin-top:0.25rem; }}
.mta-hint a, .linkedin-hint a {{ color:var(--accent); text-decoration:none; }}
.mta-hint a:hover, .linkedin-hint a:hover {{ text-decoration:underline; }}

/* Add-author modal */
#add-modal-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:1000; align-items:center; justify-content:center; }}
#add-modal-overlay.open {{ display:flex; }}
#add-modal {{ background:var(--card); border:1px solid var(--border); border-radius:12px; width:min(600px,95vw);
  max-height:90vh; overflow-y:auto; padding:1.5rem; box-shadow:0 20px 60px rgba(0,0,0,.3); position:relative; }}
#add-modal h2 {{ font-size:1.1rem; font-weight:700; margin-bottom:1rem; }}
.modal-section {{ margin-bottom:1rem; }}
.modal-section h3 {{ font-size:0.78rem; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:.4rem; }}
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
.modal-actions {{ display:flex; gap:.5rem; justify-content:flex-end; margin-top:1rem; padding-top:1rem; border-top:1px solid var(--border); }}
.btn-primary {{ background:var(--accent); color:#fff; border:none; border-radius:6px; padding:.45rem 1.1rem; font-size:.85rem; font-weight:600; cursor:pointer; }}
.btn-primary:hover {{ opacity:.9; }}
.btn-secondary {{ background:var(--chip-bg); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:.45rem 1.1rem; font-size:.85rem; cursor:pointer; }}
.loading-dots::after {{ content:'.'; animation:dots 1.2s steps(3,end) infinite; }}
@keyframes dots {{ 0%,20%{{content:'.';}} 40%{{content:'..';}} 60%,100%{{content:'...';}} }}
#add-modal-close {{ position:absolute; top:.75rem; right:.75rem; background:none; border:none; font-size:1.2rem; cursor:pointer; color:var(--muted); line-height:1; }}

@media (max-width: 640px) {{
  #app {{ flex-direction: column; height: auto; }}
  #sidebar {{ width: 100%; max-height: 50vh; }}
  #main {{ overflow: visible; }}
}}
</style>
</head>
<body>
<div id="clipboard-toast"></div>
<!-- Add-author modal -->
<div id="add-modal-overlay">
  <div id="add-modal">
    <button id="add-modal-close" onclick="closeAddModal()" title="Bezárás">✕</button>
    <h2 id="modal-title">Új szerző hozzáadása</h2>

    <div class="modal-field">
      <label>Szerző neve</label>
      <div style="display:flex;gap:.4rem">
        <input type="text" id="m-name" placeholder="pl. Gábor Tardos" style="flex:1"
               onkeydown="if(event.key==='Enter') searchByName()">
        <button class="btn-secondary" onclick="searchByName()">🔍 Keresés</button>
      </div>
    </div>

    <div id="m-existing-hint" style="font-size:.8rem;margin-bottom:.6rem;min-height:1.2em"></div>

    <div class="modal-section">
      <h3>DBLP profil</h3>
      <div id="dblp-status" class="candidate-none">Adj meg nevet a kereséshez</div>
      <div id="dblp-list" class="candidate-list" style="display:none"></div>
    </div>

    <div class="modal-section">
      <h3>MTMT profil</h3>
      <div id="mtmt-status" class="candidate-none">Adj meg nevet a kereséshez</div>
      <div id="mtmt-list" class="candidate-list" style="display:none"></div>
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
      <label>Fénykép URL</label>
      <input type="text" id="m-mta-photo" placeholder="https://…">
    </div>
    <div class="modal-field">
      <label>PhD év</label>
      <input type="text" id="m-phd-year" placeholder="pl. 2012" style="width:8rem">
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
    <div id="m-slug-preview" style="font-size:.78rem;color:var(--muted);margin-top:.25rem"></div>

    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeAddModal()">Mégsem</button>
      <button class="btn-primary" onclick="saveAddModal()">💾 Mentés GitHubra →</button>
    </div>
  </div>
</div>

<div id="app">
  <div id="sidebar">
    <div id="sidebar-header">
      <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem">
        <h1 style="flex:1"><a href="index.html" style="color:inherit;text-decoration:none" title="Főoldal">Hungarian CS Authors</a></h1>
        <button onclick="openNewAuthorModal()" class="edit-btn" title="Új szerző hozzáadása">+ Új szerző</button>
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
    <div class="filter-row">
      <span class="chip active" data-group="age" data-val="">Karriér: mind</span>
      <span class="chip" data-group="age" data-val="no PhD">no PhD</span>
      <span class="chip" data-group="age" data-val="ERC Starting">Starting</span>
      <span class="chip" data-group="age" data-val="ERC Consolidator">Consolidator</span>
      <span class="chip" data-group="age" data-val="ERC Advanced">Advanced</span>
    </div>
    <div class="filter-row sort-row">
      <label for="sort-select">Sorrend:</label>
      <select id="sort-select">
        <option value="astar_equiv">Core A* eq.</option>
        <option value="astar">Core A*</option>
        <option value="name">Név</option>
      </select>
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
const ANON_COUNT = {anon_count_js};
const GITHUB_REPO   = "{GITHUB_REPO}";
const GITHUB_BRANCH = "{GITHUB_BRANCH}";

// Index by slug for fast hash-based routing
const BY_SLUG = {{}};
AUTHORS.forEach(a => BY_SLUG[a.slug] = a);

let filterCat = "", filterWorks = "", filterAge = "", sortBy = "astar_equiv", searchQ = "";
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
    return `<div class="mtmt-option" data-mtid="${{c.mtid}}" data-label="${{safeLabel}}"><strong>${{c.mtid}}</strong> — ${{safeLabel}}</div>`;
  }}).join("");
  container.innerHTML = `<div class="mtmt-results-label">Kattints a megfelelő szerzőre:</div>${{items}}`;
  container.querySelectorAll(".mtmt-option").forEach(el => {{
    el.addEventListener("click", () => selectMTMT(el.dataset.mtid, el.dataset.label, el));
  }});
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

function showToast(msg, duration) {{
  const t = document.getElementById("clipboard-toast");
  t.className = "";
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.style.display = "none", duration || 5000);
}}

function showSavePanel(json, ghUrl) {{
  const t = document.getElementById("clipboard-toast");
  t.className = "fallback";
  t.innerHTML = `
    <strong>1. Másold a JSON-t → 2. Nyisd meg a GitHub szerkesztőt → 3. Ctrl+A + Ctrl+V → 4. Commit</strong>
    <textarea readonly onclick="this.select()" style="height:160px">${{json}}</textarea>
    <div class="toast-actions">
      <button class="primary" id="copy-and-open-btn">📋 Másolás + GitHub megnyitása</button>
      <button onclick="this.closest('#clipboard-toast').style.display='none'">✕</button>
    </div>`;
  const btn = t.querySelector("#copy-and-open-btn");
  btn.addEventListener("click", async () => {{
    try {{
      await navigator.clipboard.writeText(json);
    }} catch {{
      // execCommand fallback: fresh focused textarea
      const copyTa = document.createElement("textarea");
      copyTa.value = json;
      copyTa.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;opacity:0.01";
      document.body.appendChild(copyTa);
      copyTa.focus();
      copyTa.select();
      document.execCommand("copy");
      document.body.removeChild(copyTa);
    }}
    btn.textContent = "✓ Másolva!";
    setTimeout(() => window.open(ghUrl, "_blank"), 150);
  }});
  t.style.display = "block";
  clearTimeout(t._timer);
  // auto-select so user can Ctrl+C manually too
  setTimeout(() => t.querySelector("textarea").select(), 50);
}}

// Fields computed by scripts — never write back to profile JSON
const COMPUTED_FIELDS = new Set([
  "core_astar","core_a","core_b","core_c","no_core",
  "core_astar_equiv","hungarian_core_astar_equiv","first_author_core_astar_equiv",
  "years_since_phd","phd_year_source",
  "hung_astar_rank","hung_astar_total","category_astar_rank","age_astar_rank",
  "_has_profile","_github_edit_url",
]);

function saveEdits() {{
  const tbl = document.getElementById("edit-kv-table");
  if (!tbl) return;
  const slug = tbl.dataset.slug;
  const hasProfile = tbl.dataset.hasProfile === "1";
  const editUrl = tbl.dataset.editUrl;

  if (hasProfile) {{
    // Build base from in-memory AUTHORS data (no async fetch needed)
    const base = BY_SLUG[slug] || {{}};
    const merged = {{}};
    for (const [k, v] of Object.entries(base)) {{
      if (!COMPUTED_FIELDS.has(k)) merged[k] = v;
    }}

    // Apply edits from the form fields
    document.querySelectorAll("[data-edit]").forEach(el => {{
      const v = el.value.trim();
      const k = el.dataset.edit;
      if (v === "" || v === "-") {{
        delete merged[k];
      }} else {{
        merged[k] = (k === "phd_year" && /^\d+$/.test(v)) ? parseInt(v, 10) : v;
      }}
    }});

    // Compute age_group client-side so the saved profile is immediately correct
    const ADVANCED_DEGREES = ["kandidátus","levelező tag","rendes tag","tudomány doktora","MTA doktora"];
    const deg = base.degree || "";
    if (ADVANCED_DEGREES.some(d => deg.startsWith(d))) {{
      merged.age_group = "ERC Advanced";
    }} else if (merged.phd_year) {{
      const yrs = new Date().getFullYear() - merged.phd_year;
      if (yrs <= 7) merged.age_group = "ERC Starting";
      else if (yrs <= 12) merged.age_group = "ERC Consolidator";
      else merged.age_group = "ERC Advanced";
    }} else {{
      delete merged.age_group;
    }}

    const json = JSON.stringify(merged, null, 2);
    showSavePanel(json, editUrl);
  }} else {{
    // New profile: build minimal JSON and open GitHub new-file form
    const obj = {{}};
    document.querySelectorAll("[data-edit]").forEach(el => {{
      const v = el.value.trim();
      if (v && v !== "-") obj[el.dataset.edit] = v;
    }});
    const json = JSON.stringify(obj, null, 2);
    const encoded = encodeURIComponent(json);
    const url = `https://github.com/${{GITHUB_REPO}}/new/${{GITHUB_BRANCH}}?filename=profiles/${{slug}}.json&value=${{encoded}}`;
    window.open(url, "_blank");
    showToast("GitHub lap megnyílt — töltsd ki és commitold!", 4000);
  }}
}}

function stripAccents(s) {{
  return (s||"").normalize("NFD").replace(/[\\u0300-\\u036f]/g,"").toLowerCase();
}}

function renderList() {{
  const q = stripAccents(searchQ);
  const filtered = AUTHORS.filter(a => {{
    if (filterCat && a.category !== filterCat) return false;
    if (filterWorks) {{
      const w = (a.works || "").toLowerCase();
      if (filterWorks === "abroad" && !w.includes("abroad")) return false;
      if (filterWorks === "hungary" && w.includes("abroad")) return false;
    }}
    if (filterAge) {{
      if ((a.age_group || "") !== filterAge) return false;
    }}
    if (q) {{
      const hay = stripAccents((a.name||"")+" "+(a.affiliations||"")+" "+(a.mtmt_affiliations||"")+" "+(a.dblp_institutions||""));
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

  const sorted = [...filtered].sort((a, b) => {{
    if (sortBy === "name") return (a.name||"").localeCompare(b.name||"", "hu");
    if (sortBy === "astar") return (b.core_astar||0) - (a.core_astar||0);
    return (b.core_astar_equiv||0) - (a.core_astar_equiv||0);
  }});

  const anonNote = (q && ANON_COUNT > 0) ? ` + ${{ANON_COUNT}} anonymized` : "";
  document.getElementById("list-count").textContent = sorted.length + " / " + AUTHORS.length + " author" + anonNote;

  const el = document.getElementById("author-list");
  el.innerHTML = sorted.map(a => {{
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

  const astarUrl = `core_papers.html?author=${{a.slug}}&tier=astar&nat=összes&name=${{encodeURIComponent(a.name.replace(/\\s+\\d{{4}}$/,""))}}`;
  const bothUrl  = `core_papers.html?author=${{a.slug}}&tier=both&sort=tier&nat=összes&name=${{encodeURIComponent(a.name.replace(/\\s+\\d{{4}}$/,""))}}`;
  const aUrl     = `core_papers.html?author=${{a.slug}}&tier=a&nat=összes&name=${{encodeURIComponent(a.name.replace(/\\s+\\d{{4}}$/,""))}}`;
  const cleanName     = (a.name || "").replace(/\\s+\\d{{4}}$/, "").trim();
  const hungTableUrl  = a.works === "hungary" ? `authors_table.html?munkahely=hungary&highlight=${{encodeURIComponent(cleanName)}}` : "";
  const catTableUrl   = a.works === "hungary" && a.category ? `authors_table.html?munkahely=hungary&tema=${{encodeURIComponent(a.category)}}&highlight=${{encodeURIComponent(cleanName)}}` : "";
  const ageTableUrl   = a.works === "hungary" && a.age_group ? `authors_table.html?munkahely=hungary&karrier=${{encodeURIComponent(a.age_group)}}&highlight=${{encodeURIComponent(cleanName)}}` : "";
  const hungRankStr   = a.hung_astar_rank != null ? `${{a.hung_astar_rank}}/${{a.hung_astar_total}}` : null;
  const dblpSrc   = null;
  const mtmtSrc   = null;
  const calcSrc   = null;
  const oaSrc     = a.openalex_id ? ["OpenAlex", `https://openalex.org/authors/${{a.openalex_id}}`] : null;
  const statsData = [
    ["Core A*",        a.core_astar,                    0,    a.core_astar > 0 ? astarUrl : "", dblpSrc],
    ["Core A* eq.",    a.core_astar_equiv,              2,    a.core_astar_equiv > 0 ? bothUrl : "",  calcSrc],
    ["1st Author eq.", a.first_author_core_astar_equiv, 2,    a.first_author_core_astar_equiv > 0 ? bothUrl : "",  calcSrc],
    ["HU eq.",         a.hungarian_core_astar_equiv,    2,    a.hungarian_core_astar_equiv > 0 ? bothUrl : "",  calcSrc],
    ["Core A",         a.core_a,                        0, a.core_a > 0 ? aUrl : "",            dblpSrc],
    ["MTMT idézet",    a.mtmt_citations,                0, "", mtmtSrc],
    ["D1 eq.",         a.mtmt_d1_equiv,                 1, "", mtmtSrc],
    ["OA idézet",      a.openalex_cited_by_count,       0, "", oaSrc],
    ["OA h-index",     a.openalex_h_index,              0, "", oaSrc],
    ["OA 2yr idézet",  a.openalex_2yr_cited_by_count,   0, "", oaSrc],
    ["Magyar rang",    hungRankStr,                     null, hungTableUrl, calcSrc],
    ["Kat. rang",      a.category_astar_rank,           0,    catTableUrl,  calcSrc],
    ["Életkor rang",   a.age_astar_rank,                0,    ageTableUrl,  calcSrc],
  ].filter(([,v]) => v != null && v !== 0);

  let stats;
  if (a._anon) {{
    stats = `<div class="section">
    <h3>Metrics</h3>
    <p style="color:var(--muted);font-style:italic;margin:0.5rem 0">
      A szerző kérésére a metrikák rejtve.
      <a href="${{bothUrl}}" style="margin-left:0.5rem">Cikkek megtekintése →</a>
    </p>
  </div>`;
  }} else {{
    stats = statsData.length ? `<div class="section">
    <h3>Metrics</h3>
    <div class="stats-grid">
      ${{statsData.map(([lbl, v, fmt_, url, src]) => {{
        const valStr = typeof v === "number" && fmt_ != null ? v.toFixed(fmt_) : fmt(v);
        // When card is itself a link, source badge must not be a nested <a> (invalid HTML).
        // Use a span with onclick+stopPropagation instead.
        let srcHtml = "";
        if (src) {{
          if (!src[1]) {{
            srcHtml = `<div class="src">${{src[0]}}</div>`;
          }} else if (url) {{
            srcHtml = `<div class="src"><span class="src-link" onclick="event.preventDefault();event.stopPropagation();window.open('${{src[1]}}','_blank')">${{src[0]}}</span></div>`;
          }} else {{
            srcHtml = `<div class="src"><a href="${{src[1]}}" target="_blank" rel="noopener">${{src[0]}}</a></div>`;
          }}
        }}
        const inner  = `<div class="val">${{valStr}}</div><div class="lbl">${{lbl}}</div>${{srcHtml}}`;
        return url
          ? `<a class="stat-card stat-link" href="${{url}}" title="${{lbl}} cikkek listája">${{inner}}</a>`
          : `<div class="stat-card">${{inner}}</div>`;
      }}).join("")}}
    </div>
  </div>` : "";
  }}

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
    {{key:"phd_year",    label:"PhD éve",        type:"text"}},
  ];
  const editRows = EDIT_FIELDS.map(f => {{
    const raw = a[f.key];
    const val = (raw === null || raw === undefined || raw === "-") ? "" : String(raw);
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

  const topicsHtml = (() => {{
    const topics = a.openalex_topics;
    if (!topics || !topics.length) return "";
    // Group by field
    const byField = {{}};
    for (const t of topics) {{
      const fn = t.field ? t.field.name : "Egyéb";
      if (!byField[fn]) byField[fn] = [];
      byField[fn].push(t);
    }}
    const rows = Object.entries(byField).map(([field, ts]) => {{
      const chips = ts.map(t => {{
        const url = `https://openalex.org/topics/${{t.id}}`;
        return `<a class="topic-chip" href="${{url}}" target="_blank" rel="noopener" title="${{esc(t.subfield ? t.subfield.name : "")}}">
          ${{esc(t.name)}}<span class="tc-count">${{t.count}}</span>
        </a>`;
      }}).join("");
      return `<div style="margin-bottom:0.5rem">
        <div style="font-size:0.68rem;color:var(--muted);margin-bottom:0.2rem">${{esc(field)}}</div>
        <div class="topic-chips">${{chips}}</div>
      </div>`;
    }}).join("");
    return `<div class="topics-section">
      <h4>OpenAlex kutatási területek</h4>
      ${{rows}}
    </div>`;
  }})();

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
    ${{topicsHtml}}
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
    if (group === "age") filterAge = chip.dataset.val;
    renderList();
  }});
}});

document.getElementById("search").addEventListener("input", e => {{
  searchQ = e.target.value.trim();
  renderList();
}});

document.getElementById("sort-select").addEventListener("change", e => {{
  sortBy = e.target.value;
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

// ── Add-author modal ──────────────────────────────────────────────────────────

let _modalName = "", _modalSlug = "", _modalDblpName = "";

function openNewAuthorModal() {{
  _modalName = ""; _modalSlug = ""; _modalDblpName = "";
  document.getElementById("modal-title").textContent = "Új szerző hozzáadása";
  document.getElementById("m-name").value = "";
  ["m-dblp-url","m-mtmt-id","m-mtmt-name","m-mta-att-id","m-affiliations","m-homepage","m-linkedin","m-note","m-phd-year","m-mta-photo"].forEach(id => {{
    document.getElementById(id).value = "";
  }});
  document.getElementById("m-category").value = "";
  document.getElementById("m-works").value = "";
  document.getElementById("dblp-list").style.display = "none";
  document.getElementById("mtmt-list").style.display = "none";
  document.getElementById("dblp-status").textContent = "Adj meg nevet a kereséshez";
  document.getElementById("dblp-status").style.display = "";
  document.getElementById("mtmt-status").textContent = "Adj meg nevet a kereséshez";
  document.getElementById("mtmt-status").style.display = "";
  document.getElementById("m-linkedin-hint").innerHTML = "";
  document.getElementById("m-existing-hint").innerHTML = "";
  document.getElementById("m-slug-preview").textContent = "";
  document.getElementById("add-modal-overlay").classList.add("open");
  setTimeout(() => document.getElementById("m-name").focus(), 50);
}}

function closeAddModal() {{
  document.getElementById("add-modal-overlay").classList.remove("open");
}}

function searchByName() {{
  const name = document.getElementById("m-name").value.trim();
  if (!name) return;
  _modalName = name;
  _modalDblpName = "";
  _modalSlug = slugifyJS(name);
  document.getElementById("m-slug-preview").textContent = "";
  document.getElementById("dblp-list").innerHTML = "";
  document.getElementById("dblp-list").style.display = "none";
  document.getElementById("dblp-status").className = "candidate-none loading-dots";
  document.getElementById("dblp-status").textContent = "Keresés";
  document.getElementById("dblp-status").style.display = "";
  document.getElementById("mtmt-list").innerHTML = "";
  document.getElementById("mtmt-list").style.display = "none";
  document.getElementById("mtmt-status").className = "candidate-none loading-dots";
  document.getElementById("mtmt-status").textContent = "Keresés";
  document.getElementById("mtmt-status").style.display = "";
  document.getElementById("m-linkedin-hint").innerHTML =
    '<a href="https://www.linkedin.com/search/results/people/?keywords=' + encodeURIComponent(name) + '" target="_blank" rel="noopener">🔍 Keresés LinkedIn-en →</a>';
  checkExistingAuthors(name);
  searchDblp(name);
  searchMtmt(name);
}}

function normalize(s) {{
  return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"");
}}

function checkExistingAuthors(name) {{
  const q = normalize(name);
  const qTokens = q.split(/\s+/).filter(t => t.length >= 3);
  const matches = AUTHORS.filter(a => {{
    const n = normalize(a.name);
    const nTokens = n.split(/\s+/);
    // name contains the full query, or any query token is a full token of the name
    if (n.includes(q)) return true;
    return qTokens.some(qt => nTokens.some(nt => nt === qt || (qt.length >= 5 && nt.startsWith(qt))));
  }});
  const el = document.getElementById("m-existing-hint");
  if (!matches.length) {{ el.innerHTML = ""; return; }}
  el.innerHTML = '<span style="color:#b45309;font-weight:600">⚠️ Már szerepel az adatbázisban:</span> '
    + matches.slice(0,8).map(a =>
        `<a href="#${{a.slug}}" onclick="closeAddModal()" style="color:var(--accent)">${{a.name}}</a>`
      ).join(", ");
}}

function slugifyJS(name) {{
  return name.toLowerCase()
    .normalize("NFD").replace(/[\\u0300-\\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}}

async function dblpFetch(name) {{
  // sparql.dblp.org has CORS headers; direct fetch and proxies do not
  const safe = name.replace(/['"\\\\]/g, " ");
  const sparql = [
    "PREFIX dblp: <https://dblp.org/rdf/schema#>",
    "SELECT DISTINCT ?person ?name WHERE {{",
    "  ?person a dblp:Person ; dblp:primaryCreatorName ?name .",
    '  FILTER(CONTAINS(LCASE(STR(?name)), LCASE("' + safe + '")))',
    "}} LIMIT 20"
  ].join("\\n");
  const r = await fetch("https://sparql.dblp.org/sparql", {{
    method: "POST",
    headers: {{
      "Accept": "application/sparql-results+json",
      "Content-Type": "application/x-www-form-urlencoded"
    }},
    body: "query=" + encodeURIComponent(sparql)
  }});
  if (!r.ok) throw new Error("SPARQL " + r.status);
  const data = await r.json();
  const bindings = data?.results?.bindings || [];
  return {{
    result: {{
      hits: {{
        hit: bindings.map(b => ({{
          info: {{
            author: b.name?.value || "",
            url: (b.person?.value || "").replace("https://dblp.org/", "")
          }}
        }}))
      }}
    }}
  }};
}}

async function searchDblp(name) {{
  const statusEl = document.getElementById("dblp-status");
  const listEl = document.getElementById("dblp-list");
  try {{
    const data = await dblpFetch(name);
    const hits = data?.result?.hits?.hit || [];
    statusEl.style.display = "none";
    statusEl.className = "candidate-none";
    if (!hits.length) {{
      statusEl.innerHTML = 'Nem található DBLP-n &mdash; <a href="https://dblp.org/search?q=' + encodeURIComponent(name) + '" target="_blank" rel="noopener">Keresés DBLP-n →</a>';
      statusEl.style.display = "";
      return;
    }}
    listEl.innerHTML = hits.map(h => {{
      const info = h.info || {{}};
      const authorName = info.author || "";
      const pid = info.url || "";
      const dblpUrl = pid ? "https://dblp.org/pid/" + pid.replace(/^.*pid\\//,"") : "";
      const slug = slugifyJS(authorName);
      return `<div class="candidate" onclick="selectDblp(${{JSON.stringify(dblpUrl)}}, ${{JSON.stringify(authorName)}}, this)">
        <span>🔗</span>
        <span><strong>${{authorName}}</strong> <span style="color:var(--muted);font-size:.72rem">→ ${{slug}}.json</span></span>
        ${{dblpUrl ? '<a href="' + dblpUrl + '" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="margin-left:auto;font-size:.75rem;color:var(--accent)">DBLP →</a>' : ''}}
      </div>`;
    }}).join("");
    listEl.style.display = "flex";
    // Auto-select if exactly one result
    if (hits.length === 1) {{
      const first = listEl.querySelector(".candidate");
      if (first) first.click();
    }}
  }} catch(e) {{
    statusEl.className = "candidate-none";
    statusEl.innerHTML = 'DBLP keresés sikertelen &mdash; <a href="https://dblp.org/search?q=' + encodeURIComponent(document.getElementById("m-name").value.trim()) + '" target="_blank" rel="noopener">Keresés DBLP-n →</a>';
    statusEl.style.display = "";
  }}
}}

function selectDblp(url, name, el) {{
  document.getElementById("m-dblp-url").value = url;
  document.getElementById("m-name").value = name;
  document.querySelectorAll("#dblp-list .candidate").forEach(c => c.classList.remove("selected"));
  el.classList.add("selected");
  _modalDblpName = name;
  _modalSlug = slugifyJS(name);
  document.getElementById("m-slug-preview").textContent = "Fájlnév: profiles/" + _modalSlug + ".json";
  checkExistingAuthors(name);
}}

const _existingMtmtIds = new Set(AUTHORS.map(a => String(a.mtmt_id || "")).filter(Boolean));

async function searchMtmt(name) {{
  const statusEl = document.getElementById("mtmt-status");
  const listEl = document.getElementById("mtmt-list");
  const parts = name.trim().split(/\\s+/);
  const families = [...new Set([parts[parts.length-1], parts[0]])];
  const seen = new Map();
  for (const fam of families) {{
    try {{
      const url = "https://m2.mtmt.hu/api/author?cond=familyName;eq;" + encodeURIComponent(fam) + "&format=json&size=20";
      const resp = await fetch(url);
      const data = await resp.json();
      for (const c of (data.content || [])) {{
        if (c.mtid && !seen.has(c.mtid)) seen.set(c.mtid, c.label || "");
      }}
    }} catch(e) {{}}
  }}
  // Filter out already-known authors
  for (const mtid of seen.keys()) {{
    if (_existingMtmtIds.has(String(mtid))) seen.delete(mtid);
  }}
  statusEl.style.display = "none";
  statusEl.className = "candidate-none";
  if (!seen.size) {{
    statusEl.textContent = "Nem található MTMT-n (vagy már az adatbázisban van)";
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
  const mtid = +el.dataset.mtid;
  const label = el.dataset.label;
  document.getElementById("m-mtmt-id").value = mtid;
  document.getElementById("m-mtmt-name").value = label;
  document.querySelectorAll("#mtmt-list .candidate").forEach(c => c.classList.remove("selected"));
  el.classList.add("selected");
  enrichFromMtmt(mtid, label);
}}

const HU_INST = {{
  "BME": "BME", "Budapest University of Technology": "BME",
  "ELTE": "ELTE", "Eötvös": "ELTE",
  "SZTE": "SZTE", "Szegedi": "SZTE",
  "Rényi": "Rényi", "RAMKI": "Rényi",
  "SZTAKI": "SZTAKI", "HUN-REN": "SZTAKI",
  "Ericsson": "Ericsson", "Corvinus": "Corvinus",
  "PPKE": "PPKE", "Pázmány": "PPKE",
  "Debrecen": "DE", "Pécsi": "PTE",
}};
const THEORY_KW = ["Matematika","Számítástudomány","Kombinatorika","Elmélet","Algebra","Mathematics","Combinatorics","Theory","Logic"];
const APPLIED_KW = ["Villamosmérnöki","Informatika","Hálózat","Távközlés","Electrical","Network","Computer Engineering"];

function instAbbr(label) {{
  for (const [kw, abbr] of Object.entries(HU_INST)) {{
    if (label.includes(kw)) return abbr;
  }}
  return null;
}}

function parseAffLabel(label) {{
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
    const affs = (c.affiliations || []).map(a => parseAffLabel(a.label || "")).filter(Boolean);
    const seen = new Set();
    const unique = affs.filter(a => {{ const k = a.replace(/\\d{{4}}.*/, "").trim(); return seen.has(k) ? false : seen.add(k); }});
    if (unique.length && !document.getElementById("m-affiliations").value.trim())
      document.getElementById("m-affiliations").value = unique.join("; ");
    if (!document.getElementById("m-works").value) {{
      const isHu = affs.some(a => Object.values(HU_INST).some(abbr => a.startsWith(abbr)));
      if (isHu) document.getElementById("m-works").value = "hungary";
    }}
    if (!document.getElementById("m-category").value) {{
      const disc = (label.match(/\\(([^)]+)\\)/) || [])[1] || "";
      if (THEORY_KW.some(k => disc.includes(k))) document.getElementById("m-category").value = "theory";
      else if (APPLIED_KW.some(k => disc.includes(k))) document.getElementById("m-category").value = "applied";
    }}
  }} catch(e) {{}}
}}

function saveAddModal() {{
  const typedName = document.getElementById("m-name").value.trim() || _modalName;
  const name = _modalDblpName || typedName;
  if (!name) {{ alert("Add meg a szerző nevét!"); return; }}
  const slug = slugifyJS(name);
  const obj = {{ name, slug }};
  const fields = {{
    dblp_url: "m-dblp-url", mtmt_id: "m-mtmt-id", mtmt_name: "m-mtmt-name",
    mta_att_id: "m-mta-att-id", category: "m-category", works: "m-works",
    affiliations: "m-affiliations", homepage: "m-homepage", linkedin: "m-linkedin",
    note: "m-note", phd_year: "m-phd-year", mta_photo: "m-mta-photo"
  }};
  for (const [key, id] of Object.entries(fields)) {{
    const v = document.getElementById(id).value.trim();
    if (v) obj[key] = key === "phd_year" ? parseInt(v) || v : v;
  }}
  const json = JSON.stringify(obj, null, 2);
  const encoded = encodeURIComponent(json);
  const url = `https://github.com/${{GITHUB_REPO}}/new/${{GITHUB_BRANCH}}?filename=profiles/${{slug}}.json&value=${{encoded}}`;
  window.open(url, "_blank");
  closeAddModal();
}}

document.getElementById("add-modal-overlay").addEventListener("click", function(e) {{
  if (e.target === this) closeAddModal();
}});
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
            "openalex_cited_by_count", "openalex_h_index", "openalex_2yr_cited_by_count",
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

    anon_slugs = load_anon_slugs()
    ignore_slugs = load_ignore_slugs()
    html = generate(merged, anon_slugs=anon_slugs, ignore_slugs=ignore_slugs)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"Generated {OUT_FILE} with {len(merged)} authors ({len(profiles)} profiles, {len(new_authors)} new, {len(anon_slugs)} anon, {len(ignore_slugs)} ignored)")


if __name__ == "__main__":
    main()
