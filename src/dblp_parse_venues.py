import gzip
import json
import os
import time

import xml.etree.ElementTree as ET
from xml.etree.ElementTree import XMLParser
from html.entities import name2codepoint
import classify_paper
    
DBLP_FILE = "inputs/dblp.xml.gz"

# Generate complete HTML entity mapping from Python's html.entities module
# This includes all 252 standard HTML entities (euml, ocirc, etc.)
HTML_ENTITIES = {}
for name, codepoint in name2codepoint.items():
    HTML_ENTITIES[name] = chr(codepoint)


def iter_dblp_publications(filename: str):
    """
    Generátor, ami végigiterál a teljes dblp.xml.gz dump összes releváns
    publikációs rekordján. Minden rekordot egy dict-ként ad vissza.
    """
    # Create custom parser that handles HTML entities
    parser = XMLParser()
    # Register HTML entities
    for entity, char in HTML_ENTITIES.items():
        parser.entity[entity] = char
    
    with gzip.open(filename, "rb") as f:
        # csak 'end' esemény kell, hogy akkor dolgozzuk fel, amikor egy elem lezárult
        context = ET.iterparse(f, events=("end",), parser=parser)
        for event, elem in context:
            tag = elem.tag
            # A root elem (dblp) neve általában 'dblp', azt kihagyjuk
            if tag == "inproceedings":
                # Példa: kinyerünk néhány mezőt
                pub = {
                    "type": tag,
                    "key": elem.get("key"),
                    "authors": [],
                    "title": elem.get("title", ""),
                    "year": None,
                    "url": None,
                    "venue": None,
                    "pages": None,
                    "crossref": None
                }

                for child in elem:
                    ctag = child.tag
                    text = (child.text or "").strip()

                    if ctag == "author":
                        pub["authors"].append(text)
                    elif ctag == "title":
                        pub["title"] = text
                    elif ctag == "year":
                        pub["year"] = text
                    elif ctag == "url":
                        venue=text.replace("db/", "").split("/")
                        venue_str='/'.join(venue[:-1])
                        pub["url"] = venue_str
                    elif ctag == "crossref":
                        pub["crossref"] = text
                    elif ctag == "booktitle":
                        pub["venue"] = text
                    elif ctag == "pages":
                        pub["pages"] = text

                # Itt adjuk vissza a rekordot
                if pub['year'] is not None:
                    yield pub

                # Nagyon fontos: memória felszabadítása
                elem.clear()


if __name__ == "__main__":
    count = 0
    statistics = {}
    statistics["no_rank"] = {}
    statistics["no_rank"]["all"] = {}
    venue_counts = {} 
    venue_names = {}
    # Cache for core_rank lookups to avoid repeated pandas queries
    rank_cache = {}
    # Time-based progress logging (every ~10s)
    last_log_time = time.time()
    last_log_count = 0
    for pub in iter_dblp_publications(DBLP_FILE):
        # Itt azt csinálsz a rekorddal, amit akarsz:
        # pl. szűrés, kiírás, adatbázisba rakás stb.
        #short_paper = False
        year=int(pub.get("year", 0))
        venue_dblp=pub.get("url", "")
        venue_crossref=pub.get("crossref", "")
        if venue_crossref:
            venue_crossref_short='/'.join(venue_crossref.split('/')[:2]) 
            if venue_dblp != venue_crossref_short:
                #print(f"Figyelem: eltérés a URL és crossref között: {venue_dblp} vs {venue_crossref_short}")
                venue_dblp=venue_crossref_short
        venue_name=pub.get("venue", "")
        #print(venue_dblp,pub.get("crossref", ""))
        if venue_dblp not in venue_counts:
            venue_counts[venue_dblp] = 0
        venue_counts[venue_dblp] += 1
        
        # Use cache for rank lookup
        cache_key = (venue_name, venue_crossref, venue_dblp, year)
        if cache_key in rank_cache:
            rank, short_paper = rank_cache[cache_key]
        else:
            rank, short_paper = classify_paper.core_rank(venue_name, venue_crossref, venue_dblp, year)
            rank_cache[cache_key] = (rank, short_paper)
        short_paper_str="short" if short_paper else "full"
        if rank == "no_rank":
            # Correctly accumulate no_rank counts under the 'all' bucket per year
            if year not in statistics["no_rank"]["all"]:
                statistics["no_rank"]["all"][year] = 0
            statistics["no_rank"]["all"][year] += 1
            continue
        venue_=classify_paper.remove_numbers_and_parentheses(venue_name)
        # if classify_paper.is_short_paper(pub, venue_name, rank):
        #     venue_=venue_+'_short'
        #     if venue:
        #         venue=venue+'_short'
        #     else:
        #         venue=venue_
        pages_str = pub.get("pages", "")
        pagenum = classify_paper.get_paper_length(pages_str)
        # Use nested dict instead of list for O(1) lookup
        if venue_dblp not in venue_names:
            venue_names[venue_dblp] = {}
        if venue_ not in venue_names[venue_dblp]:
            venue_names[venue_dblp][venue_] = {}
        if pagenum not in venue_names[venue_dblp][venue_]:
            venue_names[venue_dblp][venue_][pagenum] = 0
        venue_names[venue_dblp][venue_][pagenum] += 1

        if rank not in statistics:
            statistics[rank] = {'full': {}, 'short': {}}
        if venue_dblp not in statistics[rank][short_paper_str]:
            statistics[rank][short_paper_str][venue_dblp] = {}
        if year not in statistics[rank][short_paper_str][venue_dblp]:
            statistics[rank][short_paper_str][venue_dblp][year] = 0
        statistics[rank][short_paper_str][venue_dblp][year] += 1
        count += 1
        # Print progress every ~10 seconds with processing rate
        now = time.time()
        if now - last_log_time >= 10:
            delta = count - last_log_count
            elapsed = now - last_log_time if now - last_log_time > 0 else 1.0
            rate = delta / elapsed
            print(f"{count} rekord feldolgozva... ~{rate:.0f} rec/s", flush=True)
            last_log_time = now
            last_log_count = count

    print(f"Összesen {count} publikációt dolgoztam fel.")
    
    if not os.path.exists('conference_stats'):
        os.makedirs('conference_stats')
    # JSON fájlba írás
    # Rendezett kiíráshoz először rekurzívan sorbarendezzük a numerikus év-kulcsokat
    def _sort_keys_rec(obj):
        if isinstance(obj, dict):
            # Rekurzívan dolgozzuk fel a gyerekeket
            new_children = {k: _sort_keys_rec(v) for k, v in obj.items()}
            # Rendezési kulcs: numerikus kulcsok elsőként (egész szám szerint), aztán a többi lexikografikusan
            def _sort_key(k):
                if isinstance(k, str) and k.isdigit():
                    return (0, int(k))
                return (1, k)
            ordered = {}
            for k in sorted(new_children.keys(), key=_sort_key):
                ordered[k] = new_children[k]
            return ordered
        elif isinstance(obj, list):
            return [_sort_keys_rec(v) for v in obj]
        else:
            return obj

    sorted_statistics = _sort_keys_rec(statistics)
    with open('conference_stats/dblp_statistics.json', 'w', encoding='utf-8') as f:
        json.dump(sorted_statistics, f, ensure_ascii=False, indent=2)
    print(f"✓ Statisztikák mentve: conference_stats/dblp_statistics.json (évszámok rendezve)")
    
    # Venue statistics
    with open('conference_stats/dblp_venue_counts.json', 'w', encoding='utf-8') as f:
        json.dump(venue_counts, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: conference_stats/dblp_venue_counts.json")
    
    with open('conference_stats/dblp_venue_names.json', 'w', encoding='utf-8') as f:
        json.dump(venue_names, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: conference_stats/dblp_venue_names.json")

    with open('conference_stats/dblp_acronym_to_crossref.json', 'w', encoding='utf-8') as f:
        json.dump(classify_paper.acronym_to_crossref, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: conference_stats/dblp_acronym_to_crossref.json")


    # Print top venues
    print(f"\nÖsszes venue: {len(venue_counts)}")


