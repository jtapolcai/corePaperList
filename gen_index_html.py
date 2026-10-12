#!/usr/bin/env python3
"""Generate index.html — dashboard for the Hungarian CS Research Database."""
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parent
AUTHORS_JSON = BASE / "authors.json"
PROFILES_DIR = BASE / "profiles"
OUT = BASE / "index.html"

WORKS_LABEL = {
    "hungary": "Magyar intézmény",
    "company_hungary": "Magyar cég",
    "abroad": "Külföldi intézmény",
    "company_abroad": "Külföldi cég",
    "inactive": "Inaktív",
    "retired": "Nyugdíjas",
    "unknown": "Ismeretlen",
}

AGE_ORDER = ["0-5 év", "5-10 év", "10-20 év", "20+ év", "25+ év", "unknown"]


def load() -> list:
    return json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))


def profile_count() -> int:
    return len([f for f in PROFILES_DIR.glob("*.json") if not f.stem.startswith("_")])


def compute_stats(authors: list) -> dict:
    total = len(authors)
    hungary = sum(1 for a in authors if (a.get("works") or "") in ("hungary", "company_hungary"))
    abroad = sum(1 for a in authors if (a.get("works") or "") in ("abroad", "company_abroad"))
    theory = sum(1 for a in authors if a.get("category") == "theory")
    applied = sum(1 for a in authors if a.get("category") == "applied")

    astar_coauth = sum(a.get("core_astar", 0) or 0 for a in authors)
    astar_papers = sum(a.get("core_astar_papers", 0) or 0 for a in authors)
    hun_astar_eq = sum(a.get("hungarian_core_astar_equiv", 0) or 0 for a in authors)

    mtmt_cit = sum(a.get("mtmt_citations", 0) or 0 for a in authors)

    works_counter = Counter(a.get("works") or "unknown" for a in authors)
    age_counter = Counter(a.get("age_group") or "unknown" for a in authors)
    cat_counter = Counter(a.get("category") or "unknown" for a in authors)

    top_astar = sorted(
        [a for a in authors if (a.get("core_astar") or 0) > 0],
        key=lambda a: a.get("core_astar", 0) or 0,
        reverse=True,
    )[:15]

    return {
        "total": total,
        "hungary": hungary,
        "abroad": abroad,
        "theory": theory,
        "applied": applied,
        "astar_coauth": astar_coauth,
        "astar_papers": astar_papers,
        "hun_astar_eq": hun_astar_eq,
        "mtmt_cit": mtmt_cit,
        "works_counter": dict(works_counter),
        "age_counter": dict(age_counter),
        "cat_counter": dict(cat_counter),
        "top_astar": top_astar,
        "profiles": profile_count(),
    }


def works_rows(works_counter: dict) -> str:
    rows = []
    for key in ["hungary", "company_hungary", "abroad", "company_abroad", "inactive", "retired", "unknown"]:
        n = works_counter.get(key, 0)
        label = WORKS_LABEL.get(key, key)
        rows.append(f"<tr><td>{label}</td><td class='num'>{n}</td></tr>")
    return "\n".join(rows)


def age_rows(age_counter: dict) -> str:
    rows = []
    for key in AGE_ORDER:
        n = age_counter.get(key, 0)
        if n == 0:
            continue
        label = key if key != "unknown" else "Ismeretlen"
        rows.append(f"<tr><td>{key}</td><td class='num'>{n}</td></tr>")
    return "\n".join(rows)


def top_rows(top: list) -> str:
    rows = []
    for i, a in enumerate(top, 1):
        name = a.get("name", "")
        slug = a.get("slug", "")
        astar = a.get("core_astar", 0) or 0
        works = a.get("works", "") or ""
        cat = a.get("category", "") or ""
        cat_badge = (
            '<span class="badge theory">Elmélet</span>'
            if cat == "theory"
            else '<span class="badge applied">Alkalmazott</span>'
            if cat == "applied"
            else ""
        )
        loc = "🇭🇺" if works in ("hungary", "company_hungary") else "🌍" if works in ("abroad", "company_abroad") else ""
        profile_link = (
            f'<a href="authors_profile.html#{slug}">{name}</a>'
            if slug
            else name
        )
        rows.append(
            f"<tr><td class='rank'>{i}.</td><td>{loc} {profile_link}</td>"
            f"<td>{cat_badge}</td><td class='num'>{astar}</td></tr>"
        )
    return "\n".join(rows)


def render(s: dict) -> str:
    hun_pct = round(100 * s["hungary"] / s["total"]) if s["total"] else 0
    ab_pct = round(100 * s["abroad"] / s["total"]) if s["total"] else 0

    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Magyar CS Kutatók – Áttekintő</title>
<style>
  :root {{
    --bg: #f8f9fa;
    --card: #fff;
    --border: #dee2e6;
    --accent: #0d6efd;
    --accent2: #198754;
    --accent3: #dc3545;
    --text: #212529;
    --muted: #6c757d;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
  header {{
    background: linear-gradient(135deg, #1a3a5c 0%, #0d6efd 100%);
    color: #fff; padding: 2rem 1rem; text-align: center;
  }}
  header h1 {{ font-size: 1.8rem; margin-bottom: 0.25rem; }}
  header p {{ opacity: 0.85; font-size: 0.95rem; }}

  main {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}

  /* Nav cards */
  .nav-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .nav-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem;
    padding: 1.25rem; text-decoration: none; color: var(--text);
    transition: box-shadow 0.15s, transform 0.15s;
    display: flex; flex-direction: column; gap: 0.35rem;
  }}
  .nav-card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,0.12); transform: translateY(-2px); text-decoration: none; }}
  .nav-card .icon {{ font-size: 2rem; }}
  .nav-card .title {{ font-weight: 600; font-size: 1rem; color: var(--accent); }}
  .nav-card .desc {{ font-size: 0.85rem; color: var(--muted); }}

  /* Stat cards */
  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .stat-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem;
    padding: 1rem; text-align: center;
  }}
  .stat-card .val {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
  .stat-card .val.green {{ color: var(--accent2); }}
  .stat-card .val.red {{ color: var(--accent3); }}
  .stat-card .lbl {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.15rem; }}

  /* Sections */
  .section-title {{ font-size: 1.1rem; font-weight: 600; margin: 1.75rem 0 0.75rem; border-bottom: 2px solid var(--border); padding-bottom: 0.35rem; }}

  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }}
  @media (max-width: 640px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

  table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem; overflow: hidden; }}
  th {{ background: #f1f3f5; font-weight: 600; font-size: 0.85rem; padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
  td {{ padding: 0.45rem 0.75rem; border-bottom: 1px solid var(--border); font-size: 0.875rem; }}
  tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .rank {{ color: var(--muted); width: 2rem; }}

  .badge {{ display: inline-block; padding: 0.1em 0.5em; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; }}
  .badge.theory {{ background: #cfe2ff; color: #084298; }}
  .badge.applied {{ background: #d1e7dd; color: #0a3622; }}

  /* Progress bar */
  .bar-wrap {{ background: #e9ecef; border-radius: 0.25rem; height: 0.6rem; margin-top: 0.3rem; }}
  .bar {{ height: 100%; border-radius: 0.25rem; background: var(--accent); }}

  footer {{ text-align: center; font-size: 0.78rem; color: var(--muted); padding: 1rem; }}
</style>
</head>
<body>

<header>
  <h1>Magyar Számítástudományi Kutatók</h1>
  <p>CORE A* &amp; CORE A minősítésű publikációkkal rendelkező kutatók adatbázisa</p>
</header>

<main>

  <!-- Navigation -->
  <div class="nav-cards">
    <a class="nav-card" href="authors_profile.html">
      <span class="icon">👤</span>
      <span class="title">Kutatói profilok</span>
      <span class="desc">Részletes adatlapok, szerkesztési lehetőséggel</span>
    </a>
    <a class="nav-card" href="core_astar.html">
      <span class="icon">⭐</span>
      <span class="title">CORE A* cikkek</span>
      <span class="desc">Magyar szerzős legrangosabb konferencia-cikkek</span>
    </a>
    <a class="nav-card" href="authors_table.html">
      <span class="icon">📊</span>
      <span class="title">Összehasonlító táblázat</span>
      <span class="desc">Szűrhető, rendezhető kutatói összehasonlítás</span>
    </a>
  </div>

  <!-- Key stats -->
  <div class="section-title">Kulcsmutatók</div>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="val">{s["total"]}</div>
      <div class="lbl">Nyilvántartott kutató</div>
    </div>
    <div class="stat-card">
      <div class="val green">{s["hungary"]}</div>
      <div class="lbl">Magyarországon dolgozik<br>({hun_pct}%)</div>
    </div>
    <div class="stat-card">
      <div class="val red">{s["abroad"]}</div>
      <div class="lbl">Külföldön dolgozik<br>({ab_pct}%)</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["astar_papers"]}</div>
      <div class="lbl">CORE A* cikk<br>(összes egyedi)</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["astar_coauth"]}</div>
      <div class="lbl">CORE A* szerzőség<br>(szerző × cikk)</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["hun_astar_eq"]:.0f}</div>
      <div class="lbl">Magyar CORE A* ekvivalens<br>(súlyozott)</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["theory"]}</div>
      <div class="lbl">Elméleti informatikus</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["applied"]}</div>
      <div class="lbl">Alkalmazott informatikus</div>
    </div>
  </div>

  <!-- Distribution tables -->
  <div class="section-title">Eloszlások</div>
  <div class="two-col">
    <div>
      <table>
        <thead><tr><th>Munkahely</th><th class="num">Fő</th></tr></thead>
        <tbody>{works_rows(s["works_counter"])}</tbody>
      </table>
    </div>
    <div>
      <table>
        <thead><tr><th>PhD óta eltelt idő</th><th class="num">Fő</th></tr></thead>
        <tbody>{age_rows(s["age_counter"])}</tbody>
      </table>
    </div>
  </div>

  <!-- Top researchers -->
  <div class="section-title">Top 15 kutató CORE A* szerzőségek szerint</div>
  <table>
    <thead>
      <tr>
        <th></th>
        <th>Kutató</th>
        <th>Kategória</th>
        <th class="num">CORE A*</th>
      </tr>
    </thead>
    <tbody>{top_rows(s["top_astar"])}</tbody>
  </table>

</main>

<footer>Adatok forrása: DBLP, MTMT, MTA • Automatikusan generálva</footer>

</body>
</html>"""


def main():
    authors = load()
    stats = compute_stats(authors)
    html = render(stats)
    OUT.write_text(html, encoding="utf-8")
    print(f"Generated {OUT}")


if __name__ == "__main__":
    main()
