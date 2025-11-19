#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test script for first paper year extraction"""

import json
from create_author_order import find_first_paper_year, add_first_paper_year

# Load author data
with open('results/full_authors_data.json', 'r', encoding='utf-8') as f:
    author_data = json.load(f)

# Test with first few authors
print("Testing first paper year extraction:\n")
count = 0
for author_name, data in author_data.items():
    if count >= 10:  # Test first 10 authors
        break
    
    first_year = find_first_paper_year(data)
    if first_year:
        print(f"{author_name}: {first_year}")
        count += 1

# Test with add_first_paper_year function
print("\n\nTesting add_first_paper_year function:")
test_rows = [
    {'Név': author_name}
    for author_name in list(author_data.keys())[:5]
]

add_first_paper_year(test_rows, author_data_dict=author_data)

for row in test_rows:
    print(f"{row['Név']}: {row.get('First Paper Year', 'N/A')}")

print("\n✓ Test completed")
