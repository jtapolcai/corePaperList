import gzip
import json
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import XMLParser
from html.entities import name2codepoint

DBLP_FILE = "inputs/dblp.xml.gz"

# Generate complete HTML entity mapping from Python's html.entities module
HTML_ENTITIES = {}
for name, codepoint in name2codepoint.items():
    HTML_ENTITIES[name] = chr(codepoint)

def iter_dblp_tags(filename: str):
    """
    Generator to iterate over all tags in the DBLP XML dump.
    Builds a hierarchical tree of tags and counts their occurrences.
    """
    # Create custom parser that handles HTML entities
    parser = XMLParser()
    for entity, char in HTML_ENTITIES.items():
        parser.entity[entity] = char

    with gzip.open(filename, "rb") as f:
        context = ET.iterparse(f, events=("start", "end"), parser=parser)
        tag_stack = []
        for event, elem in context:
            if event == "start":
                tag_stack.append(elem.tag)
                yield tag_stack.copy()
            elif event == "end":
                tag_stack.pop()
                elem.clear()  # Free memory

def build_tag_tree_and_counts(filename):
    """
    Build a hierarchical tree of tags and count their occurrences.

    Args:
        filename (str): Path to the DBLP XML file.

    Returns:
        dict: A nested dictionary representing the tag hierarchy and counts.
    """
    tag_tree = {}

    def add_to_tree(tree, path):
        current = tree
        for tag in path:
            if tag not in current:
                current[tag] = {"_count": 0, "_children": {}}
            current[tag]["_count"] += 1
            current = current[tag]["_children"]

    for tag_path in iter_dblp_tags(filename):
        add_to_tree(tag_tree, tag_path)

    return tag_tree

if __name__ == "__main__":
    print("Building tag tree and counting occurrences...")
    tag_tree = build_tag_tree_and_counts(DBLP_FILE)

    # Save the tag tree to a JSON file
    with open('results/dblp_tag_tree.json', 'w', encoding='utf-8') as f:
        json.dump(tag_tree, f, ensure_ascii=False, indent=2)

    print("✓ Tag tree and counts saved to results/dblp_tag_tree.json")


