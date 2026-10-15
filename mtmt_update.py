#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update MTMT metrics in profiles/*.json from the MTMT API.

Downloads author publication data and caches it under mtmt/{mtmt_id}.json
(same pattern as dblp/{Name}.json). Then updates the profile JSON with
derived metrics.

Usage:
  python3 mtmt_update.py                  # all profiles, use cache
  python3 mtmt_update.py --force          # all profiles, re-fetch from MTMT
  python3 mtmt_update.py peter-babarczi  # single profile slug
  python3 mtmt_update.py peter-babarczi --force
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
import mtmt_utils


# Maps MTMT degree type label → (profile degree prefix, is_phd_equivalent)
# is_phd_equivalent=True → use year as phd_year instead of setting degree text
_DEGREE_MAP = {
    "PhD":              ("PhD",            True),
    "Kandidátus":       ("kandidátus",     True),   # Soviet-era PhD, always pre-2000
    "MTA Doktora":      ("MTA doktora",    False),
    "MTA Levelező tag": ("levelező tag",   False),
    "MTA Rendes tag":   ("rendes tag",     False),
    "MTA külső tagja":  ("levelező tag",   False),  # treat as equivalent
}


def extract_degree_info(author_rec: dict) -> tuple[int | None, str | None]:
    """Return (phd_year, degree_text) from MTMT degrees list.

    phd_year  – set for PhD/Kandidátus entries
    degree_text – set for MTA-level degrees (triggers ERC Advanced in compile)
    Priority: PhD > Kandidátus > MTA Doktora > Levelező > Rendes tag.
    """
    phd_year: int | None = None
    degree_text: str | None = None
    priority = 99

    for deg in author_rec.get("degrees") or []:
        label = deg.get("label", "")
        kind = deg.get("degree", {}).get("label", "")
        if kind not in _DEGREE_MAP:
            continue
        prefix, is_phd = _DEGREE_MAP[kind]
        year_m = re.search(r"\b(19|20)\d{2}\b", label)
        year = int(year_m.group()) if year_m else None
        p = list(_DEGREE_MAP).index(kind)
        if p >= priority:
            continue
        priority = p
        if is_phd:
            phd_year = year
            degree_text = None  # PhD/Kandidátus: use phd_year, no degree text needed
        else:
            phd_year = None
            degree_text = f"{prefix} ({year})" if year else prefix

    return phd_year, degree_text

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"

METRIC_MAP = {
    # get_metrics() key  →  profile JSON key
    "journal_publications":     "mtmt_journals",
    "conference_publications":  "mtmt_conferences",
    "total_citations":          "mtmt_citations",
    "journal D1 eqvivalents":   "mtmt_d1_equiv",
}

RANK_MAP = {
    # rank subkey  →  profile JSON key
    "D1": "mtmt_d1",
    "Q1": "mtmt_q1",
    "Q2": "mtmt_q2",
    "Q3": "mtmt_q3",
    "Q4": "mtmt_q4",
}


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

    mtmt_id = str(profile.get("mtmt_id", "")).strip()
    if not mtmt_id:
        return False

    name = profile.get("name", path.stem)
    print(f"  {name} (MTMT {mtmt_id}) ...", end=" ", flush=True)

    author_rec, pub_rec = mtmt_utils.get_mtmt_record(mtmt_id, force=force, author_name=name)
    if not author_rec:
        print("no data")
        return False

    metrics = mtmt_utils.get_metrics(author_rec, pub_rec)

    changed = False

    for src_key, dst_key in METRIC_MAP.items():
        val = metrics.get(src_key)
        if val is None:
            continue
        if isinstance(val, float):
            val = round(val, 4)
        old = profile.get(dst_key)
        if old != val:
            profile[dst_key] = val
            changed = True

    rank = metrics.get("rank", {})
    for rank_key, dst_key in RANK_MAP.items():
        val = rank.get(rank_key, 0)
        old = profile.get(dst_key)
        if old != val:
            profile[dst_key] = val
            changed = True

    affils = metrics.get("affiliations")
    if affils is not None:
        affil_str = "; ".join(a for a in affils if a)
        old = profile.get("mtmt_affiliations", "")
        if old != affil_str:
            profile["mtmt_affiliations"] = affil_str
            changed = True

    # Fill phd_year / degree from MTMT degrees — only if not already set
    if not profile.get("phd_year") and not profile.get("degree"):
        phd_year, degree_text = extract_degree_info(author_rec)
        if phd_year:
            profile["phd_year"] = phd_year
            changed = True
        elif degree_text:
            profile["degree"] = degree_text
            changed = True
    elif not profile.get("phd_year"):
        # degree is set but phd_year missing — only fill phd_year from PhD/Kandidátus
        phd_year, _ = extract_degree_info(author_rec)
        if phd_year:
            profile["phd_year"] = phd_year
            changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print("updated")
    else:
        print("no change")

    return changed


def main():
    parser = argparse.ArgumentParser(description="Update MTMT metrics in profiles")
    parser.add_argument("slug", nargs="?", help="Profile slug (e.g. peter-babarczi)")
    parser.add_argument("--force", action="store_true", help="Re-fetch from MTMT even if cached")
    args = parser.parse_args()

    paths = profile_paths(args.slug)
    updated = 0
    skipped = 0

    print(f"Processing {len(paths)} profile(s){'  [force]' if args.force else ''}...")

    for p in paths:
        if p.stem.startswith("_"):
            continue
        try:
            if update_profile(p, force=args.force):
                updated += 1
        except Exception as e:
            print(f"  ERROR {p.stem}: {e}")
            skipped += 1

    print(f"\nDone: {updated} updated, {skipped} errors, {len(paths)-updated-skipped} unchanged.")
    if updated:
        print("Run compile_authors_json.py then the HTML generators to publish changes.")


if __name__ == "__main__":
    main()
