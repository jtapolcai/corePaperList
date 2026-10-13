#!/usr/bin/env python3
"""
Compile authors.json from profiles/*.json + computed stats from results JSONs.

Run after run_every_day.py (which generates the results/*.json files) and
before the HTML generators.

What it does:
  1. Reads every profiles/{slug}.json as the source of truth for manual data.
  2. Computes publication counts from results/*.json using PID-based matching.
  3. Computes A* equivalent scores (A*=1, A=1/3, B=1/6, C=1/9, NR=1/15).
  4. Writes the combined data to authors.json (sorted by slug).

Usage:
  python3 compile_authors_json.py
"""
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"
RESULTS_DIR = BASE / "results"
AUTHORS_JSON = BASE / "authors.json"

TIER_WEIGHT = {"astar": 1.0, "a": 1 / 3, "b": 1 / 6, "c": 1 / 9, "nr": 1 / 15}

# (filename, is_hungarian)
TIER_SOURCES = {
    "astar": [
        ("hungarian_papers_coreAstar.json", True),
        ("already_abroad_papers_coreAstar.json", False),
    ],
    "a": [
        ("hungarian_papers_coreA.json", True),
        ("already_abroad_papers_coreA.json", False),
    ],
    "b": [
        ("hungarian_papers_coreB.json", True),
        ("already_abroad_papers_coreB.json", False),
    ],
    "c": [
        ("hungarian_papers_coreC.json", True),
        ("already_abroad_papers_coreC.json", False),
    ],
    "nr": [
        ("hungarian_papers_coreno_rank.json", True),
        ("hungarian_papers_norank.json", True),
        ("already_abroad_papers_norank.json", False),
    ],
}


def extract_pid(dblp_url: str) -> str | None:
    if not dblp_url:
        return None
    m = re.search(r"/pid/(.+)$", dblp_url.rstrip("/"))
    return m.group(1) if m else None


def load_profiles() -> list[dict]:
    profiles = []
    for f in sorted(PROFILES_DIR.glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "slug" in data:
                profiles.append(data)
        except Exception as e:
            print(f"Warning: skipping {f.name}: {e}")
    return profiles


def compute_stats(profiles: list[dict]) -> dict[str, dict]:
    pid_to_slug = {}
    name_to_slug = {}
    for p in profiles:
        pid = extract_pid(p.get("dblp_url", ""))
        if pid:
            pid_to_slug[pid] = p["slug"]
        name = p.get("name", "")
        if name:
            name_to_slug[name] = p["slug"]

    # stats[slug][tier] = {total, hu, first, hu_first}
    stats: dict[str, dict] = defaultdict(
        lambda: {
            t: {"total": 0, "hu": 0, "first": 0, "hu_first": 0}
            for t in TIER_WEIGHT
        }
    )

    seen_papers: dict[str, set] = defaultdict(set)  # slug -> set of paper keys already counted per tier

    for tier, sources in TIER_SOURCES.items():
        # Deduplicate papers across files within the same tier (a paper may appear in multiple files)
        tier_seen: dict[str, set] = defaultdict(set)  # slug -> paper keys counted for this tier

        for filename, is_hu in sources:
            path = RESULTS_DIR / filename
            if not path.exists():
                continue
            try:
                papers = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Warning: skipping {filename}: {e}")
                continue

            for paper_key, paper in papers.items():
                authors = paper.get("authors", [])
                for i, entry in enumerate(authors):
                    if isinstance(entry, list):
                        name, pid = entry[0], entry[1] if len(entry) > 1 else None
                    else:
                        name, pid = entry, None

                    slug = pid_to_slug.get(pid) if pid else None
                    if slug is None:
                        slug = name_to_slug.get(name)
                    if slug is None:
                        continue

                    # Deduplicate: count each paper only once per (slug, tier)
                    if paper_key in tier_seen[slug]:
                        continue
                    tier_seen[slug].add(paper_key)

                    is_first = i == 0
                    stats[slug][tier]["total"] += 1
                    if is_hu:
                        stats[slug][tier]["hu"] += 1
                    if is_first:
                        stats[slug][tier]["first"] += 1
                        if is_hu:
                            stats[slug][tier]["hu_first"] += 1

    return stats


def r4(v: float) -> float:
    return round(v, 4)


def build_author_record(profile: dict, stats: dict[str, dict]) -> dict:
    slug = profile.get("slug", "")
    s = stats.get(slug, {t: {"total": 0, "hu": 0, "first": 0, "hu_first": 0} for t in TIER_WEIGHT})

    astar = s["astar"]["total"]; a = s["a"]["total"]; b = s["b"]["total"]; c = s["c"]["total"]; nr = s["nr"]["total"]
    hu_astar = s["astar"]["hu"]; hu_a = s["a"]["hu"]; hu_b = s["b"]["hu"]; hu_c = s["c"]["hu"]; hu_nr = s["nr"]["hu"]
    f_astar = s["astar"]["first"]; f_a = s["a"]["first"]; f_b = s["b"]["first"]; f_c = s["c"]["first"]; f_nr = s["nr"]["first"]

    equiv = r4(astar + a / 3 + b / 6 + c / 9 + nr / 15)
    hu_equiv = r4(hu_astar + hu_a / 3 + hu_b / 6 + hu_c / 9 + hu_nr / 15)
    first_equiv = r4(f_astar + f_a / 3 + f_b / 6 + f_c / 9 + f_nr / 15)

    phd_year = profile.get("phd_year")
    years_since_phd = date.today().year - phd_year if phd_year else None

    if years_since_phd is None:
        age_group = "unknown"
    elif years_since_phd <= 7:
        age_group = "ERC Starting"
    elif years_since_phd <= 12:
        age_group = "ERC Consolidator"
    else:
        age_group = "ERC Advanced"

    return {
        **profile,
        # Computed stats (overwrite whatever was in the profile)
        "core_astar": astar,
        "core_a": a,
        "core_b": b,
        "core_c": c,
        "no_core": nr,
        "core_astar_equiv": equiv,
        "hungarian_core_astar_equiv": hu_equiv,
        "first_author_core_astar_equiv": first_equiv,
        # Derived
        "years_since_phd": years_since_phd,
        "age_group": age_group,
    }


def compute_ranks(authors: list[dict]) -> list[dict]:
    hung = sorted(
        [a for a in authors if a.get("works") == "hungary" and (a.get("core_astar_equiv") or 0) > 0],
        key=lambda x: -(x.get("core_astar_equiv") or 0),
    )
    rank_map = {a["slug"]: i for i, a in enumerate(hung, 1)}
    total = len(hung)
    for a in authors:
        r = rank_map.get(a.get("slug", ""))
        if r is not None:
            a["category_astar_rank"] = r
            a["age_astar_rank"] = r  # simplified; proper age-bucket ranking can be added later
            a["hung_astar_rank"] = r
            a["hung_astar_total"] = total
    return authors


def main():
    profiles = load_profiles()
    print(f"Loaded {len(profiles)} profiles from {PROFILES_DIR}")

    stats = compute_stats(profiles)
    print(f"Computed stats for {len(stats)} authors from results JSONs")

    authors = [build_author_record(p, stats) for p in profiles]
    authors = compute_ranks(authors)

    AUTHORS_JSON.write_text(
        json.dumps(authors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Written {len(authors)} entries to {AUTHORS_JSON}")


if __name__ == "__main__":
    main()
