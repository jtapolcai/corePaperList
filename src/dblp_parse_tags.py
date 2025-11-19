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
            if len(elem):
                yield tag
                # Nagyon fontos: memória felszabadítása
                elem.clear()


if __name__ == "__main__":
    count = 0
    statistics = {}
    tag_counts = {} 
    for pub in iter_dblp_publications(DBLP_FILE):
        if pub not in tag_counts:
            tag_counts[pub] = 0
        tag_counts[pub] += 1
        count += 1
        if count % 100000 == 0: # 12093075 
            print(f"{count} rekord feldolgozva...")
            with open('dblp_tag_statistics.json', 'w', encoding='utf-8') as f:
                json.dump(tag_counts, f, ensure_ascii=False, indent=2)
    print(f"Összesen {count} publikációt dolgoztam fel.")
    
    # JSON fájlba írás
    with open('dblp_tag_statistics.json', 'w', encoding='utf-8') as f:
        json.dump(tag_counts, f, ensure_ascii=False, indent=2)
    print(f"✓ Statisztikák mentve: dblp_tag_statistics.json")
    


