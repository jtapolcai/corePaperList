# -*- coding: utf-8 -*-
"""
DBLP utilities module
Handles DBLP API queries, XML parsing, record caching, and author verification.
Restored version.
"""
import json
import os
import requests
import xmltodict
from typing import Optional, Callable, Tuple, Any
import time
import google_author_sheet
from urllib.parse import quote

def remove_accents(text: str) -> str:
    """Remove Hungarian (and other) accents from text for file naming."""
    from unidecode import unidecode
    return unidecode(text)

def get_DBLP_record(dblp_url: str, author: str, force: bool = False) -> Optional[dict]:
    """Query DBLP for author/person data and cache results under dblp/{author}.json.

    Args:
        dblp_url: DBLP URL path (e.g. https://dblp.org/pid/xx/yy or /pid/xx/yy)
        author: Author name (used for cache filename)
        force: If True, ignore existing cache and refetch
    Returns:
        Parsed XML dict or None on failure.
    """
    os.makedirs("dblp", exist_ok=True)
    author_safe = remove_accents(author).replace(" ", "_")
    file_path = os.path.join("dblp", f"{author_safe}.json")

    if not force and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    # Normalize URL (allow passing '/pid/xx/yy')
    if not dblp_url.startswith("http"):
        dblp_url_full = f"https://dblp.org{dblp_url}"
    else:
        dblp_url_full = dblp_url

    try:
        print(f"Fetching: {author} {dblp_url_full}.xml")
        response = requests.get(f"{dblp_url_full}.xml")
        if response.status_code != 200:
            raise Exception(f"HTTP error {response.status_code}")
        data = xmltodict.parse(response.content)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data
    except Exception as e:
        print(f"Error fetching {dblp_url_full}: {e}")
        return None

def search_dblp_by_name(name_for_search: str,
                        mtmt_record: dict, pub_rec: list) :
    """Search DBLP author API by name (with '+' separators) and verify candidate hits.

    Returns first matching DBLP record dict or None.
    """
    url = f"https://dblp.org/search/author/api?q={name_for_search}&format=json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            result = response.json()
            hits = result.get("result", {}).get("hits", {}).get("hit", [])
            for hit in hits:
                info = hit.get("info", {})
                dblp_record = get_DBLP_record(info.get("url", ""), info.get("author", "author"), force=True)
                if dblp_record:
                    similarity = is_same_dblp_and_mtmt_records(dblp_record, mtmt_record, pub_rec)
                    if similarity>=0.5:
                        return dblp_record, similarity
        else:
            print(f"HTTP hiba DBLP keresésnél {name_for_search}: {response.status_code}")
    except Exception as e:
        print(f"Hiba DBLP keresésnél {name_for_search}: {e}")
    return None, 0.0

def find_dblp_by_name(mtmt_record: dict, pub_rec: list):
    """Try the full MTMT given + family name, then component combinations if needed."""
    family = mtmt_record.get("familyName", "")
    given = mtmt_record.get("givenName", "")
    full = f"{given} {family}".strip()
    query = full.replace(" ", "+")
    ret, similarity = search_dblp_by_name(query, mtmt_record, pub_rec)
    if ret and similarity> 0.5:
        return ret
    print(f"Trying alternative name combinations for {full} DBLP search for mtmt {mtmt_record.get('mtid', '')} ")
    best_dbl=None
    best_similarity=0.0
    if not ret and (len(given.split()) > 2 or len(family.split()) > 2):
        for g_part in given.split():
            for f_part in family.split():
                alt = f"{g_part}+{f_part}"
                ret, similarity = search_dblp_by_name(alt, mtmt_record, pub_rec)
                if similarity> best_similarity:
                    best_dbl = ret
                    best_similarity = similarity
                    if similarity>0.5:
                        return best_dbl
    if best_similarity>0.5:
        return best_dbl
    if not ret and len(family.split()) >= 1:
        for f_part in family.split():
            alt = f"{f_part}"
            ret, similarity = search_dblp_by_name(alt, mtmt_record, pub_rec)
            if similarity> best_similarity:
                best_dbl = ret
                best_similarity = similarity
                if similarity>0.5:
                    return best_dbl
    return best_dbl


def extract_affiliation_info(dblp_record: dict) -> Tuple[str, str]:
    """Extract affiliation info from top-level note fields.

    Returns (affiliation_string, location_flag) where location_flag in {'hungary','abroad',''}.
    """
    if not dblp_record:
        return "", ""
    root = dblp_record.get("dblpperson", dblp_record)
    notes = root.get("note", [])
    if isinstance(notes, dict):
        notes = [notes]
    for note in notes:
        if "affiliation" in note:
            affil = note["affiliation"].lower()
            label = note.get("@label", "").lower()
            entry = affil if not label else f"{affil} ({label})"
            if any(x in affil for x in ["budapest", "hungary", "magyarország", "szeged", "egyetem", "renyi"]):
                return entry, "hungary"
            return entry, "abroad"
    return "", ""

def compare_dblp_paper_to_mtmt(paper: dict,
                               mtmt_record: dict,
                               find_mtmt_papers_by_title_func: Callable[[str, str, str, str], Tuple[str, Optional[str]]]) -> bool:
    """Given a single DBLP paper entry and an MTMT record, attempt to validate authorship by title lookup."""
    if not paper:
        return False
    title = ""
    if "article" in paper:
        title = paper["article"].get("title", "")
    if "inproceedings" in paper:
        title = paper["inproceedings"].get("title", title)
    if isinstance(title, dict):
        return False
    if title:
        if title.endswith('.'):
            title = title[:-1]
        status, alt_id = find_mtmt_papers_by_title_func(title, mtmt_record.get("mtid", ""), mtmt_record.get("familyName", ""), mtmt_record.get("givenName", ""))
        if status == 'same_author':
            return True
        if status == 'same_name_different_author' and alt_id:
            print(f"Could be confused with MTMT IDs: {alt_id}")
            return False
    return False

def is_same_dblp_and_mtmt_records(dblp_record: dict,
                                  mtmt_record: dict, pub_rec: list) -> float:
    """Iterate papers in DBLP record until a confirming match is found in MTMT."""
    if not dblp_record or not mtmt_record or not pub_rec:
        return 0.0
    root = dblp_record.get("dblpperson", dblp_record)
    papers = root.get("r", [])
    titles=[]
    mtmt_papers = mtmt_record if isinstance(mtmt_record, list) else [mtmt_record]
    for paper in pub_rec:
        title=paper.get('title','')
        if title and title not in titles:
            titles.append(title)

    found=0
    if isinstance(papers, list):
        for  paper_dict in papers:
            if 'inporceedings' in paper_dict:
                paper=paper_dict['inproceedings']
            elif 'article' in paper_dict:
                paper=paper_dict['article']
            if paper is not None:
                if 'title' in paper:
                    if isinstance(paper['title'], dict):
                        title=paper['title'].get('#text','')
                    else:
                        title=paper.get('title', '')
                    if title.endswith('.'):
                        title=title[:-1]
                    if title in titles:
                        found+=1
        if found<len(titles) // 2 and found>0:
            print(f"Potenciális DBLP és MTMT rekord (talált: {found} / {len(titles)}) {root['@name']}")
            if found >=5:
                return  0.4 + 0.6 * found / len(titles)
        if found>0:
            return 0.3 + 0.7 * found / len(titles)
    else:
        title=papers.get('title', '') if 'title' in papers else ''
        if title in titles:
            return 1.0
    return 0.0

def check_if_dblp_id_corresponds_to_mtmt(mtmt_id: str,
                                         author_name: str,
                                         get_mtmt_record_func: Optional[Callable[..., Optional[dict]]] = None,
                                         get_dblp_record_func: Optional[Callable[..., Optional[dict]]] = None,
                                         is_same_func: Optional[Callable[..., bool]] = None,
                                         magyar_nev: Optional[str] = None) -> Tuple[Optional[dict], Optional[dict]]:
    """High-level verification helper combining MTMT + DBLP records.

    Returns (dblp_record, mtmt_record) if matching, else (None, None).
    """
    mtmt_record = None
    if get_mtmt_record_func:
        try:
            mtmt_record = get_mtmt_record_func(mtmt_id, author_name)
            # handle tuple returns (author, publications)
            if isinstance(mtmt_record, tuple):
                mtmt_record = mtmt_record[0]
        except Exception:
            mtmt_record = None
    if not mtmt_record:
        print(f"MTMT record not found for ID: {mtmt_id}")
        return None, None
    if magyar_nev:
        fam = mtmt_record.get('familyName', '').lower()
        giv = mtmt_record.get('givenName', '').lower()
        if fam not in magyar_nev.lower() and giv not in magyar_nev.lower():
            print(f"MTMT record name does not match the provided Hungarian name: {magyar_nev}")
            return None, None
    dblp_record = None
    if get_dblp_record_func:
        dblp_record = get_dblp_record_func(author_name)
    if not dblp_record:
        print(f"DBLP record not found for author: {author_name}")
        return None, None
    if is_same_func and is_same_func(dblp_record, mtmt_record):
        return dblp_record, mtmt_record
    return None, None

def cache_DBLP_query(authors_data,force): 
    os.makedirs("dblp", exist_ok=True)

    full_log = ""
    counter = 0

    for author, author_cls in authors_data.items():
        #if not author_cls.get("location"):
        #    full_log += "{} is not working in Hungary\n".format(author)
        #    continue

        # we save the reuslts as dblp/author_name.json
        author_safe = google_author_sheet.remove_accents(author).replace(" ", "_")
        output_path = os.path.join("dblp", "{}.json".format(author_safe))

        if not force and os.path.exists(output_path):
            #print(f"Skip {author} (already exists)")
            continue

        author_query = google_author_sheet.remove_accents(author)
        if "dblp_url" in author_cls and author_cls.get("dblp_url", "").strip() != "":
            pid = author_cls.get("dblp_url", "").strip()
            url = "https://dblp.org/pid{}.xml".format(pid)
        else:
            print("No pid for {}, using name search".format(author))
            url = "https://dblp.org/search/publ/api?q=author:{}&h=1000&format=xml".format(quote(author_query))
        
        try:
            print("Fetching: {}".format(author))
            time.sleep(0.5)
            response = requests.get(url)
            counter += 1

            if counter % 50 == 0:
                print("Pause after {} queries".format(counter))
                time.sleep(30)
            if counter % 1000 == 0:
                print("Too many queries – exiting")
                break

            if response.status_code != 200:
                raise Exception("HTTP error {}".format(response.status_code))

            data = xmltodict.parse(response.content)
            #data = response.json()
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print("Error with {}: {}".format(author,e))
            time.sleep(20)

    # Log mentése
    with open("dblp_fetch_log.txt", "w", encoding="utf-8") as f:
        f.write(full_log)

    print("DBLP JSON lekérések kész, elmentve: dblp/")