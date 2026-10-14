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
import re
from pathlib import Path
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

def get_DBLP_record(dblp_url: str, author: str = "", force: bool = False) -> Optional[dict]:
    """Query DBLP for author/person data and cache results under dblp/{author}.json.

    Args:
        dblp_url: DBLP URL path (e.g. https://dblp.org/pid/xx/yy or /pid/xx/yy)
        author: Author name (used for cache filename)
        force: If True, ignore existing cache and refetch
    Returns:
        Parsed XML dict or None on failure.
    """
    base_dir = Path(__file__).resolve().parent.parent
    dblp_dir = base_dir / "dblp"
    dblp_dir.mkdir(parents=True, exist_ok=True)
    if author.strip() != "":
        author_safe = remove_accents(author).replace(" ", "_")
        file_path = dblp_dir / f"{author_safe}.json"

        if not force and Path(file_path).exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")

    if not dblp_url.startswith("http"):
        if dblp_url.startswith("/"):
            dblp_url_full = f"https://dblp.org/pid{dblp_url}"
        elif dblp_url.startswith("/dip/"):
            dblp_url_full = f"https://dblp.org{dblp_url}"
        else:
            dblp_url_full = f"https://dblp.org/pid/{dblp_url}"
    else:
        dblp_url_full = dblp_url


    #dblp_url_full = dblp_url_full.replace("https://dblp.org/", "https://dblp2.uni-trier.de/")

    try:
        print(f"Fetching: {author} {dblp_url_full}.xml")
        sys.sleep(1)  # Be polite to DBLP
        response = requests.get(f"{dblp_url_full}.xml")
        if response.status_code != 200:
            raise Exception(f"HTTP error {response.status_code}")
        data = xmltodict.parse(response.content)
        
        dblp_dir.mkdir(parents=True, exist_ok=True)
        if author.strip() == "":
            author=data.get("dblpperson", {}).get("@name", "unknown_author")
            print("Name: {} from DBLP record".format(author))
            

        author_safe = remove_accents(author).replace(" ", "_")
        file_path = dblp_dir / f"{author_safe}.json"
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

SPARQL_URL = "https://sparql.dblp.org/sparql"
SPARQL_TYPE_MAP = {
    "https://dblp.org/rdf/schema#Inproceedings": "Conference and Workshop Papers",
    "https://dblp.org/rdf/schema#Article": "Journal Articles",
    "https://dblp.org/rdf/schema#Editorship": "Editorship",
    "https://dblp.org/rdf/schema#Reference": "Reference Works",
    "https://dblp.org/rdf/schema#Informal": "Informal and Other Publications",
    "https://dblp.org/rdf/schema#Thesis": "Thesis",
}


def _sparql_count(pid):
    """Return total publication count for a PID via SPARQL (cheap check)."""
    query = (
        "SELECT (COUNT(DISTINCT ?pub) AS ?n) WHERE { "
        "?pub <https://dblp.org/rdf/schema#authoredBy> <https://dblp.org/pid/" + pid + "> }"
    )
    r = requests.post(SPARQL_URL, data={"query": query},
                      headers={"Accept": "application/sparql-results+json"}, timeout=30)
    r.raise_for_status()
    bindings = r.json().get("results", {}).get("bindings", [])
    return int(bindings[0]["n"]["value"]) if bindings else -1


def _sparql_fetch(pid, author_name=""):
    """Fetch all publications for a PID and return a dblpperson dict.

    Output format matches xmltodict-parsed PID XML so the existing
    classification pipeline (get_dblp_record / classify_paper) works unchanged.
    """
    author_uri = "https://dblp.org/pid/" + pid

    pubs_query = (
        "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
        "SELECT DISTINCT ?pub ?type ?title ?year ?venue ?doi ?pages WHERE {\n"
        "  ?pub dblp:authoredBy <" + author_uri + "> ;\n"
        "       dblp:title ?title ; dblp:yearOfPublication ?year .\n"
        "  OPTIONAL { ?pub a ?type .\n"
        "    FILTER(STRSTARTS(STR(?type),\"https://dblp.org/rdf/schema#\")"
        " && ?type != dblp:Publication) }\n"
        "  OPTIONAL { ?pub dblp:publishedIn ?venue }\n"
        "  OPTIONAL { ?pub dblp:doi ?doi }\n"
        "  OPTIONAL { ?pub dblp:pagination ?pages }\n"
        "}"
    )
    r = requests.post(SPARQL_URL, data={"query": pubs_query},
                      headers={"Accept": "application/sparql-results+json"}, timeout=60)
    r.raise_for_status()
    bindings = r.json()["results"]["bindings"]

    pubs = {}
    for b in bindings:
        uri = b["pub"]["value"]
        if uri not in pubs:
            pubs[uri] = b
        elif "type" in b and ("Inproceedings" in b["type"]["value"] or "Article" in b["type"]["value"]):
            pubs[uri] = b

    if not pubs:
        return {"dblpperson": {"@name": author_name, "r": []}}

    # Use dblp:hasSignature + dblp:ordinalNumber to preserve publication author order.
    # The plain dblp:authoredBy relation is an unordered RDF set; SPARQL returns
    # rows in non-deterministic order which scrambles author lists.
    authors_query = (
        "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
        "SELECT ?pub ?ord ?coAuthorName ?coAuthorPid WHERE {\n"
        "  ?pub dblp:authoredBy <" + author_uri + "> .\n"
        "  ?pub dblp:hasSignature ?sig .\n"
        "  ?sig dblp:signatureCreator ?co .\n"
        "  ?sig dblp:ordinalNumber ?ord .\n"
        "  ?co dblp:primaryCreatorName ?coAuthorName .\n"
        "  BIND(REPLACE(STR(?co),\"https://dblp.org/pid/\",\"\") AS ?coAuthorPid)\n"
        "} ORDER BY ?pub ?ord"
    )
    r2 = requests.post(SPARQL_URL, data={"query": authors_query},
                       headers={"Accept": "application/sparql-results+json"}, timeout=60)
    r2.raise_for_status()
    pub_authors: dict = {}
    seen_pairs: dict = {}
    bindings2 = r2.json()["results"]["bindings"]
    if not bindings2:
        # Fallback: dblp:hasSignature not available for these records; use
        # unordered dblp:authoredBy (legacy behaviour, order not guaranteed).
        authors_query_fallback = (
            "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
            "SELECT DISTINCT ?pub ?coAuthorName ?coAuthorPid WHERE {\n"
            "  ?pub dblp:authoredBy <" + author_uri + "> .\n"
            "  ?pub dblp:authoredBy ?co . ?co dblp:primaryCreatorName ?coAuthorName .\n"
            "  BIND(REPLACE(STR(?co),\"https://dblp.org/pid/\",\"\") AS ?coAuthorPid)\n"
            "}"
        )
        r2b = requests.post(SPARQL_URL, data={"query": authors_query_fallback},
                            headers={"Accept": "application/sparql-results+json"}, timeout=60)
        r2b.raise_for_status()
        bindings2 = r2b.json()["results"]["bindings"]
    for b in bindings2:
        uri = b["pub"]["value"]
        name = b["coAuthorName"]["value"]
        apid = b["coAuthorPid"]["value"]
        pub_authors.setdefault(uri, [])
        seen_pairs.setdefault(uri, set())
        if (name, apid) not in seen_pairs[uri]:
            pub_authors[uri].append({"#text": name, "@pid": apid})
            seen_pairs[uri].add((name, apid))

    # Build dblpperson.r list — same structure as xmltodict-parsed PID XML
    TYPE_TO_TAG = {
        "https://dblp.org/rdf/schema#Inproceedings": "inproceedings",
        "https://dblp.org/rdf/schema#Article": "article",
    }
    r_list = []
    for uri, b in pubs.items():
        rec_key = uri.replace("https://dblp.org/rec/", "")
        raw_type = b.get("type", {}).get("value", "")
        tag = TYPE_TO_TAG.get(raw_type, "informal")
        venue_key = "booktitle" if tag == "inproceedings" else "journal"
        doi_uri = b.get("doi", {}).get("value", "")
        paper = {
            "@key": rec_key,
            "title": b["title"]["value"].rstrip("."),
            venue_key: b.get("venue", {}).get("value", ""),
            "year": b["year"]["value"],
        }
        if b.get("pages"):
            paper["pages"] = b["pages"]["value"]
        if doi_uri:
            paper["ee"] = doi_uri
        authors = pub_authors.get(uri, [])
        if authors:
            paper["author"] = authors[0] if len(authors) == 1 else authors
        r_list.append({tag: paper})

    return {"dblpperson": {"@name": author_name, "r": r_list}}


def _sparql_fetch_hits(pid):
    """Legacy wrapper — returns raw hits list (result.hits format) for private pipeline."""
    author_uri = "https://dblp.org/pid/" + pid

    pubs_query = (
        "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
        "SELECT DISTINCT ?pub ?type ?title ?year ?venue ?doi ?pages WHERE {\n"
        "  ?pub dblp:authoredBy <" + author_uri + "> ;\n"
        "       dblp:title ?title ; dblp:yearOfPublication ?year .\n"
        "  OPTIONAL { ?pub a ?type .\n"
        "    FILTER(STRSTARTS(STR(?type),\"https://dblp.org/rdf/schema#\")"
        " && ?type != dblp:Publication) }\n"
        "  OPTIONAL { ?pub dblp:publishedIn ?venue }\n"
        "  OPTIONAL { ?pub dblp:doi ?doi }\n"
        "  OPTIONAL { ?pub dblp:pagination ?pages }\n"
        "}"
    )
    r = requests.post(SPARQL_URL, data={"query": pubs_query},
                      headers={"Accept": "application/sparql-results+json"}, timeout=60)
    r.raise_for_status()
    bindings = r.json()["results"]["bindings"]

    pubs = {}
    for b in bindings:
        uri = b["pub"]["value"]
        if uri not in pubs:
            pubs[uri] = b
        elif "type" in b and ("Inproceedings" in b["type"]["value"] or "Article" in b["type"]["value"]):
            pubs[uri] = b

    if not pubs:
        return []

    authors_query = (
        "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
        "SELECT DISTINCT ?pub ?coAuthorName ?coAuthorPid WHERE {\n"
        "  ?pub dblp:authoredBy <" + author_uri + "> .\n"
        "  ?pub dblp:authoredBy ?co . ?co dblp:primaryCreatorName ?coAuthorName .\n"
        "  BIND(REPLACE(STR(?co),\"https://dblp.org/pid/\",\"\") AS ?coAuthorPid)\n"
        "}"
    )
    r2 = requests.post(SPARQL_URL, data={"query": authors_query},
                       headers={"Accept": "application/sparql-results+json"}, timeout=60)
    r2.raise_for_status()
    pub_authors: dict = {}
    seen_pairs: dict = {}
    for b in r2.json()["results"]["bindings"]:
        uri = b["pub"]["value"]
        name = b["coAuthorName"]["value"]
        apid = b["coAuthorPid"]["value"]
        pub_authors.setdefault(uri, [])
        seen_pairs.setdefault(uri, set())
        if (name, apid) not in seen_pairs[uri]:
            pub_authors[uri].append({"text": name, "@pid": apid})
            seen_pairs[uri].add((name, apid))

    hits = []
    for uri, b in pubs.items():
        rec_key = uri.replace("https://dblp.org/rec/", "")
        raw_type = b.get("type", {}).get("value", "")
        pub_type = SPARQL_TYPE_MAP.get(raw_type, "Informal and Other Publications")
        doi_uri = b.get("doi", {}).get("value", "")
        doi = doi_uri.replace("https://doi.org/", "") if doi_uri else ""
        info = {
            "type": pub_type,
            "key": rec_key,
            "title": b["title"]["value"].rstrip("."),
            "venue": b.get("venue", {}).get("value", ""),
            "year": b["year"]["value"],
            "pages": b.get("pages", {}).get("value", ""),
            "doi": doi,
            "ee": doi_uri,
            "url": uri,
            "authors": {"author": pub_authors.get(uri, [])},
        }
        hits.append({"info": info})
    return hits


# search for an author
def cache_DBLP_query(authors_data, force):
    base_dir = Path(__file__).resolve().parent.parent
    dblp_dir = base_dir / "dblp"
    dblp_dir.mkdir(parents=True, exist_ok=True)

    counts_path = dblp_dir / "dblp_counts.json"
    counts_cache = {}
    if counts_path.exists():
        try:
            counts_cache = json.loads(counts_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    counter = 0
    for author, author_cls in authors_data.items():
        author_safe = google_author_sheet.remove_accents(author).replace(" ", "_")
        output_path = dblp_dir / "{}.json".format(author_safe)

        dblp_url_raw = author_cls.get("dblp_url", "").strip()
        if not dblp_url_raw:
            if not force and output_path.exists():
                continue
            print("No DBLP PID for {} — skip".format(author))
            continue

        # Extract PID (strip leading slash and dblp.org prefix)
        pid = re.sub(r"^https?://(?:www\.)?dblp\.(?:org|uni-trier\.de)/pid/", "", dblp_url_raw)
        pid = pid.strip("/").rstrip(".html").rstrip(".xml")
        if not pid:
            continue

        # Count check: skip if paper count unchanged and file exists
        if not force and output_path.exists():
            try:
                total = _sparql_count(pid)
                if total >= 0 and counts_cache.get(author_safe) == total:
                    continue
                counts_cache[author_safe] = total
            except Exception as e:
                print("Count check failed for {}: {}".format(author, e))
                continue  # keep existing file, try next time

        try:
            print("Fetching via SPARQL: {}".format(author), flush=True)
            data = _sparql_fetch(pid, author_name=author)
            time.sleep(0.5)
            counter += 1
            if counter % 50 == 0:
                print("Pause after {} queries".format(counter))
                time.sleep(30)

            r_list = data.get("dblpperson", {}).get("r", [])
            tmp = output_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(output_path)
            new_count = len(r_list)
            prev_count = counts_cache.get(author_safe)
            counts_cache[author_safe] = new_count
            if prev_count is not None and prev_count != new_count:
                print("{}: {} rekord (volt: {})".format(author, new_count, prev_count), flush=True)
            else:
                print("{}: {} rekord".format(author, new_count), flush=True)

        except Exception as e:
            print("Error with {}: {}".format(author, e))
            time.sleep(20)

    counts_path.write_text(json.dumps(counts_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DBLP JSON lekérések kész, elmentve: dblp/")