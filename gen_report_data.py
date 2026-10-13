#!/usr/bin/env python3
"""
Regenerate figure CSV files used by the LaTeX academic report.
Reads corePaperList-git/results/ JSONs, writes to figures/.
"""
import json
import os
from collections import defaultdict

RESULTS_DIR = "results"
FIGURES_DIR = "figures"

os.makedirs(FIGURES_DIR, exist_ok=True)

TIER_SOURCES = {
    "astar_hungarian": "hungarian_papers_coreAstar.json",
    "astar_abroad": "already_abroad_papers_coreAstar.json",
    "a_hungarian": "hungarian_papers_coreA.json",
    "a_abroad": "already_abroad_papers_coreA.json",
    "b_hungarian": "hungarian_papers_coreB.json",
    "b_abroad": "already_abroad_papers_coreB.json",
}


def classify_category(classified):
    if "theory" in classified:
        return 3
    if "applied" in classified:
        return 6
    return "Unknown"


def load_papers(filename):
    path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(path):
        print(f"  Warning: {path} not found, skipping")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def papers_by_year(filename):
    """Returns {year: {3: count, 6: count, 'Unknown': count}}"""
    papers = load_papers(filename)
    counts = defaultdict(lambda: defaultdict(int))
    for paper in papers.values():
        year = paper.get("year", "Unknown")
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = "Unknown"
        cat = classify_category(paper.get("classfiied", []))
        counts[year][cat] += 1
    return counts


def write_by_year_csv(counts, out_path):
    years = sorted(y for y in counts if isinstance(y, int))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("Year,3,6,Unknown\n")
        for year in years:
            row = counts[year]
            f.write(f"{year},{float(row.get(3,0))},{float(row.get(6,0))},{float(row.get('Unknown',0))}\n")
    print(f"  Written: {out_path} ({len(years)} years)")


CSV_OUTPUTS = [
    ("hungarian_papers_coreAstar.json", "hungarian_coreAstar_by_year.csv"),
    ("already_abroad_papers_coreAstar.json", "already_abroad_coreAstar_by_year.csv"),
    ("hungarian_papers_coreA.json", "hungarian_coreA_by_year.csv"),
    ("already_abroad_papers_coreA.json", "already_abroad_coreA_by_year.csv"),
]

for src, dst in CSV_OUTPUTS:
    print(f"Processing {src} …")
    counts = papers_by_year(src)
    write_by_year_csv(counts, os.path.join(FIGURES_DIR, dst))

print("Done.")
