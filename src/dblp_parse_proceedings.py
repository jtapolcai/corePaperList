import gzip
import json
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import XMLParser
from html.entities import name2codepoint
    
DBLP_FILE = "../corePaperList/inputs/dblp.xml.gz"

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
            if tag == "proceedings":
                # Példa: kinyerünk néhány mezőt
                pub = {
                    "type": tag,
                    "key": elem.get("key"),
                    "editor": [],
                    "year": None,
                    "url": None,
                    "venue": None,
                    "series": None
                }

                for child in elem:
                    ctag = child.tag
                    text = (child.text or "").strip()

                    if ctag == "editor":
                        pub["editor"].append(text)
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
                    elif ctag == "series":
                        pub["series"] = text

                # Itt adjuk vissza a rekordot
                if pub['year'] is not None:
                    yield pub

                # Nagyon fontos: memória felszabadítása
                elem.clear()


if __name__ == "__main__":
    count = 0
    proceedings = {}
    for pub in iter_dblp_publications(DBLP_FILE):
        # Itt azt csinálsz a rekorddal, amit akarsz:
        # pl. szűrés, kiírás, adatbázisba rakás stb.
        #short_paper = False
        year=int(pub.get("year", 0))
        venue_crossref=pub.get("url", "")
        venue_name=pub.get("venue", "")
        key = pub.get("key", "")
        keys = key.split('/')
        if len(keys)>=2:
            venue_from_key='/'.join(keys[:2])
            rest_of_key='/'.join(keys[2:])
        else:
            print(f"Figyelem: nem várt key formátum: {key}")
        if venue_from_key not in proceedings:
            proceedings[venue_from_key]={}
        if rest_of_key not in proceedings[venue_from_key]:
            proceedings[venue_from_key][rest_of_key] = pub
        else:
            print(f"Duplikált kulcs találat: {key}")
            print(f"Rekord: {pub}")
            print(f"Korábbi rekord: {proceedings[key]}")
        count += 1
        if count % 1000 == 0: # 12093075 
            print(f"{count} rekord feldolgozva...")
            with open('proceedings.json', 'w', encoding='utf-8') as f:
                json.dump(proceedings, f, ensure_ascii=False, indent=2)
    print(f"Összesen {count} publikációt dolgoztam fel.")
    

    
    # Venue statistics
    with open('proceedings.json', 'w', encoding='utf-8') as f:
        json.dump(proceedings, f, ensure_ascii=False, indent=2)
    print(f"✓ Venue statisztikák mentve: proceedings.json")
    


             