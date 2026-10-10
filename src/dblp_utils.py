# -*- coding: utf-8 -*-
"""
DBLP utilities module
Handles DBLP API queries, XML parsing, record caching, and author verification.
Restored version.
"""
import sys, os
_parent = os.path.dirname(os.path.dirname(__file__))
_src = os.path.dirname(__file__)
if _parent not in sys.path: sys.path.insert(0, _parent)
if _src not in sys.path: sys.path.insert(0, _src)

import json
import os
import requests
import xmltodict
from typing import Optional, Callable, Tuple, Any
import time
import urllib.parse
import urllib.request
import google_author_sheet
from urllib.parse import quote

SPARQL_ENDPOINT = "https://sparql.dblp.org/sparql"

def remove_accents(text: str) -> str:
    """Remove Hungarian (and other) accents from text for file naming."""
    from unidecode import unidecode
    return unidecode(text)

def _pid_to_uri(dblp_url: str) -> str:
    """Convert any DBLP URL form to a full https://dblp.org/pid/xx/yy URI."""
    if dblp_url.startswith("http"):
        return dblp_url.rstrip("/")
    if not dblp_url.startswith("/pid/"):
        dblp_url = "/pid" + dblp_url
    return f"https://dblp.org{dblp_url}"


def get_DBLP_record(dblp_url: str, author: str, force: bool = False) -> Optional[dict]:
    """Fetch author publications via DBLP SPARQL and cache under dblp/{author}.json.

    Returns a dict in the same xmltodict-compatible format as the old XML fetch:
      {"dblpperson": {"@name": ..., "@pid": ..., "r": [{"inproceedings": {...}}, ...]}}
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

    author_uri = _pid_to_uri(dblp_url)
    pid = author_uri.replace("https://dblp.org/pid/", "")

    query = f"""PREFIX dblp: <https://dblp.org/rdf/schema#>
SELECT ?pub ?type ?title ?year ?venue ?crossref ?pages ?doi ?authorName ?authorOrd ?authorPid WHERE {{
  ?pub dblp:authoredBy <{author_uri}> ;
       a ?type ;
       dblp:title ?title ;
       dblp:yearOfPublication ?year .
  FILTER(?type IN (dblp:Inproceedings, dblp:Article))
  OPTIONAL {{ ?pub dblp:publishedIn ?venue }}
  OPTIONAL {{ ?pub dblp:publishedAsPartOf ?crossref }}
  OPTIONAL {{ ?pub dblp:pagination ?pages }}
  OPTIONAL {{ ?pub dblp:doi ?doi }}
  OPTIONAL {{
    ?pub dblp:hasSignature ?sig .
    ?sig dblp:signatureDblpName ?authorName ;
         dblp:signatureOrdinal ?authorOrd .
    OPTIONAL {{ ?sig dblp:signaturePerson ?authorPid }}
  }}
}}
ORDER BY ?pub ?authorOrd
LIMIT 5000"""

    try:
        print(f"SPARQL: {author} ({pid})")
        req = urllib.request.Request(
            f"{SPARQL_ENDPOINT}?query={urllib.parse.quote(query)}",
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "NKFIH-author-tool/1.0 (mailto:tapolcai@tmit.bme.hu)",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        # Group rows by publication URI preserving order
        pub_order = []
        pubs: dict = {}
        for row in data["results"]["bindings"]:
            pub_uri = row["pub"]["value"]
            if pub_uri not in pubs:
                pub_order.append(pub_uri)
                is_inproc = "Inproceedings" in row["type"]["value"]
                crossref_uri = row.get("crossref", {}).get("value", "")
                crossref = crossref_uri.replace("https://dblp.org/rec/", "") if crossref_uri else ""
                pubs[pub_uri] = {
                    "is_inproc": is_inproc,
                    "key": pub_uri.replace("https://dblp.org/rec/", ""),
                    "title": row["title"]["value"],
                    "year": row["year"]["value"],
                    "venue": row.get("venue", {}).get("value", ""),
                    "crossref": crossref,
                    "pages": row.get("pages", {}).get("value", ""),
                    "doi": row.get("doi", {}).get("value", ""),
                    "authors": [],
                }
            if "authorName" in row:
                author_pid_uri = row.get("authorPid", {}).get("value", "")
                author_pid = author_pid_uri.replace("https://dblp.org/pid/", "") if author_pid_uri else ""
                pubs[pub_uri]["authors"].append((
                    int(row.get("authorOrd", {}).get("value", 99)),
                    row["authorName"]["value"],
                    author_pid,
                ))

        # Build r[] in xmltodict-compatible format
        records = []
        for pub_uri in pub_order:
            p = pubs[pub_uri]
            sorted_authors = [
                {"#text": name, "@pid": apid} if apid else name
                for _, name, apid in sorted(p["authors"])
            ]
            pub_type = "inproceedings" if p["is_inproc"] else "article"
            inner: dict = {
                "@key": p["key"],
                "author": sorted_authors,
                "title": p["title"],
                "year": p["year"],
                "crossref": p["crossref"],
                "pages": p["pages"],
                "ee": p["doi"],
            }
            if p["is_inproc"]:
                inner["booktitle"] = p["venue"]
            else:
                inner["journal"] = p["venue"]
            records.append({pub_type: inner})

        result = {"dblpperson": {"@name": author, "@pid": pid, "r": records}}
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  → {len(records)} pub")
        return result

    except Exception as e:
        print(f"SPARQL hiba ({author}): {e}")
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

def cache_DBLP_query(authors_data, force):
    """Refresh dblp/ cache for all authors using the SPARQL endpoint."""
    os.makedirs("dblp", exist_ok=True)
    os.makedirs("results", exist_ok=True)

    total   = len(authors_data)
    skipped = 0
    fetched = 0
    failed  = 0

    for i, (author, author_cls) in enumerate(authors_data.items(), 1):
        author_safe = google_author_sheet.remove_accents(author).replace(" ", "_")
        output_path = os.path.join("dblp", f"{author_safe}.json")

        if not force and os.path.exists(output_path):
            skipped += 1
            continue

        dblp_url = author_cls.get("dblp_url", "").strip()
        if not dblp_url:
            print(f"[{i}/{total}] Nincs DBLP URL: {author} — kihagyva")
            failed += 1
            continue

        result = get_DBLP_record(dblp_url, author, force=force)
        if result:
            fetched += 1
        else:
            failed += 1

    log = (f"DBLP SPARQL cache frissítés\n"
           f"Összesen: {total}, lekérve: {fetched}, kihagyva: {skipped}, hiba: {failed}\n")
    with open("results/log_dblp_fetch_log.txt", "w", encoding="utf-8") as f:
        f.write(log)
    print(f"DBLP cache kész — lekérve: {fetched}, kihagyva: {skipped}, hiba: {failed}")