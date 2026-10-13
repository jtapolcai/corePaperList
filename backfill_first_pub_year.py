#!/usr/bin/env python3
"""
Backfill openalex_first_pub_year for profiles that already have openalex_id
but are missing the field (added later to enrich_openalex.py).

Usage:
  python3 backfill_first_pub_year.py [--dry-run] [--limit N]
"""
import argparse
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"
SLEEP = 0.12
OA_BASE = "https://api.openalex.org"


def oa_get(path, params=None):
    from urllib.parse import urlencode
    url = OA_BASE + path
    if params:
        url += "?" + urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "corePaperList/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    profiles = sorted(p for p in PROFILES_DIR.glob("*.json") if not p.stem.startswith("_"))
    to_update = []
    for path in profiles:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("openalex_id") and "openalex_first_pub_year" not in d:
            to_update.append((path, d))

    print(f"Profiles needing first_pub_year: {len(to_update)}")

    done = updated = skipped = 0
    for path, profile in to_update:
        if args.limit and done >= args.limit:
            break

        oa_id = profile["openalex_id"]
        short_id = oa_id.split("/")[-1] if "/" in oa_id else oa_id
        name = profile.get("name", path.stem)

        data = oa_get(f"/authors/{short_id}", {"select": "counts_by_year"})
        time.sleep(SLEEP)

        if not data:
            print(f"  FAIL {name} ({short_id})")
            skipped += 1
            done += 1
            continue

        counts = data.get("counts_by_year") or []
        pub_years = [x["year"] for x in counts if x.get("works_count", 0) > 0]
        first_pub = min(pub_years) if pub_years else None

        print(f"  {name}: first_pub={first_pub}")

        if not args.dry_run and first_pub is not None:
            profile["openalex_first_pub_year"] = first_pub
            path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            updated += 1

        done += 1

    print(f"\nDone: updated={updated}, skipped={skipped}, total={done}")


if __name__ == "__main__":
    main()
