#!/usr/bin/env python3
"""Batch LLM verification of classified Hungarian papers.

Checks whether papers in hungarian_papers_core*.json were correctly
identified as full papers (not short/poster/demo/workshop papers).

Usage:
  python3 verify_papers.py                    # all ranks, use cache
  python3 verify_papers.py --ranks A* A       # only A* and A
  python3 verify_papers.py --force            # ignore cache, re-verify all
  python3 verify_papers.py --output flagged   # also save flagged.json

Requires:  pip install anthropic
           ANTHROPIC_API_KEY environment variable
"""
import argparse
import json
import sys
import time
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent / "src"))
from llm_verify import (
    load_cache,
    save_cache,
    verify_paper,
    CACHE_PATH,
)

RESULTS_DIR = Path("results")
RANKS = ["A*", "A", "B", "C", "no_rank"]


def rank_filename(rank: str) -> str:
    return rank.replace("*", "star")


def main():
    parser = argparse.ArgumentParser(description="LLM-verify paper classifications")
    parser.add_argument("--ranks", nargs="+", default=RANKS, metavar="RANK")
    parser.add_argument("--force", action="store_true", help="Ignore cache")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Save flagged papers to FILE.json")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    cache = {} if args.force else load_cache()
    all_flagged = []
    grand_total = grand_checked = 0

    for rank in args.ranks:
        path = RESULTS_DIR / f"hungarian_papers_core{rank_filename(rank)}.json"
        if not path.exists():
            print(f"[skip] {path.name} not found")
            continue

        papers = json.loads(path.read_text(encoding="utf-8"))
        rank_flagged = []
        rank_checked = 0
        print(f"\n{'='*60}")
        print(f"  {rank}  ({len(papers)} papers)")
        print(f"{'='*60}")

        for key, paper in papers.items():
            grand_total += 1
            title = paper.get("title", "?")[:70]

            if key in cache and not args.force:
                result = cache[key]
            else:
                result = verify_paper(paper, rank, client)
                result["rank"] = rank
                cache[key] = result
                save_cache(cache)
                grand_checked += 1
                rank_checked += 1
                time.sleep(0.12)

            if result.get("flagged"):
                icon = "⚠️ "
                conf = result.get("confidence", "?")[0].upper()
                reason = result.get("reason", "")[:80]
                print(f"  {icon}[{conf}] {title}")
                print(f"       {reason}")
                rank_flagged.append({"key": key, "rank": rank, "paper": paper, **result})

        if not rank_flagged:
            print("  ✓ No issues found")
        all_flagged.extend(rank_flagged)
        print(f"  Flagged: {len(rank_flagged)}  (newly checked: {rank_checked})")

    print(f"\n{'='*60}")
    print(f"Total: {grand_total} papers, {grand_checked} newly verified via LLM")
    print(f"Flagged: {len(all_flagged)} papers")

    if args.output:
        out = Path(args.output).with_suffix(".json")
        out.write_text(json.dumps(all_flagged, indent=2, ensure_ascii=False))
        print(f"Saved flagged list → {out}")
    else:
        if all_flagged:
            print("\n=== SUMMARY OF FLAGGED PAPERS ===")
            for f in all_flagged:
                print(f"  [{f['rank']}] {f['paper'].get('title','?')}")
                print(f"    → {f.get('reason','')}")


if __name__ == "__main__":
    main()
