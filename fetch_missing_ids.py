#!/usr/bin/env python3
"""
Search MTMT for authors in authors.json who are missing an mtmt_id.
Writes confident matches into profiles/{slug}.json.

Usage:
  python3 fetch_missing_ids.py              # dry-run, print candidates
  python3 fetch_missing_ids.py --write      # write to profiles/
  python3 fetch_missing_ids.py --slug csaba-szepesvari --write  # single author
"""
import json
import sys
import time
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path

BASE = Path(__file__).parent
AUTHORS_JSON = BASE / "authors.json"
PROFILES_DIR = BASE / "profiles"

DRY_RUN = "--write" not in sys.argv
SINGLE_SLUG = None
if "--slug" in sys.argv:
    idx = sys.argv.index("--slug")
    SINGLE_SLUG = sys.argv[idx + 1]


def normalize(s: str) -> str:
    """Remove accents, lowercase."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def mtmt_search_by_family(family_name: str, given_name: str) -> list:
    """Search MTMT for author by Hungarian family name."""
    url = (
        f"https://m2.mtmt.hu/api/author"
        f"?cond=familyName;eq;{urllib.parse.quote(family_name)}"
        f"&format=json&size=20"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("content", [])
    except Exception as e:
        print(f"  MTMT API error: {e}")
        return []


def split_name(name: str):
    """Return (family, given) guesses from DBLP-style 'Given Family' name."""
    parts = name.strip().split()
    # Try each word as potential family name
    guesses = []
    for i in range(1, len(parts)):
        given = " ".join(parts[:i])
        family = " ".join(parts[i:])
        guesses.append((family, given))
    # Also try reversed (Hungarian order: Family Given)
    if len(parts) >= 2:
        guesses.append((parts[0], " ".join(parts[1:])))
    return guesses


def score_match(candidate: dict, given_name: str, family_name: str) -> float:
    """Score confidence of a match (0–1). Compares after accent normalization."""
    c_fam = normalize(candidate.get("familyName", ""))
    c_giv = normalize(candidate.get("givenName", ""))
    fam = normalize(family_name)
    giv = normalize(given_name)
    # MTMT givenName sometimes includes the family name too
    c_giv_first = c_giv.split()[0] if c_giv else ""
    giv_first = giv.split()[0] if giv else ""
    score = 0.0
    if c_fam == fam:
        score += 0.5
    elif fam in c_fam or c_fam in fam:
        score += 0.3
    if c_giv_first == giv_first:
        score += 0.5
    elif giv_first in c_giv or c_giv_first in giv:
        score += 0.3
    return score


def load_profiles() -> dict:
    profiles = {}
    for f in PROFILES_DIR.glob("*.json"):
        if f.stem.startswith("_"):
            continue
        try:
            profiles[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return profiles


def save_profile(slug: str, key: str, value: str):
    path = PROFILES_DIR / f"{slug}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    data[key] = value
    PROFILES_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → Wrote {key}={value!r} to profiles/{slug}.json")


def main():
    authors = json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))
    profiles = load_profiles()

    found = skipped = missing = 0

    for a in authors:
        slug = a["slug"]
        if SINGLE_SLUG and slug != SINGLE_SLUG:
            continue

        name = a["name"]

        # Determine effective mtmt_id (from authors.json or profile override)
        profile = profiles.get(slug, {})
        effective_mtmt = (
            profile.get("mtmt_id")
            or a.get("mtmt_id")
        )
        effective_mta = (
            profile.get("mta_att_id")
            or a.get("mta_att_id")
        )

        if effective_mtmt:
            skipped += 1
            continue  # Already has ID

        print(f"\n{name} ({slug})")

        best_match = None
        best_score = 0.0
        best_family = best_given = ""

        for family, given in split_name(name):
            candidates = mtmt_search_by_family(family, given)
            if not candidates:
                continue
            for c in candidates:
                s = score_match(c, given, family)
                if s > best_score:
                    best_score = s
                    best_match = c
                    best_family = family
                    best_given = given
            if best_score >= 0.9:
                break
            time.sleep(0.3)

        if best_match and best_score >= 0.8:
            mtmt_id = str(best_match["mtid"])
            label = best_match.get("label", "")
            print(f"  ✅ Match (score={best_score:.2f}): {label} → mtmt_id={mtmt_id}")
            found += 1
            if not DRY_RUN:
                save_profile(slug, "mtmt_id", mtmt_id)
        elif best_match and best_score >= 0.5:
            label = best_match.get("label", "")
            print(f"  ⚠️  Uncertain (score={best_score:.2f}): {label} — skipped")
            missing += 1
        else:
            print(f"  ❌ Not found in MTMT")
            missing += 1

        time.sleep(0.4)

    print(f"\n--- Done: {found} found, {skipped} already had ID, {missing} not found ---")
    if DRY_RUN and found > 0:
        print("Run with --write to save results to profiles/")


if __name__ == "__main__":
    main()
