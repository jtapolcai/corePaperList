#!/usr/bin/env python3
"""
Backfill phd_year from MTMT API for profiles that have mtmt_id but no phd_year.

Usage:
  python3 backfill_phd_year_mtmt.py [--dry-run] [--limit N]
"""
import argparse
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"
SLEEP = 0.2

PHD_DEGREES = {"phd", "kandidátus", "tudomány doktora", "csc"}


_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def fetch_mtmt_author(mtmt_id):
    url = f"https://m2.mtmt.hu/api/author/{mtmt_id}?labelLang=hun"
    req = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as r:
            return json.load(r)
    except Exception as e:
        print(f"    [{e}]", end=" ")
        return None


def extract_phd_year(data):
    degrees = (data.get("content") or {}).get("degrees") or []
    phd_year = None
    for deg in degrees:
        label = deg.get("label") or ""
        degree_label = (deg.get("degree") or {}).get("label") or ""
        # Check if it's a PhD-type degree
        if any(p in label.lower() or p in degree_label.lower() for p in PHD_DEGREES):
            m = re.search(r"\b(19|20)\d{2}\b", label)
            if m:
                yr = int(m.group())
                # Keep earliest PhD year
                if phd_year is None or yr < phd_year:
                    phd_year = yr
    return phd_year


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
        if d.get("mtmt_id") and not d.get("phd_year"):
            to_update.append((path, d))

    print(f"Profiles with mtmt_id but no phd_year: {len(to_update)}")

    done = updated = skipped = not_found = 0
    for path, profile in to_update:
        if args.limit and done >= args.limit:
            break

        mtmt_id = profile["mtmt_id"]
        name = profile.get("name", path.stem)

        data = fetch_mtmt_author(mtmt_id)
        time.sleep(SLEEP)

        if not data:
            print(f"  FAIL  {name} ({mtmt_id})")
            skipped += 1
            done += 1
            continue

        phd_year = extract_phd_year(data)
        if phd_year is None:
            print(f"  NONE  {name}: no PhD degree found in MTMT")
            not_found += 1
            done += 1
            continue

        print(f"  OK    {name}: phd_year={phd_year}")
        if not args.dry_run:
            profile["phd_year"] = phd_year
            path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            updated += 1

        done += 1

    print(f"\nDone: updated={updated}, not_found={not_found}, skipped={skipped}, total={done}")


if __name__ == "__main__":
    main()
