#!/usr/bin/env python3
"""Generate index.html — dashboard for the Hungarian CS Research Database."""
import datetime
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).parent
AUTHORS_JSON = BASE / "authors.json"
PROFILES_DIR = BASE / "profiles"
HUN_PAPERS = BASE / "results" / "hungarian_papers_coreAstar.json"
ABR_PAPERS = BASE / "results" / "already_abroad_papers_coreAstar.json"
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

AGE_ORDER = ["ERC Starting", "ERC Consolidator", "ERC Advanced", "unknown"]
AGE_LABEL = {
    "ERC Starting": "ERC Starting (≤7 év PhD után)",
    "ERC Consolidator": "ERC Consolidator (7–12 év)",
    "ERC Advanced": "ERC Advanced (12+ év)",
    "unknown": "Ismeretlen",
}


def load_authors() -> list:
    return json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))


def load_papers() -> tuple[dict, dict]:
    hun = json.loads(HUN_PAPERS.read_text(encoding="utf-8")) if HUN_PAPERS.exists() else {}
    abr = json.loads(ABR_PAPERS.read_text(encoding="utf-8")) if ABR_PAPERS.exists() else {}
    return hun, abr


def profile_count() -> int:
    return len([f for f in PROFILES_DIR.glob("*.json") if not f.stem.startswith("_")])


def load_photo_map() -> dict[str, str]:
    """Return {slug: photo_url} from cache + per-profile overrides."""
    photo_map: dict[str, str] = {}
    cache_file = PROFILES_DIR / "_mta_photos.json"
    if cache_file.exists():
        try:
            for slug, url in json.loads(cache_file.read_text(encoding="utf-8")).items():
                if url:
                    photo_map[slug] = url
        except Exception:
            pass
    # per-profile overrides (mta_photo field)
    for f in PROFILES_DIR.glob("*.json"):
        if f.stem.startswith("_"):
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            url = p.get("mta_photo") or ""
            if url:
                photo_map[f.stem] = url
        except Exception:
            pass
    return photo_map


def paper_category(paper: dict, name_cat: dict) -> str:
    cats = {name_cat.get(n[0] if isinstance(n, list) else n, "unknown") for n in paper.get("authors", [])}
    cats.discard("unknown")
    if not cats:
        return "unknown"
    if len(cats) == 1:
        return cats.pop()
    return "theory"  # mixed: theory wins (matches paper classification logic)


def build_chart_data(hun: dict, abr: dict, name_cat: dict) -> dict:
    hun_theory: dict[int, int] = defaultdict(int)
    hun_applied: dict[int, int] = defaultdict(int)
    all_theory: dict[int, int] = defaultdict(int)
    all_applied: dict[int, int] = defaultdict(int)

    all_papers: dict = {}
    all_papers.update(hun)
    all_papers.update(abr)

    for p in hun.values():
        yr = int(p["year"])
        cat = paper_category(p, name_cat)
        if cat == "theory":
            hun_theory[yr] += 1
        elif cat == "applied":
            hun_applied[yr] += 1

    for p in all_papers.values():
        yr = int(p["year"])
        cat = paper_category(p, name_cat)
        if cat == "theory":
            all_theory[yr] += 1
        elif cat == "applied":
            all_applied[yr] += 1

    years = sorted(
        set(list(hun_theory) + list(hun_applied) + list(all_theory) + list(all_applied))
    )
    # exclude current incomplete year
    current_year = datetime.date.today().year
    years = [y for y in years if y < current_year]

    return {
        "years": years,
        "hun_theory": [hun_theory[y] for y in years],
        "hun_applied": [hun_applied[y] for y in years],
        "all_theory": [all_theory[y] for y in years],
        "all_applied": [all_applied[y] for y in years],
    }


def compute_stats(authors: list) -> dict:
    total = len(authors)
    hungary = sum(1 for a in authors if (a.get("works") or "") in ("hungary", "company_hungary"))
    abroad = sum(1 for a in authors if (a.get("works") or "") in ("abroad", "company_abroad"))
    theory = sum(1 for a in authors if a.get("category") == "theory")
    applied = sum(1 for a in authors if a.get("category") == "applied")

    astar_coauth = sum(a.get("core_astar", 0) or 0 for a in authors)
    astar_papers = sum(a.get("core_astar_papers", 0) or 0 for a in authors)
    hun_astar_eq = sum(a.get("hungarian_core_astar_equiv", 0) or 0 for a in authors)

    works_counter = Counter(a.get("works") or "unknown" for a in authors)
    age_counter = Counter(a.get("age_group") or "unknown" for a in authors)

    top_all = sorted(
        [a for a in authors if (a.get("core_astar") or 0) > 0],
        key=lambda a: a.get("core_astar", 0) or 0,
        reverse=True,
    )[:10]

    top_hun = sorted(
        [a for a in authors
         if (a.get("core_astar") or 0) > 0
         and (a.get("works") or "") in ("hungary", "company_hungary")],
        key=lambda a: a.get("core_astar", 0) or 0,
        reverse=True,
    )[:10]

    def top_hun_eq(age_groups=None):
        pool = [a for a in authors
                if (a.get("core_astar_equiv") or 0) > 0
                and (a.get("works") or "") in ("hungary", "company_hungary")]
        if age_groups:
            pool = [a for a in pool if (a.get("age_group") or "") in age_groups]
        return sorted(pool, key=lambda a: a.get("core_astar_equiv", 0) or 0, reverse=True)[:10]

    return {
        "total": total,
        "hungary": hungary,
        "abroad": abroad,
        "theory": theory,
        "applied": applied,
        "astar_coauth": astar_coauth,
        "astar_papers": astar_papers,
        "hun_astar_eq": hun_astar_eq,
        "works_counter": dict(works_counter),
        "age_counter": dict(age_counter),
        "top_all": top_all,
        "top_hun": top_hun,
        "top_hun_eq_all":    top_hun_eq(),
        "top_hun_eq_st":     top_hun_eq(["ERC Starting"]),
        "top_hun_eq_co":     top_hun_eq(["ERC Consolidator"]),
        "top_hun_eq_adv":    top_hun_eq(["ERC Advanced"]),
        "profiles": profile_count(),
    }


def works_rows(works_counter: dict) -> str:
    rows = []
    for key in ["hungary", "company_hungary", "abroad", "company_abroad", "inactive", "retired", "unknown"]:
        n = works_counter.get(key, 0)
        rows.append(f"<tr><td>{WORKS_LABEL.get(key, key)}</td><td class='num'>{n}</td></tr>")
    return "\n".join(rows)


def age_rows(age_counter: dict) -> str:
    rows = []
    for key in AGE_ORDER:
        n = age_counter.get(key, 0)
        if n == 0:
            continue
        label = AGE_LABEL.get(key, key)
        rows.append(f"<tr><td>{label}</td><td class='num'>{n}</td></tr>")
    return "\n".join(rows)


def top_rows(top: list, photo_map: dict, value_field: str = "core_astar", digits: int = 0) -> str:
    rows = []
    for i, a in enumerate(top, 1):
        name = a.get("name", "")
        slug = a.get("slug", "")
        val = a.get(value_field, 0) or 0
        val_str = f"{val:.{digits}f}" if isinstance(val, float) else str(val)
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
        profile_link = f'<a href="authors_profile.html#{slug}">{name}</a>' if slug else name
        photo_url = photo_map.get(slug, "")
        if photo_url:
            photo_cell = f'<img src="{photo_url}" class="thumb" alt="" onerror="this.style.display=\'none\'">'
        else:
            photo_cell = '<span class="thumb-placeholder"></span>'
        rows.append(
            f"<tr><td class='rank'>{i}.</td>"
            f"<td class='name-cell'>{photo_cell}{loc} {profile_link}</td>"
            f"<td>{cat_badge}</td><td class='num'>{val_str}</td></tr>"
        )
    return "\n".join(rows)


def render(s: dict, chart: dict, photo_map: dict) -> str:
    hun_pct = round(100 * s["hungary"] / s["total"]) if s["total"] else 0
    ab_pct = round(100 * s["abroad"] / s["total"]) if s["total"] else 0
    updated = datetime.date.today().strftime("%Y. %m. %d.")

    chart_years_js = json.dumps(chart["years"])
    chart_ht_js = json.dumps(chart["hun_theory"])
    chart_ha_js = json.dumps(chart["hun_applied"])
    chart_at_js = json.dumps(chart["all_theory"])
    chart_aa_js = json.dumps(chart["all_applied"])

    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Magyar CS Kutatók – Áttekintő</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
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

  .nav-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .nav-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem;
    padding: 1.25rem; text-decoration: none; color: var(--text);
    transition: box-shadow 0.15s, transform 0.15s;
    display: flex; flex-direction: column; gap: 0.35rem;
  }}
  .nav-card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,0.12); transform: translateY(-2px); }}
  .nav-card .icon {{ font-size: 2rem; }}
  .nav-card .title {{ font-weight: 600; font-size: 1rem; color: var(--accent); }}
  .nav-card .desc {{ font-size: 0.85rem; color: var(--muted); }}

  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .stat-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem;
    padding: 1rem; text-align: center;
  }}
  .stat-card .val {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
  .stat-card .val.green {{ color: var(--accent2); }}
  .stat-card .val.red {{ color: var(--accent3); }}
  .stat-card .lbl {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.15rem; }}

  .section-title {{ font-size: 1.1rem; font-weight: 600; margin: 1.75rem 0 0.75rem; border-bottom: 2px solid var(--border); padding-bottom: 0.35rem; }}

  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }}
  @media (max-width: 640px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

  .chart-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem;
    padding: 1.25rem; margin-bottom: 0;
  }}
  .chart-card canvas {{ width: 100% !important; }}

  table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 0.5rem; overflow: hidden; }}
  th {{ background: #f1f3f5; font-weight: 600; font-size: 0.85rem; padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
  td {{ padding: 0.45rem 0.75rem; border-bottom: 1px solid var(--border); font-size: 0.875rem; }}
  tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .rank {{ color: var(--muted); width: 2rem; }}

  .badge {{ display: inline-block; padding: 0.1em 0.5em; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; }}
  .badge.theory {{ background: #cfe2ff; color: #084298; }}
  .badge.applied {{ background: #d1e7dd; color: #0a3622; }}

  .name-cell {{ display: flex; align-items: center; gap: 0.5rem; }}
  .thumb {{ width: 32px; height: 32px; object-fit: cover; border-radius: 50%; flex-shrink: 0; border: 1px solid var(--border); }}
  .thumb-placeholder {{ width: 32px; height: 32px; border-radius: 50%; background: #e9ecef; flex-shrink: 0; }}

  footer {{ text-align: center; font-size: 0.78rem; color: var(--muted); padding: 1rem; }}
</style>
</head>
<body>

<header>
  <h1>Magyar Számítástudományi Kutatók</h1>
  <p>CORE A* &amp; CORE A minősítésű publikációkkal rendelkező kutatók adatbázisa</p>
  <p style="opacity:0.7; font-size:0.82rem; margin-top:0.4rem">Adatbázis frissítve: {updated} &nbsp;•&nbsp; Heti automatikus frissítés</p>
</header>

<main>

  <div class="nav-cards">
    <a class="nav-card" href="authors_profile.html">
      <span class="icon">👤</span>
      <span class="title">Kutatói profilok</span>
      <span class="desc">Részletes adatlapok, szerkesztési lehetőséggel</span>
    </a>
    <a class="nav-card" href="core_papers.html">
      <span class="icon">⭐</span>
      <span class="title">CORE A* cikkek</span>
      <span class="desc">Magyar szerzős legrangosabb konferencia-cikkek</span>
    </a>
    <a class="nav-card" href="authors_table.html">
      <span class="icon">📊</span>
      <span class="title">Összehasonlító táblázat</span>
      <span class="desc">Szűrhető, rendezhető kutatói összehasonlítás</span>
    </a>
    <a class="nav-card" href="journal_vs_conference_interactive.html">
      <span class="icon">📰</span>
      <span class="title">Folyóirat vs. konferencia</span>
      <span class="desc">Interaktív összehasonlítás publikációs típusonként</span>
    </a>
    <a class="nav-card" href="report.html">
      <span class="icon">📄</span>
      <span class="title">Elemzési jelentés</span>
      <span class="desc">Összefoglaló grafikonok és letölthető PDF-ek</span>
    </a>
  </div>

  <div class="section-title">Kulcsmutatók</div>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="val">{s["total"]}</div>
      <div class="lbl">Nyilvántartott kutató</div>
    </div>
    <div class="stat-card">
      <div class="val green">{s["hungary"]}</div>
      <div class="lbl">Magyarországon dolgozik ({hun_pct}%)</div>
    </div>
    <div class="stat-card">
      <div class="val red">{s["abroad"]}</div>
      <div class="lbl">Külföldön dolgozik ({ab_pct}%)</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["astar_papers"]}</div>
      <div class="lbl">CORE A* cikk (összes egyedi)</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["astar_coauth"]}</div>
      <div class="lbl">CORE A* szerzőség (szerző × cikk)</div>
    </div>
    <div class="stat-card">
      <div class="val">{s["hun_astar_eq"]:.0f}</div>
      <div class="lbl">Magyar CORE A* ekvivalens (súlyozott)</div>
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

  <div class="section-title">CORE A* cikkek évente</div>
  <div class="chart-card">
    <canvas id="yearChart" height="220"></canvas>
  </div>

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

  <div class="section-title">Top 10 kutató CORE A* szerzőségek szerint</div>
  <div class="two-col">
    <div>
      <table>
        <thead><tr><th></th><th>Kutató (összes)</th><th>Kat.</th><th class="num">A*</th></tr></thead>
        <tbody>{top_rows(s["top_all"], photo_map)}</tbody>
      </table>
    </div>
    <div>
      <table>
        <thead><tr><th></th><th>Kutató (Magyarország)</th><th>Kat.</th><th class="num">A*</th></tr></thead>
        <tbody>{top_rows(s["top_hun"], photo_map)}</tbody>
      </table>
    </div>
  </div>

  <div class="section-title">Top 10 kutató Core A* eq. szerint – Magyarország, ERC kariér szerint</div>
  <div class="two-col">
    <div>
      <table>
        <thead><tr><th></th><th>Bármely karriér</th><th>Kat.</th><th class="num">A* eq.</th></tr></thead>
        <tbody>{top_rows(s["top_hun_eq_all"], photo_map, "core_astar_equiv", 2)}</tbody>
      </table>
    </div>
    <div>
      <table>
        <thead><tr><th></th><th>ERC Starting (≤7 év)</th><th>Kat.</th><th class="num">A* eq.</th></tr></thead>
        <tbody>{top_rows(s["top_hun_eq_st"], photo_map, "core_astar_equiv", 2)}</tbody>
      </table>
    </div>
  </div>
  <div class="two-col" style="margin-top:1.25rem">
    <div>
      <table>
        <thead><tr><th></th><th>ERC Consolidator (7–12 év)</th><th>Kat.</th><th class="num">A* eq.</th></tr></thead>
        <tbody>{top_rows(s["top_hun_eq_co"], photo_map, "core_astar_equiv", 2)}</tbody>
      </table>
    </div>
    <div>
      <table>
        <thead><tr><th></th><th>ERC Advanced (12+ év)</th><th>Kat.</th><th class="num">A* eq.</th></tr></thead>
        <tbody>{top_rows(s["top_hun_eq_adv"], photo_map, "core_astar_equiv", 2)}</tbody>
      </table>
    </div>
  </div>

</main>

<footer>Adatok forrása: DBLP, MTMT, MTA • Automatikusan generálva • Utolsó frissítés: {updated}</footer>

<script>
(function() {{
  var years  = {chart_years_js};
  var hunT   = {chart_ht_js};
  var hunA   = {chart_ha_js};
  var allT   = {chart_at_js};
  var allA   = {chart_aa_js};

  var ctx = document.getElementById('yearChart').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: years,
      datasets: [
        {{
          label: 'Elméleti informatika – magyar cikkek',
          data: hunT,
          borderColor: '#c0392b',
          backgroundColor: 'rgba(192,57,43,0.15)',
          borderWidth: 2,
          borderDash: [6, 4],
          pointRadius: 2,
          fill: true,
          tension: 0.3,
          order: 4,
        }},
        {{
          label: 'Alkalmazott informatika – magyar cikkek',
          data: hunA,
          borderColor: '#1a3a9c',
          backgroundColor: 'rgba(26,58,156,0.12)',
          borderWidth: 2,
          borderDash: [6, 4],
          pointRadius: 2,
          fill: true,
          tension: 0.3,
          order: 3,
        }},
        {{
          label: 'Összes elméleti informatika cikk',
          data: allT,
          borderColor: '#c0392b',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 2,
          fill: false,
          tension: 0.3,
          order: 2,
        }},
        {{
          label: 'Összes alkalmazott informatika cikk',
          data: allA,
          borderColor: '#1a3a9c',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 2,
          fill: false,
          tension: 0.3,
          order: 1,
        }},
      ]
    }},
    options: {{
      responsive: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{
          position: 'top',
          labels: {{ boxWidth: 24, font: {{ size: 12 }} }}
        }},
        tooltip: {{ callbacks: {{
          title: function(items) {{ return items[0].label + '. év'; }}
        }} }}
      }},
      scales: {{
        x: {{
          title: {{ display: true, text: 'Év' }},
          ticks: {{ maxTicksLimit: 14 }}
        }},
        y: {{
          title: {{ display: true, text: 'Core A* cikkek száma' }},
          beginAtZero: true,
          ticks: {{ stepSize: 5 }}
        }}
      }}
    }}
  }});
}})();
</script>

</body>
</html>"""


def main():
    authors = load_authors()
    hun, abr = load_papers()
    name_cat = {a["name"]: a.get("category", "unknown") for a in authors}
    stats = compute_stats(authors)
    chart = build_chart_data(hun, abr, name_cat)
    photo_map = load_photo_map()
    html = render(stats, chart, photo_map)
    OUT.write_text(html, encoding="utf-8")
    print(f"Generated {OUT}")


if __name__ == "__main__":
    main()
