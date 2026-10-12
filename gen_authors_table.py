#!/usr/bin/env python3
"""
Generate authors_table.html from authors.json + profiles/.
Wrapper around src/create_itable.py that maps authors.json field names
to the format create_itable.main() expects.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
AUTHORS_JSON = BASE / "authors.json"
PROFILES_DIR = BASE / "profiles"


def load_profiles(profiles_dir: Path) -> tuple[dict, set]:
    profiles: dict = {}
    file_backed: set = set()
    if not profiles_dir.exists():
        return profiles, file_backed
    bulk_file = profiles_dir / "_works_overrides.json"
    if bulk_file.exists():
        try:
            for slug, fields in json.loads(bulk_file.read_text(encoding="utf-8")).items():
                profiles.setdefault(slug, {}).update(fields)
        except Exception as e:
            print(f"Warning: {bulk_file}: {e}")
    for f in profiles_dir.glob("*.json"):
        if f.stem.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            profiles[f.stem] = {**profiles.get(f.stem, {}), **data}
            file_backed.add(f.stem)
        except Exception as e:
            print(f"Warning: {f}: {e}")
    return profiles, file_backed


EDITABLE_FIELDS = [
    "dblp_url", "mtmt_id", "mtmt_name", "mta_att_id", "mta_photo",
    "category", "mtmt_status", "works", "affiliations", "age_group",
    "linkedin", "homepage", "note",
]


def enrich_mta_photos(authors: list, profiles_dir: Path) -> list:
    """Apply MTA photo URLs from profiles/_mta_photos.json cache."""
    cache_file = profiles_dir / "_mta_photos.json"
    if not cache_file.exists():
        return authors
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return authors
    for a in authors:
        if a.get("mta_photo"):
            continue
        photo = cache.get(a.get("slug", ""), "")
        if photo:
            a["mta_photo"] = photo
    return authors


def to_itable_format(authors: list, profiles: dict) -> dict:
    """Convert authors list + profiles to the dict format create_itable expects."""
    result = {}
    for a in authors:
        slug = a.get("slug", "")
        # Apply profile overrides
        if slug in profiles:
            p = profiles[slug]
            for k in EDITABLE_FIELDS:
                if k in p and p[k] not in (None, ""):
                    a = dict(a)  # copy
                    a[k] = p[k]

        name = a.get("name", "")
        mtmt_id = a.get("mtmt_id") or ""
        mtmt_url = f"https://m2.mtmt.hu/api/author/{mtmt_id}" if mtmt_id else ""

        # Map authors.json → create_itable field names
        rec = {
            "dblp_author_name":               name,
            "slug":                            slug,
            "dblp_url_":                       a.get("dblp_url") or "",
            "mtmt_id_":                        mtmt_url,
            "mta_att_id_":                     a.get("mta_att_id") or "",
            "mta_image_":                      a.get("mta_photo") or "",
            "affiliations_":                   a.get("affiliations") or "",
            "mtmt_affiliations_":              "",
            "mta_elerhetosegek":               "",
            "mtmt_name":                       a.get("mtmt_name") or "",
            "institution":                     _parse_institution(a.get("affiliations") or ""),
            "works":                           a.get("works") or "",
            "status":                          a.get("mtmt_status") or "",
            "location":                        a.get("affiliations") or "",
            "category":                        a.get("category") or "",
            "Career Length":                   a.get("age_group") or "",
            "mta_topic":                       "",
            "mta_bizottság":                   "",
            "mta_szervezeti_tagsagok":         "",
            "Years Since PhD":                 "",
            "mta_tud_fokozat":                 "",
            "mta_foglalkozas":                 "",
            # Aggregate metrics
            "Core A* equivalent":              a.get("core_astar_equiv") or "",
            "Hungarian Core A* equivalent":    a.get("hungarian_core_astar_equiv") or "",
            "First Author Core A* equivalent": a.get("first_author_core_astar_equiv") or "",
            "mtmt_journal D1 eqvivalents_":    a.get("mtmt_d1_equiv") or "",
            # Paper counts
            "paper_countA*":                   a.get("core_astar") or "",
            "papersA*":                        "",
            "paper_countA":                    a.get("core_a") or "",
            "papersA":                         "",
            "paper_countB":                    a.get("core_b") or "",
            "papersB":                         "",
            "paper_countC":                    a.get("core_c") or "",
            "papersC":                         "",
            "paper_countno_rank":              a.get("no_core") or "",
            "papersno_rank":                   "",
            # Hungarian paper counts
            "hungarian_paper_countA*":         a.get("hung_core_astar") or "",
            "hungarian_papersA*":              "",
            "hungarian_paper_countA":          a.get("hung_core_a") or "",
            "hungarian_papersA":               "",
            "hungarian_paper_countB":          a.get("hung_core_b") or "",
            "hungarian_papersB":               "",
            "hungarian_paper_countC":          a.get("hung_core_c") or "",
            "hungarian_papersC":               "",
            "hungarian_paper_countno_rank":    a.get("hung_no_core") or "",
            "hungarian_papersno_rank":         "",
            # First author counts
            "first_author_paper_countA*":      a.get("first_author_core_astar") or "",
            "first_author_papersA*":           "",
            "first_author_paper_countA":       a.get("first_author_core_a") or "",
            "first_author_papersA":            "",
            "first_author_paper_countB":       a.get("first_author_core_b") or "",
            "first_author_papersB":            "",
            "first_author_paper_countC":       a.get("first_author_core_c") or "",
            "first_author_papersC":            "",
            "first_author_paper_countno_rank": a.get("first_author_no_core") or "",
            "first_author_papersno_rank":      "",
            # MTMT counts
            "mtmt_citations_":                 a.get("mtmt_citations") or "",
            "mtmt_d1_papers_":                 "",
            "mtmt_d1_count_":                  "",
        }
        result[slug or name] = rec
    return result


def _parse_institution(affiliations: str) -> str:
    """Extract primary institution abbreviation from affiliations string."""
    INST_KEYWORDS = {
        "BME": "BME", "ELTE": "ELTE", "SZTE": "SZTE", "Rényi": "Rényi",
        "SZTAKI": "SZTAKI", "Ericsson": "Ericsson", "Corvinus": "Corvinus",
        "PPKE": "PPKE", "ÓE": "ÓE", "Miskolc": "ME",
    }
    for kw, abbr in INST_KEYWORDS.items():
        if kw in affiliations:
            return abbr
    return affiliations.split("-")[0].split()[0] if affiliations else ""


def main():
    authors = json.loads(AUTHORS_JSON.read_text(encoding="utf-8"))
    profiles, _ = load_profiles(PROFILES_DIR)
    authors = enrich_mta_photos(authors, PROFILES_DIR)
    data = to_itable_format(authors, profiles)
    print(f"Loaded {len(data)} authors from authors.json + profiles/")

    # Import and run create_itable
    sys.path.insert(0, str(BASE / "src"))
    from create_itable import main as itable_main
    itable_main(data)


if __name__ == "__main__":
    main()
