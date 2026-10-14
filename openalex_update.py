#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update OpenAlex metrics in profiles/*.json from the OpenAlex API.

Downloads author records and caches them under openalex/{id}.json
(same pattern as mtmt/{id}.json). Then updates the profile with:
  openalex_cited_by_count  – total citations
  openalex_h_index         – h-index
  openalex_2yr_cited_by_count – citations in the last 2 years

Usage:
  python3 openalex_update.py                  # all profiles with openalex_id
  python3 openalex_update.py --force          # re-fetch even if cached
  python3 openalex_update.py peter-babarczi  # single slug
  python3 openalex_update.py peter-babarczi --force
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"
CACHE_DIR = BASE / "openalex"
OA_BASE = "https://api.openalex.org"
MAILTO = "tapolcai@tmit.bme.hu"   # polite pool
SLEEP = 0.12                        # ~8 req/s, well within rate limits


def oa_get(path: str, params: dict | None = None) -> dict | None:
    params = dict(params or {})
    params["mailto"] = MAILTO
    try:
        r = requests.get(OA_BASE + path, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    OA error {path}: {e}")
        return None


def fetch_author(short_id: str, force: bool) -> dict | None:
    cache_path = CACHE_DIR / f"{short_id}.json"
    CACHE_DIR.mkdir(exist_ok=True)

    if cache_path.exists() and not force:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    data = oa_get(
        f"/authors/{short_id}",
        {"select": "id,display_name,cited_by_count,summary_stats,counts_by_year"},
    )
    time.sleep(SLEEP)
    if data:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return data


def profile_paths(slug: str | None) -> list[Path]:
    if slug:
        p = PROFILES_DIR / f"{slug}.json"
        if not p.exists():
            sys.exit(f"Profile not found: {p}")
        return [p]
    return sorted(PROFILES_DIR.glob("*.json"))


def update_profile(path: Path, force: bool) -> bool:
    with open(path, encoding="utf-8") as f:
        profile = json.load(f)

    oa_id = profile.get("openalex_id", "").strip()
    if not oa_id:
        return False

    name = profile.get("name", path.stem)
    print(f"  {name} ({oa_id}) ...", end=" ", flush=True)

    data = fetch_author(oa_id, force)
    if not data:
        print("no data")
        return False

    stats = data.get("summary_stats") or {}
    cited = data.get("cited_by_count")
    h_index = stats.get("h_index")
    counts_by_year = data.get("counts_by_year") or []

    # Sum citations for the two most recent calendar years in the data
    years = sorted({x["year"] for x in counts_by_year}, reverse=True)
    recent_years = set(years[:2])
    cit_2yr = sum(
        x.get("cited_by_count", 0)
        for x in counts_by_year
        if x["year"] in recent_years
    ) if counts_by_year else None

    updates = {
        "openalex_cited_by_count": cited,
        "openalex_h_index": h_index,
        "openalex_2yr_cited_by_count": cit_2yr,
    }

    changed = False
    for key, val in updates.items():
        if val is None:
            continue
        if profile.get(key) != val:
            profile[key] = val
            changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"updated (cited={cited}, h={h_index}, 2yr={cit_2yr})")
    else:
        print("no change")

    return changed


def main():
    parser = argparse.ArgumentParser(description="Update OpenAlex metrics in profiles")
    parser.add_argument("slug", nargs="?", help="Profile slug (e.g. peter-babarczi)")
    parser.add_argument("--force", action="store_true", help="Re-fetch from OpenAlex even if cached")
    args = parser.parse_args()

    paths = profile_paths(args.slug)
    updated = skipped = 0

    oa_paths = [p for p in paths if not p.stem.startswith("_")]
    print(f"Processing {len(oa_paths)} profile(s){'  [force]' if args.force else ''}...")

    for p in oa_paths:
        try:
            if update_profile(p, force=args.force):
                updated += 1
        except Exception as e:
            print(f"  ERROR {p.stem}: {e}")
            skipped += 1

    print(f"\nDone: {updated} updated, {skipped} errors, {len(oa_paths)-updated-skipped} unchanged.")
    if updated:
        print("Run compile_authors_json.py then gen_authors_html.py to publish changes.")


if __name__ == "__main__":
    main()
