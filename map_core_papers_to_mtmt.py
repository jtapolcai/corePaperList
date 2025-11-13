# cikkek megkeresése MTMT-ben
import json
import csv
import unicodedata
import requests
import re
import json
from collections import Counter
import matplotlib.pyplot as plt
import numpy as np
import os,sys

show_plots = True
rank_names = ["Astar", "A"]
rank_names = ["Astar", "A","B","C"]

def fix_encoding(text):
    if isinstance(text, str):
        try:
            # szimulálja a hibás dekódolást -> majd újradekódolja jól
            return text.encode('latin1').decode('utf-8')
        except Exception:
            return text
    return text

def remove_accents(text):
    if not isinstance(text, str):
        print("not text")
        return text
    normalized = unicodedata.normalize('NFD', text)
    return ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')



def download_mtmt_papers(mtmt_results, base_path='hungarian_papers_',force_download=False):
    mtmt_author_data = {}
    missing_paper = []

    miss_spelled=[
        ("Turing Machines", "Turing-machines"),
        ("- parameterized", "-parameterized"),
        ("High-Level", "High Level"),
        ("\"", "'"),
        ("“", "'"),
        ("?", ""),
        ("Incresing","Increasing"),
        ("Two", "2"),
        ("Sources Asymptotics", "Sources Asymptotic"),
        ("Routing-Independent" ,"Routing Independent"),
        ("I/O-Efficient" ,"I/O Efficient"),
        ("α" , "alpha"),
        ("Pereeptron" ,"Perceptron"),
        ("proagation" ,"propagation"),
        ("Second-Order" ,"Second Order"),
        ("High-performance" ,"High performance")
    ]
    def remove_colon_after_lowercase(s: str) -> str:
        result = []
        for i, ch in enumerate(s):
            if ch == ":" and i > 0 and s[i-1].islower():
                continue    # kihagyjuk
            result.append(ch)
        return "".join(result)
    
    for rank_name in rank_names:
        filename=base_path+'core{}.json'.format(rank_name)
        if rank_name not in mtmt_results:
            mtmt_results[rank_name]={}
        with open(filename, "r", encoding="utf-8") as f:
            skipped=0
            papers = json.load(f)
            for key, paper in papers.items():
                if not force_download and key in mtmt_results[rank_name] and len(mtmt_results[rank_name][key])>0: 
                    #print(f"⏭️ Skipping already downloaded: {key}")
                    skipped+=1
                    continue
                if key in mtmt_results[rank_name] and not mtmt_results[rank_name][key]:
                    continue
                    print(f"Was missing try now")
                try:
                    authors = paper.get("authors", [])
                    acronym = paper.get("venue", "")
                    year = paper.get("year", "")
                    key = paper.get("key", "")
                    title_orig = paper.get("title", "")
                    if isinstance(title_orig, dict):
                        #print(f"⚠️ Unexpected title format for {key}: {title_orig}")
                        try:
                            title_orig = title_orig.get('#text', "")
                        except Exception as e:
                            print(f"❌ Error extracting title for {key}: {e}")
                            continue
                    # Törli minden (...) részt, zárójelet is:
                    title_orig = re.sub(r"\([^)]*\)", "", title_orig)
                    title = title_orig.strip(' .')
                    urls=[f"https://m2.mtmt.hu/api/publication?format=json&cond=title;eq;{title.replace(' ', '%20')}",
                                 f"https://m2.mtmt.hu/api/publication?format=json&cond=title;eq;{title.replace(' ', '%20')}."]
                    title_corrected=title 
                    for wrong, correct in miss_spelled:
                        title_corrected = title_corrected.replace(wrong, correct)
                    title_corrected=remove_colon_after_lowercase(title_corrected)
                    if title != title_corrected:
                        print(f"⚠️ Corrected typos in the title for retry: {title} -> {title_corrected}")
                        urls.append(f"https://m2.mtmt.hu/api/publication?format=json&cond=title;eq;{title_corrected.replace(' ', '%20')}")
                        urls.append(f"https://m2.mtmt.hu/api/publication?format=json&cond=title;eq;{title_corrected.replace(' ', '%20')}.")
                    print(f"🔍 Lekérdezés: {key})")
                    for url  in urls: 
#                        f"https://m2.mtmt.hu/api/publication?format=json&cond=labelOrMtid;eq;{title}"]: 
                        response_ = requests.get(url, timeout=10)
                        # we fix some typos in the title for the next try if this does not succeeds

                        if response_.status_code == 200:
                            response=response_.json()
                            if "content" in response:
                                papers=response["content"]
                                mtmt_results[rank_name][key] = papers
                                if len(papers) == 0:
                                    print(f"⚠️ Nincs találat az MTMT-ben: {key} {title.replace('%20',' ')} {url}")
                                for paper in papers:                                    
                                    if "authorships" in paper:
                                        for author in paper["authorships"]:
                                            if "author" in author:
                                                mtmt_authors=author["author"]
                                                if "label" in mtmt_authors:
                                                    if mtmt_authors["label"] not in mtmt_author_data:
                                                        mtmt_author_data[mtmt_authors["label"]]=mtmt_authors
                                                else:
                                                    if mtmt_authors["mtid"] not in mtmt_author_data:
                                                        mtmt_author_data[mtmt_authors["mtid"]]=mtmt_authors
                                if len(papers):
                                    break
                        else:
                            print(f"⚠️ no content in {response}")
                    else:
                        print(f"⚠️ HTTP {response_.status_code} hiba: {key} {title.replace('%20',' ')} {url}")
                        missing_paper.append(paper)
                    #break
                except Exception as e:
                    print(f"❌ Hiba: {key}: {e}")
                    missing_paper.append(paper)
                #break            
        # 💾 Eredmények mentése
        with open(f"papers_in_mtmt_{rank_name}.json", "w", encoding="utf-8") as f:
            json.dump(mtmt_results[rank_name], f, indent=2, ensure_ascii=False)

    with open("authors_in_mtmt.json", "w", encoding="utf-8") as f:
        json.dump(mtmt_author_data, f, indent=2, ensure_ascii=False)

    with open("failed_in_mtmt.json", "w", encoding="utf-8") as f:
        json.dump(missing_paper, f, indent=2, ensure_ascii=False)

    print(f"✅ Lekérések elmentve: papers_in_mtmt.json, missing_in_mtmt.json and authors_in_mtmt.json (skipped:{skipped})")

    return missing_paper



def plot_missing_papers_histogram(papers_mtmt):
    # Combine all papers from both dicts into a single list
    papers = []
    missing_paper_keys = []
    for rank_name in rank_names:
        for key, v in papers_mtmt[rank_name].items():
            if isinstance(v, list) and v:
                papers.extend(v)
            else:
                missing_paper_keys.append(key)
    print(f"Összesen {len(papers)} cikk találva MTMT-ben és {len(missing_paper_keys)} cikk hiányzik.")

    years = []
    missing_papers = []
    for rank_name in rank_names:
        filename='hungarian_papers_core{}.json'.format(rank_name)
        with open(filename, "r", encoding="utf-8") as f:
            papers = json.load(f)
            for key, paper in papers.items():
                if key in missing_paper_keys:
                    missing_papers.append(paper)
                    if "year" in paper:
                        y = paper["year"]
                        if isinstance(y, str) and y.isdigit():
                            years.append(int(y))
                        elif isinstance(y, int):
                            years.append(y)
                        print(f"Hiányzó cikk  {paper.get('title','N/A')} {paper.get('venue','')} {y} {paper.get('url','')}")
    
    with open("missing_in_mtmt.json", "w", encoding="utf-8") as f:
        json.dump(missing_papers, f, indent=2, ensure_ascii=False)

    if not years:
        print("Nincs évszám a rekordokban.")
        exit()

    # 2) Gyakoriságok
    year_counts = Counter(years)

    # 3) Hisztogram kirajzolása
    plt.figure(figsize=(8, 4))
    x_vals = sorted(year_counts.keys())
    y_vals = [year_counts[y] for y in x_vals]
    plt.bar(x_vals, y_vals, color='skyblue')
    plt.xlabel('Év')
    plt.ylabel('Darabszám')
    plt.title('Rekordok év szerinti hisztogramja')
    plt.xticks(x_vals, rotation=45)
    plt.tight_layout()
    if show_plots:
        plt.show()
    else:
        outpath='missing_papers_histogram.png'
        plt.savefig(outpath, dpi=150)
        print(f'✅ Saved figure to {outpath}')


def plot_journal_versions(papers_mtmt):
    # Store ratings for all ranks dynamically
    ratings_by_rank = {rank: Counter() for rank in rank_names}
    rank_map={'D1':1,'Q1':2,'Q2':3,'Q3':4,'Q4':5,'nincs rank':6, 'nincs folyóirat változat':7,'nincs az MTMT-ben':8,'no_conference_version':9}

    mtmt_to_core = {}

    for rank_name in rank_names:
        papers=papers_mtmt[rank_name]
        
        filename='hungarian_papers_core{}.json'.format(rank_name)
        with open(filename, "r", encoding="utf-8") as f:
            mtmt_results = {}
            paper_dblp = json.load(f)

        otypes = []
        subtypes = []
        ratings = []

        def process_paper(key, papers_list, paper_dblp):
            # compute the best (smallest) rank for the given paper list
            if key not in paper_dblp:
                print(f'⚠️ Key {key} not found in local DBLP data, skipping (could be outdated chache)')
                return
            best_rank = len(rank_map) 
            if len(papers_list)==0:
                #print(f'⚠️ No papers found for {key} - {paper_dblp[key]} skipping')
                ratings.append(8)
                return
            found_the_conference_version = False
            for paper in papers_list:
                if not isinstance(paper, dict):
                    print(f'⚠️ Unexpected paper format for {key}: {paper} - skipping')
                    continue
                # collect some meta info (optional)
                otype = paper.get('otype', '')
                sub_obj = paper.get('subType',{})
                ratings_val = paper.get('ratingsForSort', None)
                # avoid noisy debug prints in normal runs
                # print(f"{key}: {otype}, {sub_obj.get('label') if isinstance(sub_obj, dict) else sub_obj}, {ratings_val}")
                if otype:
                    otypes.append(otype)
                this_is_a_journal_paper = False
                if isinstance(sub_obj, dict):
                    sub_label = sub_obj.get('label')
                    if sub_label:
                        subtypes.append(sub_label)
                    if sub_label in ['Konferenciaközlemény (Egyéb konferenciaközlemény)', 'Konferenciaközlemény (Könyvrészlet)']:
                        found_the_conference_version = True
                        mtmt_to_core[paper.get('mtid', 'N/A')] = rank_name.replace('star','*')
                    if sub_label in ['Folyóiratcikk (Tudományos folyóirat)', 'Folyóiratcikk (Egyéb folyóirat)']:
                        this_is_a_journal_paper = True
                # map ratingsForSort to numeric rank via rank_map; unknown values -> 'N/A' bucket if present
                if ratings_val in rank_map:
                    r = rank_map[ratings_val]
                    if r < best_rank:
                        best_rank = r
                else:
                    # treat unknown as 'N/A' fallback
                    if this_is_a_journal_paper:
                        na_rank = 6
                    else:
                        na_rank = 7
                    if na_rank < best_rank:
                        best_rank = na_rank

            if not found_the_conference_version:
                print(f"⚠️ Nem található a konferenciacikk verzió az MTMT-ben: {key} - {paper_dblp[key].get('title','N/A')}")
                #if best_rank == 6:
                #    best_rank = 8

            ratings.append(best_rank)

        for key, paper_mtmt in papers.items():
            if isinstance(paper_mtmt, dict):
                process_paper(key, [paper_mtmt],paper_dblp)
            else:
                process_paper(key, paper_mtmt,paper_dblp)

        count_otypes = Counter(otypes)
        count_subtypes = Counter(subtypes)
        count_ratings = Counter(ratings)
        print("Rank:", rank_name)
        print("Otypes:", count_otypes)
        print("Subtypes:", count_subtypes)
        print("Ratings:", count_ratings)
        # Store ratings for this rank
        ratings_by_rank[rank_name] = count_ratings

    # Save mtmt_to_core mapping to JSON file
    output_file = 'mtmt_to_core_mapping.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(mtmt_to_core, f, ensure_ascii=False, indent=2)
    print(f"\n✓ MTMT to CORE mapping saved to {output_file} ({len(mtmt_to_core)} entries)")
    
    # Kategóriák és pozíciók: használjuk a rank_map sorrendjét az x tengelyen
    # union of all numeric rank keys present in any rank
    all_keys = set()
    for ratings in ratings_by_rank.values():
        all_keys |= set(ratings.keys())
    categories = sorted(all_keys, key=lambda k: int(k))
    
    x = np.arange(len(categories))
    num_ranks = len(rank_names)
    bar_width = 0.8 / num_ranks  # oszlopok közti távolság dinamikusan
    
    # inverse mapping: numeric rank -> label name (e.g. 1 -> 'D1')
    inv_rank_map = {v: k for k, v in rank_map.items()}
    labels = [inv_rank_map.get(cat, str(cat)) for cat in categories]

    # prepare values for plotting - collect all values
    values_by_rank = {}
    all_values = []
    for rank in rank_names:
        values = [ratings_by_rank[rank].get(k, 0) for k in categories]
        values_by_rank[rank] = values
        all_values.extend(values)
    
    maxv = max(all_values) if all_values else 0

    # Colors for each rank
    colors = {'Astar': 'green', 'A': 'brown', 'B': 'orange', 'C': 'purple'}
    
    # Oszlopdiagram egymás mellett - nagyobb ábra és nagyobb betűk
    plt.rcParams.update({'font.size': 12})  # base font size
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Plot bars for each rank
    bars_dict = {}
    for i, rank in enumerate(rank_names):
        offset = (i - (num_ranks - 1) / 2) * bar_width
        label = rank.replace('star', '*')
        color = colors.get(rank, f'C{i}')
        bars = ax.bar(x + offset, values_by_rank[rank],
                width=bar_width, color=color, label=label)
        bars_dict[rank] = bars

    # Annotate bars with counts (larger annotation font)
    def annotate_bars(ax, bars, values):
        for bar, val in zip(bars, values):
            if val > 0:  # Only annotate non-zero bars
                h = bar.get_height()
                y = min( h + (maxv * 0.03 if maxv>0 else 0.1), maxv)
                ax.text(bar.get_x() + bar.get_width()/2, y, str(int(val)), ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Annotate all rank bars
    for rank in rank_names:
        annotate_bars(ax, bars_dict[rank], values_by_rank[rank])

    # Tengelyek és címek - növelt betűméret
    ax.set_xlabel('SJR-értékelés', fontsize=13)
    ax.set_ylabel('Darabszám', fontsize=13)
    ax.set_title('A konferenciacikkek folyóirat-változatainak SJR-értékelése', fontsize=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.tick_params(axis='y', labelsize=11)
    ax.legend(fontsize=11)
    plt.tight_layout()
    # include extension for saved figure
    os.makedirs('figures', exist_ok=True)
    outpath = "figures/sjr_rating.png"
    fig.savefig(outpath, dpi=150)
    print(f'✅ Saved figure to {outpath}')
    print_latex_table(categories, values_by_rank, labels)

    if show_plots:
        plt.show()
#####
def print_latex_table(categories, values_by_rank, labels):
    # Dynamic LaTeX table generation for all ranks
    latex_lines = []
    latex_lines.append(r"\begin{table}[h]")
    latex_lines.append(r"  \centering")
    
    # Build column specification dynamically: l (label) + r for each rank + r (total)
    num_ranks = len(rank_names)
    col_spec = "l" + "r" * num_ranks + "|r"
    latex_lines.append(f"  \\begin{{tabular}}{{{col_spec}}}")
    latex_lines.append(r"    \toprule")
    
    # Header row with all ranks
    rank_labels = [r.replace('star', '*') for r in rank_names]
    header = "    SJR-értékelés & " + " & ".join([f"CORE {r}" for r in rank_labels]) + r" & Összesen \\"
    latex_lines.append(header)
    latex_lines.append(r"    \midrule")

    # Add data rows
    for i, (cat, label) in enumerate(zip(categories, labels)):
        row_values = [values_by_rank[rank][i] for rank in rank_names]
        total = sum(row_values)
        row_str = f"    {label} & " + " & ".join([str(v) for v in row_values]) + f" & {total} \\\\"
        latex_lines.append(row_str)

    # Add totals row
    totals = [sum(values_by_rank[rank]) for rank in rank_names]
    grand_total = sum(totals)
    
    latex_lines.append(r"    \midrule")
    totals_str = "    Összesen & " + " & ".join([str(t) for t in totals]) + f" & {grand_total} \\\\"
    latex_lines.append(totals_str)
    latex_lines.append(r"    \bottomrule")
    latex_lines.append(r"  \end{tabular}")
    
    # Caption with all ranks mentioned
    rank_list_str = ", ".join([f"CORE {r}" for r in rank_labels])
    latex_lines.append(f"  \\caption{{A konferenciacikkek folyóirat-változatainak SJR-értékelése {rank_list_str} kategóriák szerint}}")
    latex_lines.append(r"  \label{tab:sjr_rating_summary}")
    latex_lines.append(r"\end{table}")

    # Save to file
    os.makedirs('doc/figures', exist_ok=True)
    outpath = "doc/figures/sjr_rating_table.tex"
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(latex_lines))

    print(f'✅ Saved LaTeX table to {outpath}')

if __name__ == "__main__":
    if len(sys.argv)==1:
        papers={}
        for rank_name in rank_names:
            if os.path.exists(f"papers_in_mtmt_{rank_name}.json"):
                with open(f"papers_in_mtmt_{rank_name}.json", "r", encoding="utf-8") as f:
                    papers[rank_name] = json.load(f)
        #with open("missing_in_mtmt.json", "r", encoding="utf-8") as f:
        #    missing_paper = json.load(f)

        #filename='already_abroad_'
        #filename='short_'
        #base_path='hungarian_papers_'
        missing_paper = download_mtmt_papers(papers, force_download=False)
    else:
        print("Force download enabled")
        missing_paper = download_mtmt_papers({}, force_download=True)
    if len(missing_paper)>0:
        print("Minden MTMT keresés sikeresen lefutott.")
    #plot_missing_papers_histogram(papers)
    plot_journal_versions(papers)
    