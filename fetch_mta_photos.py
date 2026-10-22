#!/usr/bin/env python3
"""
Fetch MTA profile photos for authors that have mta_att_id but no cached photo.
Updates profiles/_mta_photos.json in place.

Sources of mta_att_id (in priority order):
  1. profiles/*.json  (explicit overrides — always retried if empty)
  2. authors.json     (scraped data — only fetched if not yet in cache)

In CI (GITHUB_ACTIONS env var set) at most MAX_CI_FETCH authors are fetched
per run to keep the job within time limits. Run locally for bulk updates.
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path

MAX_CI_FETCH = 40   # limit per CI run to avoid timeouts
TIMEOUT = 8         # seconds per HTTP request

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"
CACHE_FILE = PROFILES_DIR / "_mta_photos.json"
AUTHORS_JSON = BASE / "authors.json"

_PHOTO_RE = re.compile(r"https://aat\.mta\.hu/aat/FileData/Get/\d+")


def fetch_photo(att_url: str) -> str | None:
    """Return the photo URL, "" if the page has no photo, or None on error."""
    m = re.search(r"PersonId=(\d+)", att_url)
    if not m:
        return ""
    url = f"https://mta.hu/koztestuleti_tagok?PersonId={m.group(1)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8", errors="replace")
        imgs = _PHOTO_RE.findall(html)
        return imgs[0] if imgs else ""
    except Exception as e:
        print(f"  Warning: {url}: {e}")
        return None


def collect_candidates(profiles_dir: Path, cache: dict) -> tuple[list, list]:
    """
    Return two candidate lists (slug, att_id):
      priority  — profile files with empty/missing cache (always retried first)
      bulk      — authors.json entries not yet in cache at all (new discoveries)
    """
    _BAD = {"-", "—", "N/A", "n/a", ""}

    # --- profile files (explicit overrides) ---
    profile_candidates: list[tuple[str, str]] = []
    for f in sorted(profiles_dir.glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            profile = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = f.stem
        att_id = (profile.get("mta_att_id") or "").strip()
        if att_id in _BAD:
            continue
        # retry if cache is missing or empty (user explicitly set mta_att_id)
        if not cache.get(slug):
            profile_candidates.append((slug, att_id))

    # --- authors.json (scraped bulk data) ---
    bulk_candidates: list[tuple[str, str]] = []
    if AUTHORS_JSON.exists():
        try:
            for a in json.loads(AUTHORS_JSON.read_text(encoding="utf-8")):
                slug = a.get("slug", "")
                att_id = (a.get("mta_att_id") or "").strip()
                if not slug or att_id in _BAD:
                    continue
                # only fetch if NEVER tried before (not in cache at all)
                if slug not in cache:
                    bulk_candidates.append((slug, att_id))
        except Exception:
            pass

    return profile_candidates, bulk_candidates


def main():
    in_ci = bool(os.environ.get("GITHUB_ACTIONS"))
    max_fetch = MAX_CI_FETCH if in_ci else None  # None = unlimited

    cache: dict = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    non_empty_cached = sum(1 for v in cache.values() if v)
    print(f"Cache: {len(cache)} entries, {non_empty_cached} with actual photo URL")
    if in_ci:
        print(f"CI mode: max {max_fetch} fetches per run")

    priority, bulk = collect_candidates(PROFILES_DIR, cache)
    print(f"Priority candidates (profile files): {len(priority)}")
    print(f"Bulk candidates (authors.json, new): {len(bulk)}")

    # Process priority first, then bulk up to the limit
    all_candidates = priority + bulk
    if max_fetch is not None:
        all_candidates = all_candidates[:max_fetch]

    updated = 0
    for slug, att_id in all_candidates:
        print(f"Fetching MTA photo for {slug} ({att_id})...")
        photo = fetch_photo(att_id)
        if photo:
            cache[slug] = photo
            print(f"  → {photo}")
            updated += 1
        elif photo == "":
            cache[slug] = ""
            print(f"  → no photo found")
        else:
            # fetch error (e.g. mta.hu maintenance): leave uncached so it is retried
            print(f"  → fetch failed, will retry next run")
        time.sleep(0.5)

    CACHE_FILE.write_text(
        json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if updated:
        print(f"\nUpdated _mta_photos.json with {updated} new photo(s).")
    else:
        print("No new photos found.")


if __name__ == "__main__":
    main()
