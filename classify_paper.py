# -*- coding: utf-8 -*-
"""Paper classification utilities.
Extracted from run_every_day.py to separate concerns.
"""
from typing import List, Tuple, Dict
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

_inputs_dir = "inputs"

def _load_list(filename: str) -> List[str]:
    path = os.path.join(_inputs_dir, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return []

regular_paper_list = _load_list("regular_paper_list.txt")
short_paper_list = _load_list("short_paper_list.txt")
no_hungarian_affil = _load_list("no_hungarian_affil_list.txt")
doi_short_paper_list = _load_list("doi_short_paper_list.txt")

core_table = pd.read_csv(os.path.join(_inputs_dir, "core_table.csv"))
# Convert acronyms to uppercase for case-insensitive matching
core_table["Acronym"] = core_table["Acronym"].str.upper()
core_table = core_table.set_index("Acronym", drop=False)

all_authors: List[Tuple[str, str]] = []
no_page_is_given: List[str] = []


def remove_numbers_and_parentheses(text: str) -> str:
    text = re.sub(r'\(\d+\)', '', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def core_rank(venue: str, pub_year: int) -> str:
    venue = remove_numbers_and_parentheses(venue).upper()
    if venue not in core_table.index:
        return "no_rank"
    acronym_row = core_table.loc[venue]
    core_ranks = acronym_row["YearsListed"].split(", ")
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


def get_int(text: str) -> int:
    if any(c.isalpha() for c in text):
        if 'vol' in text:
            text = text.split('vol')[0]
            if any(c.isalpha() for c in text):
                return 0
            return int(text)
        return 0
    return int(text)


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
    if rank_name not in ['B', 'C']:
        limit = 4
    if venue in ["SODA", "STOC", "FOCS"]:
        limit = 3
    if venue in ["MoDELS"]:
        limit = 7
    if venue in ["WWW"]:
        limit = 8
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
    if pages_str and (":" in pages_str or "-" in pages_str):
        if ":" not in pages_str:
            pages = re.split(r"[-:]", pages_str)
            if len(pages) > 1 and pages[1]:
                pagenum = get_int(pages[1]) - get_int(pages[0])
                if pagenum < limit:
                    return True
            else:
                return True
        else:
            parts = re.split(r"[-–]", pages_str)
            if len(parts) > 1:
                try:
                    start = int(re.findall(r"\d+", parts[0])[-1])
                    end = int(re.findall(r"\d+", parts[1])[-1])
                    pagenum = end - start + 1
                    if pagenum < limit:
                        return True
                except Exception:
                    return True
            else:
                return True
    else:
        if venue in ["ICML", "NeurIPS", "ICLR", "INTERSPEECH", "BMVC"]:
            return False
        if rank_name in ['B', 'C']:
            return False
        if title_val not in no_page_is_given:
            no_page_is_given.append(title_val)
        return True
    for doi_ in doi_short_paper_list:
        if doi_ in info.get("doi", ""):
            return True
    return False


def classify_paper(paper: Dict, search_log: str = ""):
    global all_authors
    if "inproceedings" not in paper:
        return None, None, None, False, False, search_log + "\n Skip as not inproceedings"
    info = paper["inproceedings"]
    foreign_paper = False
    short_paper = False
    title = info.get("title", "N/A")
    venue = info.get("booktitle", "")
    year = int(info.get("year", 0))
    rank = core_rank(venue, year)
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
    if info.get("title", "") in no_hungarian_affil:
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
