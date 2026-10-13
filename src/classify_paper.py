# -*- coding: utf-8 -*-
"""Paper classification utilities.
Extracted from run_every_day.py to separate concerns.
"""
import sys, os
_parent = os.path.dirname(os.path.dirname(__file__))
if _parent not in sys.path: sys.path.insert(0, _parent)

from typing import List, Tuple, Dict, Optional
from functools import lru_cache
import csv
import re
import os
import json
from pathlib import Path
import pandas as pd
from collections import defaultdict
import google_author_sheet
# Import from src to ensure we use the same module instance as run_every_day
from src import classify_author

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

_BASE_DIR = Path(__file__).resolve().parent.parent
_inputs_dir = _BASE_DIR / "inputs"

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

journal_proceedings = {}

@lru_cache(maxsize=1)
def get_core_tables():
    """
    Lazily load and build the core tables only when needed.
    Returns:
        dblp_venue_to_rows, acronym_to_row, core_table
    """
    global journal_proceedings
    import pandas as pd
    # Try both 'inputs/core_table.csv' and '../inputs/core_table.csv' relative to this file
    candidate_paths = [
        str(_inputs_dir / "core_table.csv"),
        str(Path(__file__).resolve().parent.parent / 'inputs' / 'core_table.csv')
    ]
    core_table_path = None
    for path in candidate_paths:
        if os.path.exists(path):
            core_table_path = path
            break
    if core_table_path is None:
        raise FileNotFoundError(f"The core_table.csv file does not exist in any of: {candidate_paths}")
    # Read core table robustly: try default parser, then python engine, then csv.reader fallback
    try:
        core_table = pd.read_csv(core_table_path, dtype=str)
    except Exception:
        try:
            core_table = pd.read_csv(core_table_path, dtype=str, engine='python')
        except Exception:
            # fallback to csv.reader which is more permissive about line breaks if quoting is inconsistent
            with open(core_table_path, newline='', encoding='utf-8') as f:
                rows = list(csv.reader(f))
            if not rows:
                core_table = pd.DataFrame()
            else:
                header = rows[0]
                data = rows[1:]
                core_table = pd.DataFrame(data, columns=header)

    # Normalize Acronym to uppercase for case-insensitive matching
    if "Acronym" in core_table.columns:
        core_table["Acronym"] = (
            core_table["Acronym"].fillna("").astype(str).str.upper()
        )
    # Build dblp_venue-indexed table with expansion
    dblp_venue_to_rows = {}
    # for row without dblp_venue
    acronym_to_row= {}
    if "dblp_venue" not in core_table.columns or "Acronym" not in core_table.columns:
        print("Warning: core_table.csv is missing expected columns 'dblp_venue' or 'Acronym'.")
    else:
        for _, row in core_table.iterrows():
            venues_field = row.get("dblp_venue")
            if pd.isna(venues_field) or str(venues_field).strip() == "":
                acr_field = row.get("Acronym", "")
                if pd.isna(acr_field):
                    continue
                for ac in str(acr_field).split(";"):
                    ac = ac.strip().upper()
                    if not ac:
                        continue
                    if ac in acronym_to_row:
                        print("Warning: duplicate Acronym key {} in core table".format(ac))
                    acronym_to_row[ac] = row
                continue
            for key in str(venues_field).split(";"):
                key = key.strip()
                if not key:
                    continue
                if not key.startswith("conf/"):
                    if key not in journal_proceedings:
                        journal_proceedings[key] = row.get("rules", "")
                    elif journal_proceedings[key] != row.get("rules", ""):
                        print("Warning: conflicting rules for journal {}: '{}' vs '{}'".format(
                            key, journal_proceedings[key], row.get("rules", "") ))
                if key not in dblp_venue_to_rows:
                    dblp_venue_to_rows[key] = []
                dblp_venue_to_rows[key].append(row)

    return dblp_venue_to_rows, acronym_to_row, core_table

all_authors: List[Tuple[str, str]] = []
# auxiliary set for O(1) membership checks to avoid O(n^2) behavior
_all_authors_set = set(all_authors)
no_page_is_given: List[str] = []

dblp_venue_to_rows, acronym_to_row, core_table = get_core_tables()

def remove_numbers_and_parentheses(text: str) -> str:
    # remove any parenthesised suffixes (e.g. "(Companion)") and digits
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    text=text.replace("()", "").strip()
    return text



def get_core_rank(pub: dict) -> Tuple[str, bool]:
    year = int(pub.get("year", 0))
    # Extract venue key from paper key or crossref
    if "crossref" in pub:
        venue_crossref = pub["crossref"]
    elif "@key" in pub:
        venue_crossref = pub["@key"]
        pub["crossref"] = pub["@key"]
    elif "key" in pub:
        venue_crossref = pub["key"]
        pub["crossref"] = pub["key"]
    venue_dblp = ""
    if venue_crossref:
        venue_dblp = '/'.join(venue_crossref.split('/')[:2])
    else:
        key = pub.get("key", "")
        if key:
            venue_dblp = '/'.join(key.split('/')[:2])

    venue_name = pub.get("venue", "")

    # Determine rank using the normalized dblp/acronym lookup
    rank, short_paper, acronym_row = core_rank(venue_name, venue_crossref, venue_dblp, year)

    # If the core table provides a fullpaper threshold for this venue, use it
    threshold = None
    if acronym_row is not None:
        try:
            if hasattr(acronym_row, 'get'):
                thr = acronym_row.get('fullpaper_threshold')
            else:
                thr = None
            if thr is not None and str(thr).strip() != "":
                threshold = int(str(thr).strip())
        except Exception:
            threshold = None

    if not short_paper and threshold is not None:
        pages_str = pub.get("pages", "")
        pagenum = get_paper_length(pages_str)
        if pagenum is None:
        #    print(f"No page number for {pub}")
            pass
        elif pagenum < threshold:
            short_paper = True

    return rank, short_paper

def adjust_rank(last_rank: str, short_paper) -> str:
    global short_paper_rank
    if short_paper:
        if last_rank in short_paper_rank:
            return short_paper_rank[last_rank]
    return last_rank

acronym_to_crossref={}

def identify_conference(venue_name: str, venue_crossref, venue_dblp: str):
    global acronym_to_crossref, dblp_venue_to_rows, acronym_to_row
    acronym_row = None
    short_paper=False
    # Check for companion/workshop indicators before normalization
    venue_name_upper = venue_name.upper()
    # @ symbol indicates workshop (e.g., "SESENA@ICSE")
    is_companion_or_workshop = '@' in venue_name or any(keyword in venue_name_upper for keyword in 
                                     ['COMPANION', 'WORKSHOP', 'POSTER', 'DEMO', 'FORUM', 'SHORT PAPER', 
                                'FINDING', 'DEMONSTRATION','INDUSTRY','TUTORIAL','STUDENT','LINGUISTIC', 'ADJUNCT',
                                 'DOCTORAL', 'SUPPLEMENTS', '(LATE BREAKING','(LATE-BREAKING','(SHOWCASES', '(LOCAL PROCEEDINGS',
                                  '(PRACTITIONER PROCEEDINGS)', 'PANEL', 'SPECIAL TRACK ON APPLICATIONS',
                                  '(EDUCATION', 'ART SHOW CATALOG', 'VISUAL PROCEEDINGS','(INFORMAL',
                                  'SATELLITE EVENTS','(SATELLITES)', 'SUPPLEMENTAL', 'TECHNICAL COMMUNICATIONS', 
                                  '(CHALLENGE', '(SHORT','(PHD)' 
                                  ])
    if venue_name in ['Comput. Graph. Forum', 'Australasian Transport Research Forum','Asia-Pacific Forum on Engineering and Technology Education']: 
        is_companion_or_workshop = False

    # Check if crossref indicates workshop (e.g., "conf/re/2023w" ends with 'w', "conf/caise/2011fo" ends with 'fo')
    if venue_crossref:
        crossref_parts = venue_crossref.split('/')
        if len(crossref_parts) >= 3:
            last_part = crossref_parts[-1]
            # Workshop indicators in crossref: ends with 'w', 'workshops', 'fo' (forum), or contains workshop/companion/demo/poster keywords
            if (last_part.endswith('w') or last_part.endswith('workshops') or last_part.endswith('fo') or
                any(kw in last_part.lower() for kw in ['workshop', 'companion', 'demo', 'poster', 'forum'])):
                is_companion_or_workshop = True
    
    if is_companion_or_workshop:
        short_paper = True
    venue_name = remove_numbers_and_parentheses(venue_name).upper()
    if venue_crossref:
        venue_key = '/'.join(venue_crossref.split('/')[:2])
        if venue_key not in dblp_venue_to_rows:
            if venue_name in acronym_to_row:
                # There may be multiple rows for the same acronym; iterate all and
                # apply the same checks for each matching row instead of only the first.
                acronym_matches = acronym_to_row[venue_name]
                if isinstance(acronym_matches, pd.DataFrame):
                    # If any matching row has a non-empty dblp_venue, we consider
                    # that a mismatch for the given crossref and bail out (preserve
                    # previous conservative behavior). Otherwise record crossref mapping.
                    for _, acr_row in acronym_matches.iterrows():
                        venues_field = acr_row.get("dblp_venue")
                        if not pd.isna(venues_field) and str(venues_field).strip() != "":
                            return None, short_paper
                    # all matching acronym rows had empty dblp_venue -> map crossref
                    if venue_name not in acronym_to_crossref:
                        acronym_to_crossref[venue_name] = venue_key
                    else:
                        if venue_key not in acronym_to_crossref[venue_name].split(';'):
                            acronym_to_crossref[venue_name] += ';' + venue_key
                    acronym_row = acronym_matches.iloc[0]
                else:
                    acronym_row = acronym_matches
                    venues_field = acronym_row.get("dblp_venue")
                    if not pd.isna(venues_field) and str(venues_field).strip() != "":
                        return None, short_paper
                    if venue_name not in acronym_to_crossref:
                        acronym_to_crossref[venue_name] = venue_key
                    else:
                        if venue_key not in acronym_to_crossref[venue_name].split(';'):
                            acronym_to_crossref[venue_name] += ';' + venue_key

        else:
            for acr_row in dblp_venue_to_rows[venue_key]:
                # If multiple rows match the dblp key, prefer a row whose Acronym
                # explicitly contains the normalized venue name. Evaluate all rows
                # to decide short_paper conservatively.
                acronym_list = acr_row.get("Acronym", "")
                acronyms = [a.strip() for a in str(acronym_list).split(';') if a.strip()]
                for ac in acronyms:
                    if ac.upper() == venue_name.upper():
                        return acr_row, short_paper
                acronym_row=acr_row    
            short_paper = True
    return acronym_row, short_paper
    
def core_rank(venue_name: str, venue_crossref, venue_dblp: str, pub_year: int) -> Tuple[str, bool, Optional[pd.Series]]:
    """Determine CORE rank using the dblp_venue key (already normalized in the table).

    Falls back to "no_rank" safely if:
      - venue_dblp not in index
      - YearsListed column missing or empty
      - Unexpected format encountered
    """
    acronym_row, short_paper = identify_conference(venue_name, venue_crossref, venue_dblp)
    if acronym_row is None:
        return "no_rank", False, None
    # If multiple rows match, take the first
    if isinstance(acronym_row, pd.DataFrame):
        acronym_row = acronym_row.iloc[0]
    core_ranks_str = acronym_row.get("YearsListed", "")
    if not isinstance(core_ranks_str, str) or not core_ranks_str.strip():
        return "no_rank", False, acronym_row
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
            year = int(parts[0].replace("ICORE", "").replace("CORE", "").replace("ERA", ""))
        except ValueError:
            continue
        rank = parts[1]
        # Normalize rank labels: any variant containing 'UNRANK' maps to 'no_rank'
        rank_norm = rank.strip()
        if 'UNRANK' in rank_norm.upper():
            rank_norm = 'no_rank'
        if year!=2013:
            average_rank += rank_to_value.get(rank_norm, 0)
            count+=1
        if not return_average_rank:
            if first_year is None:
                first_year = year
                if pub_year <= first_year:
                    return_average_rank=True
        if pub_year <= year and not return_average_rank:
            # Historical special case retained
            if year == 2013 and rank_norm == "A*":
                return rank_norm, short_paper, acronym_row
            return last_rank, short_paper, acronym_row
        last_rank = rank_norm
    if return_average_rank and count>0:
        avg_value=average_rank/count
        avg_value_rounded=round(avg_value)
        last_rank=value_to_rank.get(avg_value_rounded, "no_rank")
    return last_rank, short_paper, acronym_row


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
        author_cls = classify_author.classify_author(author, pid, year)
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



def classify_paper(paper: Dict, search_log: str = "", skip_author_check: bool = False):
    global all_authors, journal_proceedings
    record_type="inproceedings"
    if "inproceedings" not in paper:
        if "article" in paper:
            article=paper["article"]
            crossref='/'
            if "crossref" in article:
                crossref=article["crossref"]
            elif "@key" in article:
                crossref=article["@key"]
            crossref_short='/'.join(crossref.split('/')[:2])
            if crossref_short in journal_proceedings:
                record_type="article"
                rule=journal_proceedings[crossref_short]
                if rule.startswith("number="):
                    if "number" in paper["article"]:
                        number_val = paper["article"]["number"]
                        try:
                            number_int = int(re.findall(r"\d+", str(number_val))[0])
                            threshold = int(rule.split('=')[1])
                            if number_int != threshold:
                                return None, None, None, False, False, search_log + f"\n Skip as journal {crossref_short} with number {number_int} above threshold {threshold}", None
                        except Exception:
                            print(f"Warning: could not parse number '{number_val}' or threshold in rule '{rule}' for journal {crossref_short}")
                else:
                    print(f"Warning: unrecognized rule format '{rule}' for journal {crossref_short}")
            else:
                return None, None, None, False, False, search_log + "\n Skip as not journal inproceedings", None
        else:
            return None, None, None, False, False, search_log + "\n Skip as not inproceedings", None
    info = paper[record_type]
    foreign_paper = False
    short_paper = False
    title = info.get("title", "N/A")
    if record_type=="inproceedings":
        venue = info.get("booktitle", "")
    else:
        venue = info.get("journal", "")
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
    if "crossref" in info:
        record["crossref"] = info["crossref"]
    elif "key" in info:
        record["crossref"] = info["key"]
    elif "@key" in info:
        record["crossref"] = info["@key"]
    rank, short_paper = get_core_rank(record)

    if record_type=="article":
        short_paper = False

    if not skip_author_check:
        # Authors
        author_list_raw = info.get("author", [])
        if isinstance(author_list_raw, list):
            author_list: List[Tuple[str, str]] = []
            for a in author_list_raw:
                author_name = a.get("#text", "")
                author_pid = a.get("@pid", "")
                author_tuple = (author_name, author_pid)
                if author_tuple not in _all_authors_set:
                    all_authors.append(author_tuple)
                    _all_authors_set.add(author_tuple)
                author_list.append(author_tuple)
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
        return key, record, rank, False, False, search_log + f"\n no rank for venue {venue}", "no_rank"
    
    # # Store original rank before degradation for short_papers tracking
    original_rank = rank
    # if not short_paper:
    #     short_paper_flag, short_paper_reason = is_short_paper(info, venue, rank, year)
    # else:
    #     short_paper_flag = True
    #     short_paper_reason = "Identified as short paper from venue/acronym analysis"
    #if short_paper_flag:
    if short_paper:    
        short_paper = True
        search_log += f"\n Short paper {paper_str}"
        record["short_paper_reason"] = "Identified as short paper" #short_paper_reason
        rank = short_paper_rank[rank]
    else:
        search_log += f"\n Full paper {paper_str}"
    return key, record, rank, foreign_paper, short_paper, search_log, original_rank


def process_paper(paper: Dict, papers: Dict, search_log: str = "", foreign_papers=None, short_papers=None):
    key, record, rank, foreign_paper, short_paper, search_log, original_rank = classify_paper(paper, search_log)
    if not rank:
        return search_log, papers, foreign_papers, short_papers
    # Only add to papers dict if it's NOT a foreign paper (i.e., it has Hungarian affiliation)
    if not foreign_paper and key and rank in papers and key not in papers[rank]:
        papers[rank][key] = record
    # Add to foreign_papers dict if it IS a foreign paper
    if foreign_paper and foreign_papers is not None and rank in foreign_papers:
        if key and key not in foreign_papers[rank]:
            foreign_papers[rank][key] = record
    # Add to short_papers dict if it's a short paper (use original rank before degradation)
    if short_paper and short_papers is not None and original_rank in short_papers:
        if key and key not in short_papers[original_rank]:
            short_papers[original_rank][key] = record
    return search_log, papers, foreign_papers, short_papers

if __name__ == "__main__":
    rec = {"article": {
          "@key": "journals/cgf/abc24",
          "author": [],
          "title": "This should be classied as Rank A",
          "pages": "63-74",
          "year": "2020",
          "volume": "37",
          "journal": "Comput. Graph. Forum",
          "number": "2",
          "crossref": "journals/cgf/vc1",
        } }
    # rec= {"inproceedings": {
    #       "author": [
    #       ],
    #       "title": "This should be classied as Rank A*",
    #       "pages": "449-456",
    #       "year": "2003",
    #       "crossref": "conf/visualization/2003",
    #       "booktitle": "IEEE Visualization"
    #     }}
    rec= {"inproceedings": {
          "author": [
          ],
          "title": "This should be classied as Rank A*",
          "pages": "449-456",
          "year": "2003",
          "crossref": "conf/acl/2003",
          "booktitle": "ACL/IJCNLP (Findings)"
        }}
    key, record, rank, foreign_paper, short_paper, search_log, original_rank = classify_paper(rec)
    print(f"Key: {key}")
    print(f"Record: {record}")
    print(f"Rank: {rank}")
    print(f"Original rank: {original_rank}")
    print(f"Foreign paper: {foreign_paper}")
    print(f"Short paper: {short_paper}")
    print(f"Search log: {search_log}")