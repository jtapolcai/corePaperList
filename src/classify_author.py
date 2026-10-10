# -*- coding: utf-8 -*-
"""Author classification utilities.
Extracted from run_every_day.py to separate concerns.
"""
import sys, os
_parent = os.path.dirname(os.path.dirname(__file__))
_src = os.path.dirname(__file__)
if _parent not in sys.path: sys.path.insert(0, _parent)
if _src not in sys.path: sys.path.insert(0, _src)

from typing import Dict, Tuple
import google_author_sheet

import unicodedata

# Shared mutable state (initialized externally)
authors_data: Dict[str, Dict] = {}
pid_to_name: Dict[str, str] = {}
norm_name_to_data: Dict[str, Tuple[str, Dict]] = {}  # normalised_name → (canonical_name, data)


def _norm(name: str) -> str:
    name = name.strip()
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def reset_state():
    """Reset in-memory maps (useful for tests)."""
    authors_data.clear()
    pid_to_name.clear()


def create_pid_to_name_map(authors_data_input: Dict[str, Dict]) -> None:
    """Populate pid_to_name map from authors_data.
    Avoid rebuilding if already populated.
    """
    global pid_to_name, authors_data, norm_name_to_data
    if pid_to_name:
        return
    authors_data = authors_data_input
    for name, data in authors_data.items():
        pid = data.get("dblp_url", "").strip()
        if pid:
            if pid in pid_to_name and pid_to_name[pid] != name:
                print(f"Warning: Duplicate DBLP PID {pid} for authors {pid_to_name[pid]} and {name}")
            pid_to_name[pid] = name
        norm_name_to_data[_norm(name)] = (name, data)


def has_worked_in_hungary(author_name: str) -> bool:
    """Quick affiliation presence check for author."""
    global authors_data
    author_key = google_author_sheet.remove_accents(author_name)
    info = authors_data.get(author_key)
    if not info:
        return False
    locs = info.get("location", [])
    return bool(locs)


def classify_author(author_name: str, pid: str, year: int) -> Dict[str, str]:
    """Classify author by location (Hungary) + institution/department/category.
    If PID maps to a known name with Hungarian year-range, return details.
    """
    global authors_data, pid_to_name, norm_name_to_data
    if len(pid_to_name) == 0:
        authors_data=google_author_sheet.download_author_google_sheet()
        create_pid_to_name_map(authors_data)

    def _check_info(author_info):
        if author_info and "location" in author_info:
            for location in author_info["location"]:
                if "Hungary" in location and google_author_sheet.is_year_range(location, year):
                    return {
                        "location": "Hungary",
                        "institution": author_info.get("institution", "Unknown"),
                        "department": author_info.get("department", "Unknown"),
                        "category": author_info.get("category", "Unknown"),
                    }
        return None

    # 1. PID lookup (exact)
    pid_key = pid if pid.startswith('/') else f"/{pid}"
    if pid and pid_key in pid_to_name:
        result = _check_info(authors_data.get(pid_to_name[pid_key], {}))
        if result:
            return result

    # 2. Name-based fallback (diacritics-stripped, case-insensitive)
    norm = _norm(author_name)
    if norm in norm_name_to_data:
        _, author_info = norm_name_to_data[norm]
        result = _check_info(author_info)
        if result:
            return result

    return {
        "location": "Unknown",
        "institution": "Unknown",
        "department": "Unknown",
        "category": "Unknown",
    }

