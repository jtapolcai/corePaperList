# -*- coding: utf-8 -*-
"""
MTMT utilities module
Handles MTMT (Magyar Tudományos Művek Tára) API queries, record fetching, and validation.
"""
import datetime
import os
import json
import requests
import time

from typing import Optional, Tuple



    
def get_mtmt_record(mtmt_id: str, force: bool = False, author_name: Optional[str] = None) -> Tuple[dict, list]:
    """Fetch MTMT author record by ID.
    
    Args:
        mtmt_id: MTMT author identifier
        
    Returns:
        dict: MTMT author record or None on error
    """
    # Cache setup: store combined author+publications under mtmt/{mtmt_id}.json
    #if author_name:
        # Simple diagnostic; could be extended for per-author logging
    #    print(f"Loading MTMT record for {author_name} (ID {mtmt_id})")
    cache_dir = "mtmt"
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{mtmt_id}.json")

    # Try cache first
    if os.path.exists(cache_path) and not force:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            author_cached = cached.get("author", {})
            pubs_cached = cached.get("publications", {})
            return author_cached, pubs_cached
        except Exception as e:
            # Non-fatal: fall back to live fetch
            print(f"⚠️ Cache read error for MTMT {mtmt_id}: {e}")

    mtmt_url = f"https://m2.mtmt.hu/api/author/{mtmt_id}?format=json"
    mtmt_url_pub = f"https://m2.mtmt.hu/api/publication?cond=authors;eq;{mtmt_id}&format=json&labelLang=hun&size=500&sort=publishedYear,desc"
    try:
        response = requests.get(mtmt_url, timeout=10)
        if response.status_code == 200:
            result = response.json()
            author_record = result.get("content", {})
        else:
            print(f"HTTP hiba MTMT URL lekérésnél {mtmt_id}: {response.status_code}")
        response = requests.get(mtmt_url_pub, timeout=10)
        if response.status_code == 200:
            result_pub = response.json()
            author_record_pub = result_pub.get("content", {})
        else:
            print(f"HTTP hiba MTMT URL2 lekérésnél {mtmt_id}: {response.status_code}")
        # Write/update cache
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"author": author_record, "publications": author_record_pub}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Cache write error for MTMT {mtmt_id}: {e}")
        return author_record, author_record_pub
    except Exception as e:
        print(f"Hiba MTMT URL lekérésnél {mtmt_id}: {e}")
    # On error, return empty dicts to satisfy return type
    return {}, {} # type: ignore


def find_mtmt_papers_by_title(title_orig, mtmt_id, family_name=None, given_name=None):
    """Search MTMT for papers by title and verify authorship.
    
    Args:
        title_orig: Paper title to search
        mtmt_id: MTMT ID of expected author
        family_name: Optional family name for disambiguation
        given_name: Optional given name for disambiguation
        
    Returns:
        tuple: (status, alternative_id) where status is one of:
            'same_author', 'different_author', 'same_name_different_author',
            'no_paper_found', 'no_response'
    """
    title = title_orig.strip(' .')
    title = title.replace(' ', '%20')
    url = f"https://m2.mtmt.hu/api/publication?format=json&cond=title;eq;{title}"
    
    try:
        response_ = requests.get(url, timeout=10)
        if response_.status_code == 200:
            response = response_.json()
            if "content" in response:
                papers = response["content"]
                for paper in papers:
                    if "authorships" in paper:
                        for author in paper["authorships"]:
                            if "author" in author:
                                mtmt_authors = author["author"]
                                if mtmt_authors["mtid"] == mtmt_id:
                                    return 'same_author', None
                                elif family_name and given_name:
                                    if (mtmt_authors['familyName'].lower() in family_name.lower() and 
                                        mtmt_authors['givenName'].lower() in given_name.lower()):
                                        return ('same_name_different_author', 
                                                f"{mtmt_authors['mtid']} {mtmt_authors['familyName']} {mtmt_authors['givenName']}")
                return 'different_author', None
            else:
                return 'no_paper_found', None
        else:
            print(f"⚠️ HTTP {response_.status_code} error when querying MTMT for title {title_orig}")
    except Exception as e:
        print(f"⚠️ Exception when querying MTMT: {e}")
    return 'no_response', None


def parse_last_modified(val):
    """Parse MTMT lastModified timestamp to datetime.
    
    Args:
        val: Timestamp value (int, float, or ISO string)
        
    Returns:
        datetime or None
    """
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
            ts = int(val)
            if ts > 1e12:  # milliseconds
                ts = ts / 1000
            return datetime.datetime.fromtimestamp(ts)
    except Exception:
        pass
    
    # ISO-like string
    if isinstance(val, str):
        s = val.strip()
        try:
            return datetime.datetime.fromisoformat(s)
        except Exception:
            # Try YYYY-MM-DD prefix
            try:
                return datetime.datetime.strptime(s[:10], "%Y-%m-%d")
            except Exception:
                return None
    return None


def is_active_in_mtmt(mtmt_record):
    """Check if MTMT author profile is active (modified within 3 years).
    
    Args:
        mtmt_record: MTMT author record dict
        
    Returns:
        str: 'inactive' if not modified in 3+ years, '' otherwise
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    dt = parse_last_modified(mtmt_record.get("lastModified"))
    if dt is None:
        return ""
    
    # Normalize dt to timezone-aware UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    
    age_years = (now - dt).total_seconds() / (365.25 * 24 * 3600)
    if age_years >= 3:
        return "inactive"
    return ""


def categorize_topic(val):
    """Categorize research topic as 'theory', 'applied', or ''.
    
    Args:
        val: Topic string (e.g., from MTMT auxName)
        
    Returns:
        str: 'theory', 'applied', or ''
    """
    theory_kw = [
        "matematik", "elmélet", "gráf", "logika", "kombinatórik", "kombinatorik",
        "tudomány", "algoritmus", "operációkutatás", "geometria", "algebra",
        "theory", "matematika", "formális", "statisztika"
    ]
    practical_kw = [
        "info", "hálózat", "távközl", "szoftver", "gép", "tanulás", "vision",
        "képfeld", "intelligencia", "technológia", "technika", "mérnök", "robot",
        "fizika", "protokol", "adat", "internet", "network", "routing", "szintézis",
        "blockchain", "rendszer", "engineering", "fuzz", "idősor", "fonetika",
        "nyelv", "műszaki", "modellezés"
    ]
    s = val.lower()
    if any(k in s for k in theory_kw):
        return "theory"
    if any(k in s for k in practical_kw):
        return "applied"
    return ""

def get_metrics(mtmt_record:     dict, mtmt_pub: list) -> dict:
    """Extract basic metrics from MTMT author record."""
    metrics = {
        "journal_publications": 0,
        "conference_publications": 0,
        "total_citations": 0,
        "rank": {}
    }
    if "citationCount" in mtmt_record:
        metrics["total_citations"] = mtmt_record["citationCount"]
    for paper in mtmt_pub:
        if paper["otype"] == "JournalArticle":
            metrics["journal_publications"] += 1
        if "conference" in paper:
            metrics["conference_publications"] += 1
        if "ratingsForSort" in paper:
            rank= paper["ratingsForSort"]
            if rank in metrics["rank"]:
                metrics["rank"][rank] += 1
            else:
                metrics["rank"][rank] = 1
    metrics['journal D1 eqvivalents'] = 0
    for rank in metrics["rank"]:
        if rank=='D1':
            metrics['journal D1 eqvivalents']+=metrics["rank"][rank]
        elif rank=='Q1':
            metrics['journal D1 eqvivalents']+=metrics["rank"][rank]/3
        elif rank=='Q2':
            metrics['journal D1 eqvivalents']+=metrics["rank"][rank]/6
        elif rank=='Q3':
            metrics['journal D1 eqvivalents']+=metrics["rank"][rank]/12
        elif rank=='Q4':
            metrics['journal D1 eqvivalents']+=metrics["rank"][rank]/16
        else:
            print(f"Unknown rank {rank} in MTMT record")
    if "affiliations" in mtmt_record:
        metrics["affiliations"] = []
        for affil in mtmt_record["affiliations"]:
            if "worksFor" in affil:
                metrics["affiliations"].append(affil["worksFor"].get("label","")) 
    return metrics

if __name__ == "__main__":
    # Simple test
    test_id = "10028156"
    author_rec, pub_rec = get_mtmt_record(test_id)
    metrics = get_metrics(author_rec, pub_rec)
    for key, value in metrics.items():
        if isinstance(value, dict):
            for rank, count in value.items():
                print(f"{key} {rank}: {count}")
        elif isinstance(value, list):
            for count in value:
                print(f"{key}: {count}")
        else:
            print(f"{key}: {value}")

    #print(f"Author record for MTMT ID {test_id}: {author_rec}")
    #print(f"Publications record for MTMT ID {test_id}: {pub_rec}

def cache_mtmt_query(authors_data, force=False):
    """Cache MTMT records for all authors with MTMT IDs.
    
    Args:
        authors_data: Dictionary of author names to their data
        force: If True, re-fetch even if cached
        
    Returns:
        None (updates cache files)
    """
    import dblp_utils
    
    counter = 0
    total = len(authors_data)
    
    for name, data in authors_data.items():
        counter += 1
        
        if 'mtmt_id' not in data or not data['mtmt_id']:
            continue
            
        mtmt_id = str(data['mtmt_id']).strip()
        if not mtmt_id:
            continue
            
        print(f"[{counter}/{total}] Caching MTMT for {name} (ID: {mtmt_id})")
        
        try:
            # Fetch MTMT record (will use/update cache)
            data_mtmt, data_pub = get_mtmt_record(mtmt_id, force=force, author_name=name)
            
            # Optional: verify against DBLP if available
            if 'dblp_url' in data and data['dblp_url']:
                try:
                    dblp_record = dblp_utils.get_DBLP_record(data['dblp_url'], name, force=force)
                    if dblp_record and data_pub:
                        if not dblp_utils.is_same_dblp_and_mtmt_records(dblp_record, data_mtmt, data_pub):
                            print(f"  ❌ DBLP and MTMT records do NOT match for {name}")
                        # else:
                        #     print(f"  ✅ DBLP and MTMT records match for {name}")
                except Exception as e:
                    print(f"  ⚠️ Error checking DBLP match for {name}: {e}")
                    
            # Rate limiting
            if counter % 50 == 0:
                print("  ⏸️  Pausing 5 seconds after 50 queries...")
                time.sleep(5)
                
        except Exception as e:
            print(f"  ⚠️ Error fetching MTMT for {name}: {e}")
            
    print(f"\n✅ Cached MTMT records for {counter} authors.")