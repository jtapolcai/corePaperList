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

# Shared mutable state (initialized externally)
authors_data: Dict[str, Dict] = {}
pid_to_name: Dict[str, str] = {}


def reset_state():
    """Reset in-memory maps (useful for tests)."""
    authors_data.clear()
    pid_to_name.clear()


def create_pid_to_name_map(authors_data_input: Dict[str, Dict]) -> None:
    """Populate pid_to_name map from authors_data.
    Avoid rebuilding if already populated.
    """
    global pid_to_name, authors_data
    if pid_to_name:
        return
    authors_data = authors_data_input
    for name, data in authors_data.items():
        pid = data.get("dblp_url", "").strip()
        if not pid:
            continue
        if pid in pid_to_name and pid_to_name[pid] != name:
            print(f"Warning: Duplicate DBLP PID {pid} for authors {pid_to_name[pid]} and {name}")
        pid_to_name[pid] = name


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
    global authors_data, pid_to_name
    if len(pid_to_name) == 0:
        # pid_to_name should be populated via create_pid_to_name_map() before calling this.
        # Fallback (standalone use): load from authors.json.
        import json, re as _re
        try:
            with open('authors.json', encoding='utf-8') as _f:
                _authors = json.load(_f)
            for _a in _authors:
                _name = _a.get('name', '').strip()
                if not _name:
                    continue
                _url = _a.get('dblp_url', '')
                _pid = _re.sub(r'^https?://(?:www\.)?dblp\.(?:org|uni-trier\.de)(?:/pid)?', '', _url).strip()
                if _pid:
                    pid_to_name[_pid] = _name
                _works = _a.get('works')
                _inst = _a.get('affiliations', '')
                if not isinstance(_inst, str):
                    _inst = _inst[0] if _inst else ''
                authors_data[_name] = {
                    'dblp_url': _pid,
                    'location': ['Hungary'] if _works in ('hungary', 'company_hungary') else [],
                    'institution': _inst or 'Unknown',
                    'department': 'Unknown',
                    'category': _a.get('category') or 'Unknown',
                }
        except Exception as _e:
            print(f"classify_author fallback load failed: {_e}")
    # PIDs in pid_to_name already have the "/" prefix
    pid_key = pid if pid.startswith('/') else f"/{pid}"
    if pid and pid_key in pid_to_name:
        mapped_name = pid_to_name[pid_key]
        author_info = authors_data.get(mapped_name, {})
        if author_info:
            if "location" in author_info:
                for location in author_info["location"]:
                    if "Hungary" in location and google_author_sheet.is_year_range(location, year):
                        return {
                            "location": "Hungary",
                            "institution": author_info.get("institution", "Unknown"),
                            "department": author_info.get("department", "Unknown"),
                            "category": author_info.get("category", "Unknown"),
                        }
    return {
        "location": "Unknown",
        "institution": "Unknown",
        "department": "Unknown",
        "category": "Unknown",
    }

