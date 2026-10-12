#!/usr/bin/env python3
"""
Fetch MTA profile photos for authors that have mta_att_id but no cached photo.
Updates profiles/_mta_photos.json in place.

Sources of mta_att_id (in priority order):
  1. profiles/*.json  (explicit overrides)
  2. authors.json     (scraped data)

Re-fetches entries where the cached value is empty string "".
"""
import json
import re
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"
CACHE_FILE = PROFILES_DIR / "_mta_photos.json"
AUTHORS_JSON = BASE / "authors.json"

_PHOTO_RE = re.compile(r"https://aat\.mta\.hu/aat/FileData/Get/\d+")


def fetch_photo(att_url: str) -> str | None:
    m = re.search(r"PersonId=(\d+)", att_url)
    if not m:
        return None
    url = f"https://mta.hu/koztestuleti_tagok?PersonId={m.group(1)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
        imgs = _PHOTO_RE.findall(html)
        return imgs[0] if imgs else None
    except Exception as e:
        print(f"  Warning: {url}: {e}")
        return None


def collect_candidates(profiles_dir: Path) -> dict[str, str]:
    """Return {slug: mta_att_id} from all sources (profiles override authors.json)."""
    candidates: dict[str, str] = {}

    # 1. authors.json
    if AUTHORS_JSON.exists():
        try:
            for a in json.loads(AUTHORS_JSON.read_text(encoding="utf-8")):
                slug = a.get("slug", "")
                att_id = a.get("mta_att_id", "") or ""
                # skip placeholder values
                if slug and att_id and att_id not in ("-", "—", "N/A", "n/a"):
                    candidates[slug] = att_id
        except Exception:
            pass

    # 2. profiles/*.json (override)
    for f in sorted(profiles_dir.glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            profile = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = f.stem
        att_id = profile.get("mta_att_id", "") or ""
        if att_id and att_id not in ("-", "—", "N/A", "n/a"):
            candidates[slug] = att_id
        elif slug in candidates and not att_id:
            del candidates[slug]

    return candidates


def main():
    cache: dict = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    candidates = collect_candidates(PROFILES_DIR)
    print(f"Found {len(candidates)} authors with mta_att_id")
    non_empty_cached = sum(1 for v in cache.values() if v)
    print(f"Cache: {len(cache)} entries, {non_empty_cached} with actual photo URL")

    updated = 0
    for slug, att_id in sorted(candidates.items()):
        # Skip if already cached with a real (non-empty) photo URL
        if cache.get(slug):
            continue
        print(f"Fetching MTA photo for {slug} ({att_id})...")
        photo = fetch_photo(att_id)
        if photo:
            cache[slug] = photo
            print(f"  → {photo}")
            updated += 1
        else:
            cache[slug] = ""
            print(f"  → no photo found")
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
