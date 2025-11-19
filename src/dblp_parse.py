import gzip
import json
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


if __name__ == "__main__":
    count = 0
    statistics = {}
    venue_counts = {} 
    venue_names = {} 
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
        rank = classify_paper.get_core_rank(pub)
        if rank == "no_rank":
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
            statistics[rank] = {}
        if venue_dblp not in statistics[rank]:
            statistics[rank][venue_dblp] = {}
        if year not in statistics[rank][venue_dblp]:
            statistics[rank][venue_dblp][year] = 0
        statistics[rank][venue_dblp][year] += 1
        count += 1
        if count % 10000 == 0: # 12093075 
            print(f"{count} rekord feldolgozva...")

    print(f"Összesen {count} publikációt dolgoztam fel.")
    
    # JSON fájlba írás
    with open('dblp_statistics.json', 'w', encoding='utf-8') as f:
        json.dump(statistics, f, ensure_ascii=False, indent=2)
    print(f"✓ Statisztikák mentve: dblp_statistics.json")
    
    # Venue statistics
    with open('dblp_venue_counts.json', 'w', encoding='utf-8') as f:
        json.dump(venue_counts, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: dblp_venue_counts.json")
    
    with open('dblp_venue_names.json', 'w', encoding='utf-8') as f:
        json.dump(venue_names, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: dblp_venue_names.json")

    # Print top venues
    print(f"\nÖsszes venue: {len(venue_counts)}")


