#!/usr/bin/env python3
"""Convert google_sheet_full_updated.csv to authors.json for git-based editing."""
import csv
import json
import re
import unicodedata
import sys
from pathlib import Path

CSV_IN = Path(__file__).parent.parent / "coreA" / "corePaperList-old" / "google_sheet_full_updated.csv"
JSON_OUT = Path(__file__).parent / "authors.json"

# Override input/output via CLI args
if len(sys.argv) > 1:
    CSV_IN = Path(sys.argv[1])
if len(sys.argv) > 2:
    JSON_OUT = Path(sys.argv[2])


def slugify(name: str) -> str:
    """Convert author name to URL-safe slug."""
    s = unicodedata.normalize("NFKD", name)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s


def extract_mtmt_id(url_or_id: str) -> str:
    """Extract numeric MTMT ID from URL or plain number."""
    if not url_or_id:
        return ""
    m = re.search(r"/(\d+)$", url_or_id.strip())
    return m.group(1) if m else url_or_id.strip()


def safe_int(v: str) -> int | None:
    try:
        return int(str(v).strip()) if str(v).strip() else None
    except (ValueError, TypeError):
        return None


def safe_float(v: str) -> float | None:
    try:
        return round(float(str(v).strip()), 4) if str(v).strip() else None
    except (ValueError, TypeError):
        return None


def convert(csv_path: Path, json_path: Path):
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    authors = []
    seen_slugs: dict[str, int] = {}

    for row in rows:
        name = row.get("Author", "").strip()
        if not name:
            continue

        base_slug = slugify(name)
        if base_slug in seen_slugs:
            seen_slugs[base_slug] += 1
            slug = f"{base_slug}-{seen_slugs[base_slug]}"
        else:
            seen_slugs[base_slug] = 1
            slug = base_slug

        entry = {
            "slug": slug,
            "name": name,
            "dblp_url": row.get("DBLP URL", "").strip(),
            "dblp_alias": row.get("DBLP alias", "").strip(),
            "mtmt_id": extract_mtmt_id(row.get("MTMT id", "")),
            "mta_att_id": row.get("MTA ATT id", "").strip(),
            "mtmt_name": row.get("MTMT name", "").strip(),
            "category": row.get("Category", "").strip(),
            "mtmt_status": row.get("MTMT Status", "").strip(),
            "works": row.get("Works", "").strip(),
            "affiliations": row.get("Affiliations", "").strip(),
            "dblp_institutions": row.get("DBLP Intézmény", "").strip(),
            # Paper counts
            "core_astar": safe_int(row.get("Core A*")),
            "core_a": safe_int(row.get("Core A")),
            "core_astar_papers": safe_int(row.get("Core A* Papers")),
            "core_a_papers": safe_int(row.get("Core A Papers")),
            "core_b": safe_int(row.get("Core B")),
            "core_c": safe_int(row.get("Core C")),
            "no_core": safe_int(row.get("No Core")),
            # Equivalents
            "hungarian_core_astar_equiv": safe_float(row.get("Hungarian Core A* equivalent")),
            "core_astar_equiv": safe_float(row.get("Core A* equivalent")),
            "first_author_core_astar_equiv": safe_float(row.get("First Author Core A* equivalent")),
            # MTMT metrics
            "mtmt_journals": safe_int(row.get("MTMT Journal Publications")),
            "mtmt_conferences": safe_int(row.get("MTMT Conference Publications")),
            "mtmt_citations": safe_int(row.get("MTMT Total Citations")),
            "mtmt_d1_equiv": safe_float(row.get("MTMT Journal D1 Equivalents")),
            "mtmt_d1": safe_int(row.get("MTMT Journal D1")),
            "mtmt_q1": safe_int(row.get("MTMT Journal Q1")),
            "mtmt_q2": safe_int(row.get("MTMT Journal Q2")),
            "mtmt_q3": safe_int(row.get("MTMT Journal Q3")),
            "mtmt_q4": safe_int(row.get("MTMT Journal Q4")),
            "mtmt_affiliations": row.get("MTMT Affiliations", "").strip(),
            # Hungarian academic metadata
            "research_field": row.get("Aktuális fokozat szakterülete", "").strip(),
            "research_topic": row.get("Kutatási téma", "").strip(),
            "mta_committee": row.get("MTA Bizottság", "").strip(),
            "contact": row.get("Elérhetőségek", "").strip(),
            "degree": row.get("Aktuális fokozat", "").strip(),
            "memberships": row.get("Szervezeti tagságok", "").strip(),
            "phd_year": safe_int(row.get("PhD éve")),
            "occupation": row.get("Foglalkozás", "").strip(),
            "years_since_phd": safe_int(row.get("Years Since PhD")),
            "age_group": row.get("Age Group", "").strip(),
            "born": row.get("Született", "").strip(),
            "mta_membership": row.get("MTA tagság", "").strip(),
            "mta_photo": row.get("MTA kép", "").strip(),
            "awards": row.get("Díjak", "").strip(),
            # Rankings
            "category_astar_rank": safe_int(row.get("Category Core A* Rank")),
            "age_astar_rank": safe_int(row.get("Age Group Core A* Rank")),
        }
        # Strip None values to keep JSON compact
        entry = {k: v for k, v in entry.items() if v is not None and v != ""}
        authors.append(entry)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(authors, f, ensure_ascii=False, indent=2)

    print(f"Converted {len(authors)} authors → {json_path}")
    print(f"Sample slugs: {[a['slug'] for a in authors[:5]]}")


if __name__ == "__main__":
    convert(CSV_IN, JSON_OUT)
