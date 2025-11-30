import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import classify_paper
import json
import copy

if __name__ == "__main__":


    with open('test/test_papers.json', 'r', encoding='utf-8') as f:
        papers = json.load(f)

    results = []
    for rec_ in papers:
        if 'inproceedings' not in rec_:
            continue
        rec=rec_['inproceedings']
        rec_orig = copy.deepcopy(rec)
        key, record, rank, foreign_paper, short_paper, search_log, original_rank = classify_paper.classify_paper(rec_)
        rec['rank'] = rank
        rec['original_rank'] = original_rank
        rec['foreign_paper'] = foreign_paper
        rec['short_paper'] = short_paper
        rec['search_log'] = search_log
        print(f"Key: {key}")
        print(f"Record: {record}")
        print(f"Rank: {rank}")
        print(f"Original rank: {original_rank}")
        print(f"Foreign paper: {foreign_paper}")
        print(f"Short paper: {short_paper}")
        print(f"Search log: {search_log}")
        results.append(rec)
        # Ellenőrzés: mezőnként kiírjuk, mi változott
        if rec_orig != rec:
            print("Eltérés az eredeti és a módosított rekord között:")
            for k in rec_orig.keys():
                if rec_orig[k] != rec[k]:
                    print(f"  Mező: {k} eredeti: {rec_orig[k]} módosított: {rec[k]}")
                    #assert False, "Input record was modified!"

    with open('test/test_paper_.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("✓ Test finished: All records processed.")