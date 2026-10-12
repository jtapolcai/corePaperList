#!/usr/bin/env python3
"""
Find MTMT IDs for authors without one.
Queries MTMT API by family name and outputs a match table.

Usage:
  python3 find_missing_mtmt.py > mtmt_matches.txt
  python3 find_missing_mtmt.py --output mtmt_matches.json
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE = Path(__file__).parent
AUTHORS_JSON = BASE / "authors.json"
PROFILES_DIR = BASE / "profiles"

EXCLUDE_WORKS = {"abroad", "company_abroad"}
MTMT_API = "https://m2.mtmt.hu/api/author?cond=familyName;eq;{name}&format=json&size=25"


def clean_name(name: str) -> str:
    return re.sub(r'\s+\d{4}$', '', name).strip()


def name_parts(name: str) -> list[str]:
    clean = clean_name(name)
    parts = clean.split()
    candidates = []
    if parts:
        candidates.append(parts[-1])  # last word = likely family name
    if len(parts) > 1 and parts[0] != parts[-1]:
        candidates.append(parts[0])
    return list(dict.fromkeys(candidates))  # deduplicate


def query_mtmt(family_name: str) -> list[dict]:
    url = MTMT_API.format(name=urllib.parse.quote(family_name))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("content", [])
    except Exception as e:
        print(f"  [warn] MTMT query failed for {family_name!r}: {e}", file=sys.stderr)
        return []


def load_profiles(profiles_dir: Path) -> dict:
    profiles = {}
    if not profiles_dir.exists():
        return profiles
    for f in profiles_dir.glob("*.json"):
        if f.stem.startswith("_"):
            continue
        try:
            profiles[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return profiles


def main():
    authors = json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))
    profiles = load_profiles(PROFILES_DIR)

    # Apply profile overrides
    for a in authors:
        slug = a.get("slug", "")
        if slug in profiles:
            p = profiles[slug]
            if p.get("mtmt_id"):
                a["mtmt_id"] = p["mtmt_id"]
            if p.get("works"):
                a["works"] = p["works"]

    # Filter: no mtmt_id, not abroad
    targets = [
        a for a in authors
        if not a.get("mtmt_id")
        and a.get("works") not in EXCLUDE_WORKS
    ]

    print(f"Searching MTMT for {len(targets)} authors without mtmt_id...\n", file=sys.stderr)

    results = []
    seen_families = {}

    for i, a in enumerate(targets, 1):
        name = a.get("name", "")
        slug = a.get("slug", "")
        works = a.get("works", "")
        aff = a.get("affiliations", "")

        families = name_parts(name)
        candidates = {}

        for fam in families:
            if fam in seen_families:
                entries = seen_families[fam]
            else:
                entries = query_mtmt(fam)
                seen_families[fam] = entries
                time.sleep(0.3)  # be polite

            for c in entries:
                mtid = c.get("mtid")
                if mtid and mtid not in candidates:
                    candidates[mtid] = c.get("label", "")

        results.append({
            "slug": slug,
            "name": name,
            "works": works,
            "affiliations": aff,
            "candidates": [
                {"mtmt_id": mtid, "label": label}
                for mtid, label in candidates.items()
            ],
        })

        status = f"  [{i}/{len(targets)}] {name}: {len(candidates)} találat"
        print(status, file=sys.stderr)

    # Output
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        out_path = Path(sys.argv[idx + 1])
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved to {out_path}", file=sys.stderr)
    else:
        # Human-readable table
        print(f"{'Szerző':<35} {'Munkahely':<15} {'MTMT találatok'}")
        print("-" * 100)
        for r in results:
            cands = r["candidates"]
            if not cands:
                cand_str = "— nem található"
            elif len(cands) == 1:
                c = cands[0]
                cand_str = f"{c['mtmt_id']}: {c['label']}"
            else:
                cand_str = f"{len(cands)} találat: " + " | ".join(
                    f"{c['mtmt_id']}:{c['label'][:30]}" for c in cands[:3]
                )
            print(f"{r['name']:<35} {r['works']:<15} {cand_str}")


if __name__ == "__main__":
    main()
