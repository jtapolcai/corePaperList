import gzip
import json
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import XMLParser
from html.entities import name2codepoint
import classify_paper
import argparse
import sys
import os
import re
    
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
                    "pages": None
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
                    elif ctag == "booktitle":
                        pub["venue"] = text
                    elif ctag == "pages":
                        pub["pages"] = text

                # Itt adjuk vissza a rekordot
                if pub['year'] is not None:
                    yield pub

                # Nagyon fontos: memória felszabadítása
                elem.clear()


def find_records(filename: str, query: str = None, max_results: int = 10, stream: bool = False, out_file: str = "results/matched_records.xml", match_mode: str = "exact", field: str = None, value: str = None, case_insensitive: bool = False):
    """
    Find records in the gzipped DBLP dump according to match_mode and write or print them.
    """
    parser = XMLParser()
    for entity, char in HTML_ENTITIES.items():
        parser.entity[entity] = char

    found = 0
    field_present_but_no_match = 0
    # If streaming to file, ensure output directory exists
    if stream:
        out_dir = os.path.dirname(out_file) or "."
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        out_f = open(out_file, "w", encoding="utf-8")
        out_f.write('<?xml version="1.0" encoding="UTF-8"?>\n<dblp>\n')
    else:
        out_f = None

    try:
        with gzip.open(filename, "rb") as f:
            context = ET.iterparse(f, events=("end",), parser=parser)
            for event, elem in context:
                # csak rekord típusok érdekelnek (más típusok is lehetnek a fájlban)
                if elem.tag in ("article", "inproceedings", "proceedings", "book", "incollection", "phdthesis", "mastersthesis", "data", "www"):
                    # Normalize target field (default to title)
                    target_field = field or "title"
                    matched = False
                    field_found = False
                    # Search the target field in the element's children; consider match if any child matches
                    for child in elem:
                        if child.tag == target_field:
                            field_found = True
                            child_text = (child.text or "")
                            if case_insensitive:
                                hay = child_text.lower()
                                needle = (value or "").lower()
                            else:
                                hay = child_text
                                needle = value or ""

                            if match_mode == "exact":
                                if hay.strip() == needle.strip():
                                    matched = True
                                    break
                            elif match_mode == "contains":
                                if needle in hay:
                                    matched = True
                                    break
                            elif match_mode == "regex":
                                try:
                                    flags = re.IGNORECASE if case_insensitive else 0
                                    if re.search(needle, child_text, flags=flags):
                                        matched = True
                                        break
                                except re.error:
                                    pass

                    if matched:
                        xml_str = ET.tostring(elem, encoding="unicode")
                        
                        if stream:
                            out_f.write(xml_str + "\n")
                        else:
                            print(xml_str)
                            print("\n---\n")
                        found += 1
                    else:
                        if field_found:
                            field_present_but_no_match += 1

                    elem.clear()
                    if found >= max_results and not stream:
                        break

        if found == 0:
            print(f"No matches for value: '{value}' in field: '{field or 'title'}'")
        else:
            if stream:
                print(f"{found} matches saved to: {out_file}")
            else:
                print(f"{found} matches found")

        if field_present_but_no_match:
            print(f"{field_present_but_no_match} records had field '{field or 'title'}' but did not match the value '{value}'")
    finally:
        if out_f:
            out_f.write("</dblp>\n")
            out_f.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DBLP parse helpers")
    parser.add_argument("--file", "-f", default=DBLP_FILE, help="A dblp.xml.gz fájl elérési útja")
    parser.add_argument("--max", "-m", type=int, default=10, help="Max találatok száma a címkeresésnél")
    parser.add_argument("--stream", action="store_true", help="Ha megadod, a találatokat egy XML fájlba írja")
    parser.add_argument("--out", "-o", default="results/matched_records.xml", help="Kimeneti fájl stream módban")
    parser.add_argument("--mode", choices=["exact","contains","regex"], default="exact", help="Keresési mód: exact (alap), contains, regex")
    parser.add_argument("--field", help="Mező neve, amin keresünk (pl. title, author, year, url). Alapértelmezett: title", default="title")
    parser.add_argument("--value", help="Keresendő szöveg a megadott mezőben")
    parser.add_argument("--insensitive", action="store_true", help="Case-insensitive keresés (contains/field/exact)")
    args = parser.parse_args()

    if args.value:
        find_records(args.file, query=args.value, max_results=args.max, stream=args.stream, out_file=args.out, match_mode=args.mode, field=args.field, value=args.value, case_insensitive=args.insensitive)
        sys.exit(0)
    else:
        parser.error("Please provide --value to search for (use --field to choose XML field, default is title).")

    count = 0
    statistics = {}
    venue_counts = {} 
    venue_names = {} 
    selected = []
    for pub in iter_dblp_publications(DBLP_FILE):
        # Itt azt csinálsz a rekorddal, amit akarsz:
        # pl. szűrés, kiírás, adatbázisba rakás stb.
        #short_paper = False
        venue_dblp=pub.get("url", "")
        year=int(pub.get("year", 0))
        venue_name=pub.get("venue", "")
        if venue_dblp not in venue_counts:
            venue_counts[venue_dblp] = 0
        venue_counts[venue_dblp] += 1
        rank, short_paper, row = classify_paper.get_core_rank(pub)
        short_paper_str = "short" if short_paper else "full"
        if rank == "no_rank":
            continue
        venue_=classify_paper.remove_numbers_and_parentheses(venue_name)
        if venue_dblp == "conf/siggraph" and year ==2018:
            selected.append(pub)
        # if classify_paper.is_short_paper(pub, venue_name, rank):
        #     venue_=venue_+'_short'
        #     if venue:
        #         venue=venue+'_short'
        #     else:
        #         venue=venue_
        pages_str = pub.get("pages", "")
        pagenum = classify_paper.get_paper_length(pages_str)
        if venue_dblp not in venue_names:
            venue_names[venue_dblp] = [(venue_, {pagenum:1})]    
        else:
            # Check if venue_name already exists
            found = False
            for i, (v_name, page_dict) in enumerate(venue_names[venue_dblp]):
                if v_name == venue_:
                    # Update page number count
                    if pagenum in page_dict:
                        page_dict[pagenum] += 1
                    else:
                        page_dict[pagenum] = 1
                    venue_names[venue_dblp][i] = (v_name, page_dict)
                    found = True
                    break
            
            if not found:
                # New venue_name for this venue_
                venue_names[venue_dblp].append((venue_, {pagenum:1}))

        if rank not in statistics:
            statistics[rank] = {'full': {}, 'short': {}}
        if venue_dblp not in statistics[rank][short_paper_str]:
            statistics[rank][short_paper_str][venue_dblp] = {}
        if year not in statistics[rank][short_paper_str][venue_dblp]:
            statistics[rank][short_paper_str][venue_dblp][year] = 0
        statistics[rank][short_paper_str][venue_dblp][year] += 1
        count += 1
        if count % 10000 == 0: # 12093075 
            print(f"{count} rekord feldolgozva...")

    print(f"Összesen {count} publikációt dolgoztam fel.")
    
    # JSON fájlba írás
    with open('results/dblp_statistics.json', 'w', encoding='utf-8') as f:
        json.dump(statistics, f, ensure_ascii=False, indent=2)
    print(f"✓ Statisztikák mentve: dblp_statistics.json")
    
    with open('results/selected.json', 'w', encoding='utf-8') as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)
    print(f"✓ Statisztikák mentve: results/selected.json")

    # Venue statistics
    with open('results/dblp_venue_counts.json', 'w', encoding='utf-8') as f:
        json.dump(venue_counts, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: results/dblp_venue_counts.json")
    
    with open('results/dblp_venue_names.json', 'w', encoding='utf-8') as f:
        json.dump(venue_names, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: results/dblp_venue_names.json")
    # Print top venues
    print(f"\nÖsszes venue: {len(venue_counts)}")


