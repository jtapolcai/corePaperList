# -*- coding: utf-8 -*-
"""Paper classification utilities.
Extracted from run_every_day.py to separate concerns.
"""
from typing import List, Tuple, Dict, Optional
import re
import os
import json
import pandas as pd
from collections import defaultdict
import google_author_sheet
from classify_author import classify_author

# Constants and loaded resources
short_paper_rank = {
    'A*': 'B',
    'A': 'C',
    'B': 'C',
    'C': 'C'
}

rank_to_value = {
    'A*': 4,
    'A': 3,
    'B': 2,
    'C': 1
}
value_to_rank = {v: k for k, v in rank_to_value.items()}    

_inputs_dir = "inputs"

def _load_list(filename: str) -> List[str]:
    path = os.path.join(_inputs_dir, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            #return [line.strip() for line in f if line.strip()]
            return json.load(f)
    return []

regular_paper_list = _load_list("regular_paper_list.txt")
short_paper_list = _load_list("short_paper_list.txt")
no_hungarian_affil = _load_list("no_hungarian_affil_list.txt")
doi_short_paper_list = _load_list("doi_short_paper_list.txt")

# Load core table and prepare two indexed variants:
#  - core_table_by_dblp_venue: indexed by 'dblp_venue' (DBLP-style keys), expands ';'-separated lists
#  - core_table_by_acronym: indexed by 'Acronym' (uppercased), expands ';'-separated lists
core_table_raw = pd.read_csv(os.path.join(_inputs_dir, "core_table.csv"))

# Normalize Acronym to uppercase for case-insensitive matching
if "Acronym" in core_table_raw.columns:
    core_table_raw["Acronym"] = (
        core_table_raw["Acronym"].fillna("").astype(str).str.upper()
    )

# Build dblp_venue-indexed table with expansion
_df = core_table_raw.copy()
if "dblp_venue" in _df.columns:
    expanded_rows = []
    for _, row in _df.iterrows():
        venues_field = row.get("dblp_venue")
        if pd.isna(venues_field) or str(venues_field).strip() == "":
            continue
        for key in str(venues_field).split(";"):
            key = key.strip()
            if not key:
                continue
            r = row.copy()
            r["dblp_venue"] = key
            expanded_rows.append(r)
    if expanded_rows:
        core_table_by_dblp_venue = pd.DataFrame(expanded_rows)
    else:
        core_table_by_dblp_venue = _df.copy()
else:
    core_table_by_dblp_venue = _df.copy()

core_table_by_dblp_venue = core_table_by_dblp_venue.set_index("dblp_venue", drop=False)

# Build Acronym-indexed table with expansion (supports ';' separated acronyms)
_df2 = core_table_raw.copy()
expanded_acr_rows = []
if "Acronym" in _df2.columns:
    for _, row in _df2.iterrows():
        acr_field = row.get("Acronym", "")
        if pd.isna(acr_field):
            continue
        for ac in str(acr_field).split(";"):
            ac = ac.strip().upper()
            if not ac:
                continue
            r = row.copy()
            r["Acronym"] = ac
            expanded_acr_rows.append(r)
    if expanded_acr_rows:
        core_table_by_acronym = pd.DataFrame(expanded_acr_rows)
    else:
        core_table_by_acronym = _df2.copy()
else:
    core_table_by_acronym = _df2.copy()

core_table_by_acronym = core_table_by_acronym.set_index("Acronym", drop=False)

# Backward-compatible alias (historically dblp_venue indexed)
core_table = core_table_by_dblp_venue
# Expand semicolon-separated dblp_venue entries into multiple rows
core_table_acronym=core_table.copy()
expanded_rows = []
for _, row in core_table.iterrows():
    venues_field = row.get("Acronym")
    if pd.isna(venues_field):
        continue
    for key in str(venues_field).split(";"):
        key = key.strip()
        if not key:
            continue
        r = row.copy()
        r["dblp_venue"] = key
        expanded_rows.append(r)
if expanded_rows:
    core_table = pd.DataFrame(expanded_rows)

# Index by dblp_venue for fast lookup using DBLP-style venue keys
core_table = core_table.set_index("dblp_venue", drop=False)

all_authors: List[Tuple[str, str]] = []
no_page_is_given: List[str] = []


def remove_numbers_and_parentheses(text: str) -> str:
    text = re.sub(r'\(\d+\)', '', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def core_rank_old(venue: str, pub_year: int) -> str:
    venue = remove_numbers_and_parentheses(venue).upper()
    if venue not in core_table_by_acronym.index:
        return "no_rank"
    acronym_row = core_table_by_acronym.loc[venue]
    # Handle case where loc returns a Series (multiple rows) vs a single row
    if isinstance(acronym_row, pd.DataFrame):
        acronym_row = acronym_row.iloc[0]
    core_ranks_str = acronym_row["YearsListed"]
    core_ranks = core_ranks_str.split(", ")
    last_rank = "no_rank"
    first_year = None
    for cr in core_ranks:
        parts = cr.split("_")
        if len(parts) != 2:
            continue
        year = int(parts[0].replace("CORE", "").replace("ERA", ""))
        rank = parts[1]
        if first_year is None:
            first_year = year
            if pub_year <= first_year:
                return rank
        if pub_year < year:
            if year == 2013 and rank == "A*":
                return rank
            return last_rank
        last_rank = rank
    return last_rank

def get_core_rank(pub: dict) -> str:
    year=int(pub.get("year", 0))
    venue_dblp=pub.get("url", "")
    venue_crossref=pub.get("crossref", "")
    if venue_crossref:
        venue_crossref_short='/'.join(venue_crossref.split('/')[:2]) 
        if venue_dblp != venue_crossref_short:
            #print(f"Figyelem: eltérés a URL és crossref között: {venue_dblp} vs {venue_crossref_short}")
            venue_dblp=venue_crossref_short
    else:
        venue_crossref='/'.join(venue_dblp.split('/')[1:3]) 
    venue_name=pub.get("venue", "")
    rank = core_rank(venue_name, venue_crossref, venue_dblp, year)
    return rank

def core_rank(venue_name: str, venue_crossref, venue_dblp: str, pub_year: int) -> str:
    """Determine CORE rank using the dblp_venue key (already normalized in the table).

    Falls back to "no_rank" safely if:
      - venue_dblp not in index
      - YearsListed column missing or empty
      - Unexpected format encountered
    """
    ret="no_rank"
    acronym_row = None
    short_paper=False
    venue_name = remove_numbers_and_parentheses(venue_name).upper()
    if venue_crossref:
        venue_key = '/'.join(venue_crossref.split('/')[:2])
        if venue_key not in core_table_by_dblp_venue.index:
            if venue_name in core_table_by_acronym.index:
                acronym_row = core_table_by_acronym.loc[venue_name]
            else:
                ret="no_rank"
        try:
            acronym_row = core_table_by_dblp_venue.loc[venue_key]
            if isinstance(acronym_row, pd.DataFrame):
                acronym_row = acronym_row.iloc[0]
            acronym_= acronym_row.get("Acronym", "")
            if acronym_:
                acronyms = [a.strip() for a in acronym_.split(';')]
                if venue_name not in acronyms:
                    short_paper=True
                else:
                    if venue_name in core_table_by_acronym.index:
                        acronym_row = core_table_by_acronym.loc[venue_name]
        except KeyError:
            return "no_rank"
    if acronym_row is None:
        return "no_rank"
    # If multiple rows match, take the first
    if isinstance(acronym_row, pd.DataFrame):
        acronym_row = acronym_row.iloc[0]
    core_ranks_str = acronym_row.get("YearsListed", "")
    if not isinstance(core_ranks_str, str) or not core_ranks_str.strip():
        return "no_rank"
    core_ranks = [s.strip() for s in core_ranks_str.split(",") if s.strip()]
    last_rank = "no_rank"
    first_year = None
    average_rank=0
    count=0
    return_average_rank=False
    for cr in core_ranks:
        parts = cr.split("_")
        if len(parts) != 2:
            continue
        # Defensive parse; skip if year not int
        try:
            year = int(parts[0].replace("CORE", "").replace("ERA", ""))
        except ValueError:
            continue
        rank = parts[1]
        if year!=2013:
            average_rank += rank_to_value.get(rank, 0)
            count+=1
        if not return_average_rank:
            if first_year is None:
                first_year = year
                if pub_year <= first_year:
                    return_average_rank=True
        if pub_year <= year:
            # Historical special case retained
            if year == 2013 and rank == "A*":
                return rank
            return last_rank
        last_rank = rank
    if return_average_rank and count>0:
        avg_value=average_rank/count
        avg_value_rounded=round(avg_value)
        last_rank=value_to_rank.get(avg_value_rounded, "no_rank")
    if short_paper:
        if last_rank in short_paper_rank:
            return short_paper_rank[last_rank]
    return last_rank

def get_int(text: str) -> int:
    # Handle dot separator (e.g., "7.13" -> 13)
    if '.' in text:
        text = text.split('.')[-1]
    
    if any(c.isalpha() for c in text):
        if 'vol' in text:
            text = text.split('vol')[0]
            if any(c.isalpha() for c in text):
                return 0
            return int(text)
        return 0
    try:
        return int(text)
    except ValueError:
        print(f"Warning: could not convert '{text}' to int.")
        return 0


def get_paper_length(pages_str: str) -> Optional[int]:
    """
    Calculate paper length from page string.
    Returns number of pages, or None if cannot determine.
    """
    if not pages_str:
        return None
    
    if ":" not in pages_str:
        pages = re.split(r"[-:]", pages_str)
        if len(pages) > 1 and pages[1]:
            try:
                pagenum = get_int(pages[1]) - get_int(pages[0])
                return pagenum
            except:
                return None
        else:
            return None
    else:
        parts = re.split(r"[-–]", pages_str)
        if len(parts) > 1:
            try:
                start = int(re.findall(r"\d+", parts[0])[-1])
                end = int(re.findall(r"\d+", parts[1])[-1])
                pagenum = end - start + 1
                return pagenum
            except Exception:
                return None
        else:
            return None


def author_string(author_field) -> str:
    if isinstance(author_field, list):
        author_names = []
        for a in author_field:
            if isinstance(a, dict):
                author_name = a.get("#text", "")
            else:
                author_name = str(a)
            author_names.append(author_name)
        return ", ".join(author_names)
    elif isinstance(author_field, dict):
        return author_field.get("#text", "")
    return str(author_field)


def classify_paper_by_author(author_list: List[Tuple[str, str]], year: int, ignore_affiliations: bool = False) -> List[str]:
    hungarian = 0
    not_hungarian = 0
    ret: List[str] = []
    theory = 0
    applied = 0
    for author, pid in author_list:
        author_cls = classify_author(author, pid, year)
        if not ignore_affiliations:
            if author_cls["location"] == "Hungary":
                hungarian += 1
                for field in ["institution", "department"]:
                    val = author_cls.get(field, "Unknown")
                    if val != "Unknown" and val not in ret:
                        ret.append(val)
            else:
                not_hungarian += 1
        if author_cls["category"] == "theory":
            theory += 1
        elif author_cls["category"] == "applied":
            applied += 1
    if not ignore_affiliations:
        if hungarian == 0:
            return ret
        if hungarian <= not_hungarian:
            ret.append("international")
        elif not_hungarian == 0:
            ret.append("all_hungarian")
        else:
            ret.append("mostly_hungarian")
    ret.append("theory" if theory > applied else "applied")
    return ret


def is_short_paper(info: Dict, venue: str, rank_name: str) -> bool:
    limit = 6
    if rank_name in ['A']:
        limit = 5
    if rank_name in ['B', 'C']:
        limit = 4
    if venue in ["SODA", "STOC", "FOCS"]:
        limit = 3
    # if venue in ["MoDELS"]:
    #     limit = 7
    # if venue in ["WWW"]:
    #     limit = 8
    if "Workshop" in venue:
        return True
    title_val = info.get("title", "N/A")
    if isinstance(title_val, dict):
        title_val = title_val.get("text", "N/A")
    for t in regular_paper_list:
        if t.startswith(title_val):
            return False
    for t in short_paper_list:
        if t.startswith(title_val):
            return True
    pages_str = info.get("pages", "")
    pagenum = get_paper_length(pages_str)
    
    if pagenum is None or pagenum <= 0:
        # Cannot determine page count
        if venue in ["ICML", "NeurIPS", "ICLR", "INTERSPEECH", "BMVC","DSN"]:
            return False
        if rank_name in ['B', 'C']:
            return False
        if title_val not in no_page_is_given:
            no_page_is_given.append(title_val)
        return True
    else:
        # Have valid page count
        if pagenum < limit:
            return True
    for doi_ in doi_short_paper_list:
        if doi_ in info.get("doi", ""):
            return True
    return False


def classify_paper(paper: Dict, search_log: str = "", skip_author_check: bool = False):
    global all_authors
    if "inproceedings" not in paper:
        return None, None, None, False, False, search_log + "\n Skip as not inproceedings"
    info = paper["inproceedings"]
    foreign_paper = False
    short_paper = False
    title = info.get("title", "N/A")
    venue = info.get("booktitle", "")
    year = int(info.get("year", 0))
    record: Dict[str, object] = {}
    key = info.get("@key", "")
    record["key"] = key
    record["title"] = title
    record["venue"] = venue
    record["year"] = str(year)
    record["pages"] = info.get("pages", "")
    record["doi"] = info.get("doi", "")
    record["ee"] = info.get("ee", "")
    record["url"] = info.get("url", "")
    record["crossref"] = info.get("crossref", "")
    rank = get_core_rank(record)
    if not skip_author_check:
        # Authors
        author_list_raw = info.get("author", [])
        if isinstance(author_list_raw, list):
            author_list: List[Tuple[str, str]] = []
            for a in author_list_raw:
                author_name = a.get("#text", "")
                author_pid = a.get("@pid", "")
                if (author_name, author_pid) not in all_authors:
                    all_authors.append((author_name, author_pid))
                author_list.append((author_name, author_pid))
        else:
            author_list = [(author_list_raw.get("#text", ""), author_list_raw.get("@pid", ""))]
        record["authors"] = author_list
        authors_str = ", ".join([a[0] for a in author_list])
        ptype = classify_paper_by_author(author_list, year)
        record["classfiied"] = ptype
        paper_str = f"{venue} {year} {authors_str} - {title} "
    title=info.get("title", "")
    if isinstance(title, dict):
        title=title.get("text","")
    if not skip_author_check:
        if title in no_hungarian_affil:
            foreign_paper = True
            search_log += f"\n No hungarian affiliation {info.get('title', '')}"
        if len(ptype) == 0:
            foreign_paper = True
            search_log += f"\n No hungarian authors {paper_str}"
    if rank == "no_rank":
        return key, record, rank, False, False, search_log + f"\n no rank for venue {venue}"
    if is_short_paper(info, venue, rank):
        short_paper = True
        search_log += f"\n Short paper {paper_str}"
        rank = short_paper_rank[rank]
    else:
        search_log += f"\n Full paper {paper_str}"
    return key, record, rank, foreign_paper, short_paper, search_log


def process_paper(paper: Dict, papers: Dict, search_log: str = "", foreign_papers=None, short_papers=None):
    key, record, rank, foreign_paper, short_paper, search_log = classify_paper(paper, search_log)
    if not rank:
        return search_log, papers, foreign_papers, short_papers
    # Only add to papers dict if it's NOT a foreign paper (i.e., it has Hungarian affiliation)
    if not foreign_paper and key and rank in papers and key not in papers[rank]:
        papers[rank][key] = record
    # Add to foreign_papers dict if it IS a foreign paper
    if foreign_paper and foreign_papers is not None and rank in foreign_papers:
        if key and key not in foreign_papers[rank]:
            foreign_papers[rank][key] = record
    # Add to short_papers dict if it's a short paper (regardless of affiliation)
    if short_paper and short_papers is not None and rank in short_papers:
        if key and key not in short_papers[rank]:
            short_papers[rank][key] = record
    return search_log, papers, foreign_papers, short_papers

if __name__ == "__main__":
    rec= {}
    key, record, rank, foreign_paper, short_paper, search_log = classify_paper(rec)
    print(f"Key: {key}")
    print(f"Record: {record}")
    print(f"Rank: {rank}")
    print(f"Foreign paper: {foreign_paper}")
    print(f"Short paper: {short_paper}")
    print(f"Search log: {search_log}")