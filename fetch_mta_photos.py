#!/usr/bin/env python3
"""
Fetch MTA profile photos for authors that have mta_att_id but no cached photo.
Updates profiles/_mta_photos.json in place.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
PROFILES_DIR = BASE / "profiles"
CACHE_FILE = PROFILES_DIR / "_mta_photos.json"

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


def main():
    cache: dict = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    updated = 0
    for f in sorted(PROFILES_DIR.glob("*.json")):
        if f.stem.startswith("_"):
            continue
        try:
            profile = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        slug = f.stem
        att_id = profile.get("mta_att_id") or ""
        if not att_id:
            continue
        # Skip if already cached or profile has explicit mta_photo
        if slug in cache or profile.get("mta_photo"):
            continue
        print(f"Fetching MTA photo for {slug} ({att_id})...")
        photo = fetch_photo(att_id)
        if photo:
            cache[slug] = photo
            print(f"  → {photo}")
            updated += 1
        else:
            print(f"  → no photo found")
        time.sleep(0.5)

    if updated:
        CACHE_FILE.write_text(
            json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nUpdated _mta_photos.json with {updated} new photo(s).")
    else:
        print("No new photos to fetch.")


if __name__ == "__main__":
    main()
