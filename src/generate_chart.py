#!/usr/bin/env python3
"""generate_chart.py

Utility script to regenerate the figures used by the notebooks.

The script reads repository JSON files (Hungarian paper lists, conference
classifications and authors data) and writes PNG figures into the ``figures/``
directory. It is tolerant of missing input files and prints helpful warnings
when data are unavailable.

Usage:
    python generate_chart.py

This module focuses on producing reproducible charts and keeping color
assignments consistent between runs.
"""
import os
import json
from collections import Counter, defaultdict
import math
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm, colors
import sys
import os
# Add both parent (for tudometer) and current dir (src/) to path
_parent = os.path.dirname(os.path.dirname(__file__))
_src = os.path.dirname(__file__)
if _parent not in sys.path:
    sys.path.insert(0, _parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

import pandas as pd
import google_author_sheet
import tudometer
import dblp_utils
import classify_paper
# import download_author_google_sheet,remove_accents, count_papers_by_author, generate_author_google_sheet, fix_encoding, get_year_range, parse_affiliation, is_year_range
import numpy as np

BASE_COLORS = ["#d62828", "#f7a1b0", "#5483c2", "#90caf9"]
OTHER_COLOR = "#d3d3d3"

# canonical colors for specific MTA classes
COLOR_III = BASE_COLORS[0]
COLOR_ELMELETI_NO = BASE_COLORS[1]
COLOR_VI = BASE_COLORS[2]
COLOR_GYAKORLATI_NO = BASE_COLORS[3]

fs = 24  # font size for plots

FIG_DIR = "figures"
os.makedirs(FIG_DIR, exist_ok=True)

# MTA label names (from the notebook)
MTA_CLASSES = {
    1: "I. Nyelv- és Irodalomtudományok Osztálya",
    2: "II. Filozófiai és Történettudományok Osztálya",
    3: "III. Matematikai Tudományok Osztálya",
    4: "IV. Agrártudományok Osztálya",
    5: "V. Orvosi Tudományok Osztálya",
    6: "VI. Műszaki Tudományok Osztálya",
    7: "VII. Kémiai Tudományok Osztálya",
    8: "VIII. Biológiai Tudományok Osztálya",
    9: "IX. Gazdaság- és Jogtudományok Osztálya",
    10: "X. Földtudományok Osztálya",
    11: "XI. Fizikai Tudományok Osztálya",
}

INFORMATIKA = {
    3: "Elméleti informatika",
    6: "Alkalmazott informatika",
}

def load_json(path):
    # Use centralized loader which prefers results/ and caches reads
    try:
        from io_utils import load_json as _load_json
    except Exception:
        # fallback: try direct open
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️  Missing file: {path}")
            return None
    return _load_json(path)


def plot_conference_pies(core_table):
    """Plot two pie charts side-by-side for Core A* and Core A conferences.
    Each pie shows: [Elméleti — van cikk, Elméleti — nincs cikk, Gyakorlati — van cikk, Gyakorlati — nincs cikk]
    Colors are fixed as requested in BASE_COLORS.
    """
    labels = ["Elméleti — van cikk", "Elméleti — nincs cikk", "Gyakorlati — van cikk", "Gyakorlati — nincs cikk"]
    colors = BASE_COLORS[:]  # user-requested 4 colors in order

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    sizes_by_rank = {}
    for ax, rank in zip(axes, ["Astar", "A"]):
        # load conference classification and papers
        papers = load_json(f"hungarian_papers_core{rank}.json") or {}

        venues_with_papers = set()
        for p in papers.values():
            venue = (p.get("venue") or "").upper()
            venue = classify_paper.remove_numbers_and_parentheses(venue).upper()
            if venue:
                venues_with_papers.add(venue)

        # counters
        th_with = th_without = pr_with = pr_without = 0
        for idx, row in core_table.iterrows():
            mta=row["mta_class"] 
            if pd.isna(mta):
                continue
            # conf_name in file may differ in case from venues in papers
            conf_key = row['Acronym'].upper()
            has_hun = conf_key in venues_with_papers
            years_listed = row.get("YearsListed", "")
            listed_now=f"CORE2020_{rank.replace('star', '*')}" in years_listed
            if int(mta) == 3:
                if has_hun:
                    th_with += 1
                else:
                    if listed_now:
                        th_without += 1
            elif int(mta) == 6:
                if has_hun:
                    pr_with += 1
                else:
                    if listed_now:
                        pr_without += 1

        sizes = [th_with, th_without, pr_with, pr_without]
        # store sizes for later LaTeX table export
        sizes_by_rank[rank] = sizes
        # draw pie
        wedges, texts, autotexts = ax.pie(sizes, colors=colors, startangle=90,
                                         wedgeprops={"edgecolor": "white"}, autopct=lambda pct: f"{int(round(pct/100*sum(sizes)))}",
                                         pctdistance=0.75, textprops={"fontsize": fs})
        ax.set_title(f"Core {rank} konferenciák", fontsize=fs)
        ax.legend([f"{lab}: {sizes[i]}" for i, lab in enumerate(labels)], loc="lower center", bbox_to_anchor=(0.5, -0.25), ncol=1, fontsize=fs)

    outpath = os.path.join(FIG_DIR, "conference_core_Astar_A_pie.png")
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    #plt.show()
    plt.close(fig)
    print(f"Saved conference pies to: {outpath}")

    # Generate LaTeX table summarizing the pie counts
    try:
        generate_conference_pies_table(sizes_by_rank, labels)
    except Exception as e:
        print(f"⚠️ Failed to write conference pies LaTeX table: {e}")


def plot_mta_class_pies(authors_data, core_table):
    """Plot distribution of papers per MTA class for Core A* and Core A (pie charts).
    Uses reserved colors for III and VI classes to keep consistent appearance.
    """
    reserved = {INFORMATIKA[3]: COLOR_III, INFORMATIKA[6]: COLOR_VI}
    ranks=["Astar", "A"] #,"B","C","no_rank"
    for file in ["hungarian", "already_abroad"]:
        counter={}
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        for ax, rank in zip(axes, ranks):
            papers = load_json(f"{file}_papers_core{rank}.json") or {}
            
            cnt = Counter()
            for p in papers.values():
                venue = (p.get("venue") or "")
                venue = classify_paper.remove_numbers_and_parentheses(venue).upper()
                acronym_row, short_paper = classify_paper.identify_conference(venue, p.get("crossref"), p.get("url"))
                m = acronym_row.get("mta_class",None) if acronym_row is not None else None
                # Handle case where loc returns a Series (multiple rows)
                if isinstance(m, pd.Series):
                    m = m.iloc[0] if len(m) > 0 else None
                # Convert to int if m is a valid number
                if m is not None and not pd.isna(m):
                    try:
                        m = int(m)
                    except (ValueError, TypeError):
                        pass
                # Treat missing/NaN as Unknown to avoid 'nan' label
                if m is None or pd.isna(m):
                    key = "Unknown"
                else:
                    key = INFORMATIKA.get(m, f"{m}")
                if key not in ["Elméleti informatika", "Alkalmazott informatika"]:
                    print(f"⚠️ Unknown MTA class for venue: {venue} (mta_class={m}) in paper ID {p.get('id')}")
                cnt[key] += 1

            items = cnt.most_common()
            # keep top 4 and aggregate rest as Other
            if len(items) > 4:
                top = items[:4]
                other = sum(c for _, c in items[4:])
                labels = [k for k, _ in top] + ["Other"]
                sizes = [c for _, c in top] + [other]
            else:
                labels = [k for k, _ in items]
                sizes = [c for _, c in items]

            # map label -> color: give priority to reserved mapping for III/VI
            label_color_map = {}
            for l in labels:
                if l == "Other":
                    label_color_map[l] = OTHER_COLOR
                elif l in reserved:
                    label_color_map[l] = reserved[l]
                else:
                    # assign next color from palette (skip those reserved)
                    label_color_map[l] = next_color_for_label(l, reserved_vals=set(reserved.values()))

            colors = [label_color_map.get(l, OTHER_COLOR) for l in labels]

            wedges, texts, autotexts = ax.pie(sizes, #labels=[l if sizes[i] > 0 else "" for i, l in enumerate(labels)],
                                            colors=colors, startangle=90, wedgeprops={"edgecolor": "white"},
                                            autopct=lambda pct: f"{int(round(pct/100*sum(sizes)))}", pctdistance=0.7,
                                            textprops={"fontsize": fs})
            ax.set_title(f"CORE {rank.replace('star', '*')} — tudományági cikkek", fontsize=fs)
            counter[rank]=cnt


        # shared legend with counts
        legend_items = []
        for lab in sorted({l for c in counter.values() for l in c.keys()}, key=lambda x: (0, int(x)) if x.isdigit() else (1, x)):
            total = sum(counter[r][lab] for r in ranks)
            legend_items.append(f"{lab}: {total}")
        fig.legend(legend_items, loc="lower center", ncol=3, fontsize=fs)
        plt.tight_layout(rect=(0, 0.03, 1, 1))
        title="Magyar affiliációval rendelkező cikkek"
        if file=="already_abroad":
            title="Csak külföldi affiliációval rendelkező cikkek magyar szerzőktől"
        fig.suptitle(title, fontsize=fs, y=1.07)
        outpath = f"figures/{file}_core_Astar_A_class_pies.png"
        plt.rcParams.update({'font.size': fs}) 
        plt.savefig(outpath, dpi=150, bbox_inches='tight')
        #plt.tight_layout(rect=(0, 0.03, 1, 1))
        #plt.savefig(outpath, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved MTA-class pies to: {outpath}")
        
        # Generate LaTeX table
        generate_latex_table(counter, file, ranks)


def generate_latex_table(counter, file, ranks):
    """Generate LaTeX table summarizing paper counts by MTA class and CORE rank.
    
    Args:
        counter: dict with rank keys ('Astar', 'A') containing Counter objects
        file: str, either 'hungarian' or 'already_abroad'
        ranks: list of rank names
    """
    # Collect all unique labels
    all_labels = sorted({l for c in counter.values() for l in c.keys()}, 
                       key=lambda x: (0, int(x)) if x.isdigit() else (1, x))
    
    # Build LaTeX table
    latex_lines = []
    latex_lines.append(r"\begin{table}[h]")
    latex_lines.append(r"  \centering")
        # Caption based on file type
    if file == "hungarian":
        caption = "Magyar affiliációval rendelkező cikkek CORE A* és A konferenciákon"
    else:
        caption = "Csak külföldi affiliációval rendelkező cikkek magyar szerzőktől CORE A* és A konferenciákon"
    
    latex_lines.append(f"  \\caption{{{caption}}}")
    latex_lines.append(f"  \\label{{tab:{file}_core_summary}}")
    latex_lines.append(r"  \begin{tabular}{l|rr|r}")
    latex_lines.append(r"    \toprule")
    latex_lines.append(r"    Tudományterület & CORE A* & CORE A & Összesen \\")
    latex_lines.append(r"    \midrule")
    
    # Data rows
    total_astar = 0
    total_a = 0
    for lab in all_labels:
        count_astar = counter.get('Astar', {}).get(lab, 0)
        count_a = counter.get('A', {}).get(lab, 0)
        total = count_astar + count_a
        total_astar += count_astar
        total_a += count_a
        latex_lines.append(f"    {lab} & {count_astar} & {count_a} & {total} \\\\")
    
    #latex_lines.append(r"    \midrule")
    latex_lines.append(f"    Összesen & {total_astar} & {total_a} & {total_astar + total_a} \\\\")
    latex_lines.append(r"    \bottomrule")
    latex_lines.append(r"  \end{tabular}")
    latex_lines.append(r"\end{table}")
    
    # Save to file
    os.makedirs("doc/figures", exist_ok=True)
    outpath = f"doc/figures/{file}_summary_table.tex"
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(latex_lines))
    
    print(f"Saved LaTeX table to: {outpath}")


def generate_conference_pies_table(sizes_by_rank, labels):
    """Write a LaTeX table for the conference pie counts using booktabs rules.

    Args:
        sizes_by_rank: dict mapping rank name ('Astar','A') to list of four sizes
        labels: list of label names in the same order as sizes
            [0] = "Elméleti — van cikk"
            [1] = "Elméleti — nincs cikk"
            [2] = "Gyakorlati — van cikk"
            [3] = "Gyakorlati — nincs cikk"
    """
    astar_sizes = sizes_by_rank.get('Astar', [0, 0, 0, 0])
    a_sizes = sizes_by_rank.get('A', [0, 0, 0, 0])

    # Extract counts
    theory_astar_with, theory_astar_without, practical_astar_with, practical_astar_without = astar_sizes
    theory_a_with, theory_a_without, practical_a_with, practical_a_without = a_sizes

    latex_lines = []
    latex_lines.append(r"\begin{table}[h]")
    latex_lines.append(r"  \centering")
    latex_lines.append(r"  \caption{Rangos konferenciák, amelyeken már megjelent, illetve még nem jelent meg magyar cikk.}")
    latex_lines.append(r"  \label{tab:conference_pies_summary}")
    latex_lines.append(r"  \begin{tabular}{l|cc|cc}")
    latex_lines.append(r"    \toprule")
    latex_lines.append(r"     & \multicolumn{2}{c|}{CORE A*} & \multicolumn{2}{c}{CORE A} \\")
    latex_lines.append(r"    Kategória & van cikk & nincs cikk & van cikk & nincs cikk \\")
    latex_lines.append(r"    \midrule")
    latex_lines.append(f"    Elméleti & {theory_astar_with} & {theory_astar_without} & {theory_a_with} & {theory_a_without} \\\\")
    latex_lines.append(f"    Gyakorlati & {practical_astar_with} & {practical_astar_without} & {practical_a_with} & {practical_a_without} \\\\")
    latex_lines.append(r"    \midrule")
    # totals
    total_astar_with = theory_astar_with + practical_astar_with
    total_astar_without = theory_astar_without + practical_astar_without
    total_a_with = theory_a_with + practical_a_with
    total_a_without = theory_a_without + practical_a_without
    latex_lines.append(f"    Összesen & {total_astar_with} & {total_astar_without} & {total_a_with} & {total_a_without} \\\\")
    latex_lines.append(r"    \bottomrule")
    latex_lines.append(r"  \end{tabular}")
    latex_lines.append(r"\end{table}")

    os.makedirs("doc/figures", exist_ok=True)
    outpath = os.path.join("doc/figures", "conference_pies_summary.tex")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(latex_lines))

    print(f"Saved conference pies LaTeX table to: {outpath}")


def next_color_for_label(label, reserved_vals=None):
    """Return a reproducible color for a non-reserved label.

    This function uses Matplotlib's ``tab20`` colormap and a deterministic hash
    of the label to select a colour. If the chosen colour conflicts with any
    reserved colours, the function returns ``OTHER_COLOR`` as a fallback.
    """
    if reserved_vals is None:
        reserved_vals = set()
    cmap = cm.get_cmap("tab20")
    # deterministic hash to pick an index
    idx = abs(hash(label)) % 20
    col = colors.to_hex(cmap(idx))
    if col in reserved_vals:
        # fallback to OTHER_COLOR if collision
        return OTHER_COLOR
    return col


def plot_stacked_by_year(authors_data,core_table):
    """Create stacked bar chart of papers per year and MTA class for Core A* and Core A.
    Colors are aligned across ranks: III uses COLOR_III, VI uses COLOR_VI, others sampled.
    """
    ranks = ["Astar", "A"]
    for rank in ranks:
        for file in ["hungarian", "already_abroad"]:
            papers = load_json(f"{file}_papers_core{rank}.json") or {}


            by_year = defaultdict(Counter)
            for p in papers.values():
                year = p.get("year")
                if year is None:
                    continue
                try:
                    y = int(year)
                except Exception:
                    continue
                venue = (p.get("venue") or "")
                venue = classify_paper.remove_numbers_and_parentheses(venue).upper()
                m = core_table.loc[venue, "mta_class"] if venue in core_table.index else None
                # Handle case where loc returns a Series (multiple rows)
                if isinstance(m, pd.Series):
                    m = m.iloc[0] if len(m) > 0 else None
                # Treat missing/NaN mta_class as Unknown to avoid 'nan' column
                if m is None or pd.isna(m):
                    lab = "Unknown"
                else:
                    lab = str(m)
                by_year[y][lab] += 1

            if not by_year:
                print(f"No year data for CORE {rank}")
                continue

            df = pd.DataFrame.from_dict({y: dict(c) for y, c in by_year.items()}, orient='index').fillna(0).sort_index()
            
            # Rename index to 'Year' and convert column names to integers (handle NaN safely)
            df.index.name = 'Year'
            df.columns = [int(float(c)) if (c not in ['Unknown'] and not pd.isna(float(c))) else c for c in df.columns]
        
            # Save DataFrame to CSV
            os.makedirs("doc/figures", exist_ok=True)
            csv_path = os.path.join("doc/figures", f'{file}_core{rank}_by_year.csv')
            df.to_csv(csv_path, encoding='utf-8')
            print(f"Saved CSV to: {csv_path}")
            
            # unify columns order
            cols = list(df.columns)
            # map colors for columns
            color_map = {}
            for col in cols:
                if col == '3':
                    color_map[col] = COLOR_III
                elif col == '6':
                    color_map[col] = COLOR_VI
                else:
                    color_map[col] = next_color_for_label(col, reserved_vals={COLOR_III, COLOR_VI})

            plot_colors = [color_map[c] for c in cols]

            fig, ax = plt.subplots(figsize=(16, 8))
            df.plot(kind='bar', stacked=True, color=plot_colors, ax=ax, width=0.8)
            ax.set_title(f'CORE {rank} — publikációk évenként, MTA osztály szerint', fontsize=20)
            ax.set_xlabel('Év', fontsize=16)
            ax.set_ylabel('Cikkek száma', fontsize=16)
            ax.tick_params(axis='y', labelsize=14)
            # legend labels: convert numeric string labels to roman where appropriate
            handles, legend_labels = ax.get_legend_handles_labels()
            legend_labels2 = []
            for lab in legend_labels:
                try:
                    n = int(lab)
                    legend_labels2.append(int_to_roman(n))
                except Exception:
                    legend_labels2.append(lab)
            ax.legend(handles, legend_labels2, fontsize=12, bbox_to_anchor=(1.02, 1), loc='upper left')
            outpath = os.path.join(FIG_DIR, f'core_{file}_{rank}_by_year.png')
            #plt.show()
            plt.tight_layout(rect=(0, 0.03, 1, 1))
            plt.savefig(outpath, dpi=150, bbox_inches='tight')
            plt.close(fig)
        print(f"Saved stacked-by-year figure to: {outpath}")


def int_to_roman(num):
    if not isinstance(num, int) or num <= 0:
        return str(num)
    vals = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    res = ''
    i = 0
    while num > 0:
        for _ in range(num // vals[i]):
            res += syms[i]
            num -= vals[i]
        i += 1
    return res


# Create side-by-side pie charts for the 'excelence_' statistics (theory vs applied)
def plot_excellence_theory_applied_pies(authors_data):
    # authors_data = load_json("authors_data_merged.json")

    # for first_author_only in [True,False]:
    #     print(f"\n\nFirst author only: {first_author_only}\n")
    #     author_type = "first" if first_author_only else "all"
    #     for rank_name in ["Astar", "A"]:
    #         tudometer.count_papers_by_author(authors_data,first_author_only=first_author_only)
    #         for author, data in authors_data.items():
    #             authors_data[author][f"paper_count{rank_name}_{author_type}"] = authors_data[author][f"paper_count{rank_name}"]

    threasholds={
        'Established_':{
            'coreAstar_first':0,
            'coreAstar_all':0,
            'coreA_all':12,
        },
        'Expert_':{
            'coreAstar_first':0,
            'coreAstar_all':0,
            'coreA_all':6,
        },
        'Rising_':{
            'coreAstar_first':0,
            'coreAstar_all':0,
            'coreA_all':3,
        },
        'Entry_':{
            'coreAstar_first':0,
            'coreAstar_all':0,
            'coreA_all':1,
        },
    }
    statistics={}
    processed=[]
    for key,req in threasholds.items():
        rtypes=["theory","applied"]
        for rtype in rtypes:
            statistics[key+rtype]={
                'hungary-active':[],
                'company':[],
                'abroad':[],
                'retired':[]
            }
        for author, data in authors_data.items():
            if author in processed:
                continue
            if      float(data['First Author Core A* equivalent']) >= req['coreAstar_first'] \
                and int(data["paper_countA*"]) >= req['coreAstar_all'] \
                and float(data['Core A* equivalent']) >= req['coreA_all']:
                processed.append(author)
                if data.get("category","") in rtypes:
                    keyc=key+data["category"]
                else:
                    print(f"Missing theory/applied for {author}")
                    keyc=key+"applied"
                if data.get("status","")!="inactive" and data.get("works","")=="hungary":
                    statistics[keyc]['hungary-active'].append(author)
                elif data.get("works","")=="company":
                    statistics[keyc]['company'].append(author)
                elif data.get("works","")=="abroad":
                    statistics[keyc]['abroad'].append(author)
                elif data.get("works","")=="retired":
                    statistics[keyc]['retired'].append(author)


    for key, value in statistics.items():
        print(f"{key}: {value}")
    stats=statistics
    for key, req in threasholds.items():
        th = stats.get(key + 'theory', {})
        ap = stats.get(key + 'applied', {})

        def counts_for(d):
            # hungary-active + retired as one (dark), company (mid), abroad (light)
            hung = len(d.get('hungary-active', [])) + len(d.get('retired', []))
            comp = len(d.get('company', []))
            abroad = len(d.get('abroad', []))
            return [hung, comp, abroad]

        th_counts = counts_for(th)
        ap_counts = counts_for(ap)
        labels = ['Hungary (active+retired)', 'Company', 'Abroad']

        # color palettes: dark -> lighter
        reds = ['#8B0000', '#D9534F', '#F7A8A8']
        blues = ["#3960a5", '#5b9bd5', '#bfe0ff']

        import matplotlib.pyplot as plt
        # figure a bit wider to fit two separate legends
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))

        # Theory (reds)
        wedges1, texts1, autotexts1 = ax1.pie(
            th_counts,
            colors=reds,
            startangle=90,
            autopct=lambda pct: f"{int(round(pct/100*sum(th_counts)))}",
            pctdistance=0.72,
            wedgeprops={'edgecolor': 'white'}
        )
        ax1.set_title('Elméleti', fontsize=12)

        # Applied (blues)
        wedges2, texts2, autotexts2 = ax2.pie(
            ap_counts,
            colors=blues,
            startangle=90,
            autopct=lambda pct: f"{int(round(pct/100*sum(ap_counts)))}",
            pctdistance=0.72,
            wedgeprops={'edgecolor': 'white'}
        )
        ax2.set_title('Alkalmazott', fontsize=12)

        # Create separate legends under each subplot (axis-relative) so they are not merged
        leg1_labels = [f"{labels[i]}: {th_counts[i]}" for i in range(len(labels))]
        leg2_labels = [f"{labels[i]}: {ap_counts[i]}" for i in range(len(labels))]

        # place each legend just below its axis using axis coordinates; small offset and smaller font
        ax1.legend(leg1_labels, loc='upper center', bbox_to_anchor=(0.5, -0.08), bbox_transform=ax1.transAxes, ncol=1, frameon=False, fontsize=12)
        ax2.legend(leg2_labels, loc='upper center', bbox_to_anchor=(0.5, -0.08), bbox_transform=ax2.transAxes, ncol=1, frameon=False, fontsize=12)

        # reduce bottom margin so legends sit closer to the pies
        fig.subplots_adjust(bottom=0.12, top=0.9, wspace=0.4)

        # Common title (Hungarian) - build compact single-line summary instead of using explicit newlines
        parts = []
        if req.get('coreAstar_first', 0) > 1:
            parts.append(f"legalább {req['coreAstar_first']} Core A* első szerzős cikk")
        if req.get('coreAstar_first', 0) == 1:
            parts.append(f"Core A* első szerzős cikk")
        if req.get('coreAstar_all', 0) > 0:
            parts.append(f"legalább {req['coreAstar_all']} Core A* cikk")
        if req.get('coreA_all', 0) > 0:
            parts.append(f"legalább {req['coreA_all']/3:.1f} Core A*-ekvivalens publikáció")#(Core A cikk 1/3-nak számítva)

        if parts:
            title = f"{key[:-1]}: " + "; ".join(parts)
        else:
            title = f"{key[:-1]}"

        # place suptitle with adjusted y coordinate so it doesn't overlap the axes
        fig.suptitle(title, fontsize=14, y=0.97)

        out = f'figures/{key[:-1]}_theory_applied_pies.png'
        plt.savefig(out, dpi=150, bbox_inches='tight')
        #plt.show()
        print(f'Saved {out}')
    
    # Generate LaTeX table summarizing all excellence categories
    generate_excellence_latex_table(statistics, threasholds)

def generate_excellence_latex_table(statistics, threasholds):
    """Generate a LaTeX table summarizing excellence categories by theory/applied and location.
    
    Args:
        statistics: dict with keys like 'Established_theory', 'Established_applied', etc.
                   each containing {'hungary-active': [...], 'company': [...], 'abroad': [...], 'retired': [...]}
        threasholds: dict with category names and their requirements
    """
    # Category order and display names
    core_level_hun = {
        "Established_": "Befutott",
        "Expert_": "Nemzetközi",
        "Rising_": "Feltörekvő",
        "Entry_": "Aktív"
    }
    categories = []
    for cat,rec in threasholds.items():
        categories.append((cat, f"{core_level_hun[cat]} & $\\geq{rec['coreA_all']}$"))
        #('Expert_', 'Expert'),
    
    latex_lines = []
    latex_lines.append(r"\begin{table}[h]")
    latex_lines.append(r"  \centering")
    latex_lines.append(r"  \caption{Kiválósági kategóriák szerinti szerzők: elméleti/alkalmazott, munkahely szerint (Magyarországon kutatásban aktív, magyar iparban helyezkedett el, illetve külföldön kutatók)}")
    latex_lines.append(r"  \label{tab:excellence_summary}")
    latex_lines.append(r"  \begin{tabular}{lc|rrr|rrr|r}")
    latex_lines.append(r"    \hline")
    latex_lines.append(r"     & & \multicolumn{3}{c|}{Elméleti} & \multicolumn{3}{c|}{Alkalmazott} & \\")
    latex_lines.append(r"    Kategória &A$^*$ ekv. pub. & Aktív & Ipar & Külföld & Aktív & Ipar & Külföld & Össz. \\")
    latex_lines.append(r"    \hline")
    
    grand_total = 0
    for cat_key, cat_name in categories:
        theory_key = cat_key + 'theory'
        applied_key = cat_key + 'applied'
        
        th_stats = statistics.get(theory_key, {})
        ap_stats = statistics.get(applied_key, {})
        
        # Count for theory
        th_hu = len(th_stats.get('hungary-active', [])) + len(th_stats.get('retired', []))
        th_comp = len(th_stats.get('company', []))
        th_abroad = len(th_stats.get('abroad', []))
        th_total = th_hu + th_comp + th_abroad
        
        # Count for applied
        ap_hu = len(ap_stats.get('hungary-active', [])) + len(ap_stats.get('retired', []))
        ap_comp = len(ap_stats.get('company', []))
        ap_abroad = len(ap_stats.get('abroad', []))
        ap_total = ap_hu + ap_comp + ap_abroad
        
        row_total = th_total + ap_total
        grand_total += row_total
        
        latex_lines.append(f"    {cat_name} & {th_hu} & {th_comp} & {th_abroad} & {ap_hu} & {ap_comp} & {ap_abroad} & {row_total} \\\\")
    
    latex_lines.append(r"    \hline")
    
    # Calculate column totals
    total_th_hu = sum(len(statistics.get(cat + 'theory', {}).get('hungary-active', [])) + len(statistics.get(cat + 'theory', {}).get('retired', [])) for cat, _ in categories)
    total_th_comp = sum(len(statistics.get(cat + 'theory', {}).get('company', [])) for cat, _ in categories)
    total_th_abroad = sum(len(statistics.get(cat + 'theory', {}).get('abroad', [])) for cat, _ in categories)
    total_ap_hu = sum(len(statistics.get(cat + 'applied', {}).get('hungary-active', [])) + len(statistics.get(cat + 'applied', {}).get('retired', [])) for cat, _ in categories)
    total_ap_comp = sum(len(statistics.get(cat + 'applied', {}).get('company', [])) for cat, _ in categories)
    total_ap_abroad = sum(len(statistics.get(cat + 'applied', {}).get('abroad', [])) for cat, _ in categories)
    
    latex_lines.append(f"    Összesen & &{total_th_hu} & {total_th_comp} & {total_th_abroad} & {total_ap_hu} & {total_ap_comp} & {total_ap_abroad} & {grand_total} \\\\")
    latex_lines.append(r"    \hline")
    latex_lines.append(r"  \end{tabular}")
    latex_lines.append(r"\end{table}")
    
    os.makedirs("doc/figures", exist_ok=True)
    outpath = os.path.join("doc/figures", "excellence_summary_table.tex")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(latex_lines))
    
    print(f"Saved excellence LaTeX table to: {outpath}")

# a letöltött MTMT rekordok elemzése, hogy milyen folyóiratban jelent meg (javított ratings ábrázolás + annotáció, nagyobb betűkkel)
import json
from collections import Counter
import matplotlib.pyplot as plt
import numpy as np
import os

def plot_mtmt_ratings_comparison():
    # ensure these are Counters (not lists)
    ratings_astar = Counter()
    ratings_a = Counter()
    rank_map={'D1':1,'Q1':2,'Q2':3,'Q3':4,'Q4':5,'N/A':6,'not in MTMT':7}

    from io_utils import load_json
    for rank_name in ["Astar", "A"]:
        fn = f"papers_in_mtmt_{rank_name}.json"
        papers = load_json(fn) or {}
        if papers is None:
            print(f'⚠️ File not found: {fn} - skipping')
            continue

        otypes = []
        subtypes = []
        ratings = []

        def process_paper(key, papers_list):
            # compute the best (smallest) rank for the given paper list
            best_rank = 7
            if len(papers_list)==0:
                print(f'⚠️ No papers found for {key} - skipping')
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
                if isinstance(sub_obj, dict):
                    sub_label = sub_obj.get('label')
                    if sub_label:
                        subtypes.append(sub_label)
                # map ratingsForSort to numeric rank via rank_map; unknown values -> 'N/A' bucket if present
                if ratings_val in rank_map:
                    r = rank_map[ratings_val]
                    if r < best_rank:
                        best_rank = r
                else:
                    # treat unknown as 'N/A' fallback
                    na_rank = rank_map.get('N/A', 6)
                    if na_rank < best_rank:
                        best_rank = na_rank

            ratings.append(best_rank)

        for key, paper_mtmt in papers.items():
            if isinstance(paper_mtmt, dict):
                process_paper(key, [paper_mtmt])
            else:
                process_paper(key, paper_mtmt)

        count_otypes = Counter(otypes)
        count_subtypes = Counter(subtypes)
        count_ratings = Counter(ratings)
        print("Rank:", rank_name)
        print("Otypes:", count_otypes)
        print("Subtypes:", count_subtypes)
        print("Ratings:", count_ratings)
        if rank_name == "Astar":
            ratings_astar = count_ratings
        else:
            ratings_a = count_ratings

    # Kategóriák és pozíciók: használjuk a rank_map sorrendjét az x tengelyen
    # union of numeric rank keys present in either set
    categories = sorted(set(ratings_astar.keys()) | set(ratings_a.keys()), key=lambda k: int(k))
    x = np.arange(len(categories))
    bar_width = 0.35  # oszlopok közti távolság
    # inverse mapping: numeric rank -> label name (e.g. 1 -> 'D1')
    inv_rank_map = {v: k for k, v in rank_map.items()}
    labels = [inv_rank_map.get(cat, str(cat)) for cat in categories]

    # prepare values for plotting
    values_astar = [ratings_astar.get(k, 0) for k in categories]
    values_a = [ratings_a.get(k, 0) for k in categories]
    maxv = max(values_astar + values_a) if (values_astar + values_a) else 0

    # Oszlopdiagram egymás mellett - nagyobb ábra és nagyobb betűk
    plt.rcParams.update({'font.size': 12})  # base font size
    fig, ax = plt.subplots(figsize=(11, 5))
    bars_astar = ax.bar(x - bar_width / 2, values_astar,
            width=bar_width, color='green', label='A*')
    bars_a = ax.bar(x + bar_width / 2, values_a,
            width=bar_width, color='brown', label='A')

    # Annotate bars with counts (larger annotation font)
    def annotate_bars(ax, bars, values):
        for bar, val in zip(bars, values):
            h = bar.get_height()
            y = min( h + (maxv * 0.03 if maxv>0 else 0.1), maxv)
            ax.text(bar.get_x() + bar.get_width()/2, y, str(int(val)), ha='center', va='bottom', fontsize=11, fontweight='bold')

    annotate_bars(ax, bars_astar, values_astar)
    annotate_bars(ax, bars_a, values_a)

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
    #plt.show()

def main():
    mpl.rcParams.update({'font.size': 14})
    authors_data = google_author_sheet.download_author_google_sheet()
    core_table = pd.read_csv(os.path.join("inputs", "core_table.csv"))
    # Convert acronyms to uppercase for case-insensitive matching
    core_table["Acronym"] = core_table["Acronym"].str.upper()
    
    # Expand semicolon-separated Acronym entries into multiple rows
    expanded_rows = []
    for _, row in core_table.iterrows():
        acr_field = row.get("Acronym", "")
        if pd.isna(acr_field):
            continue
        for ac in str(acr_field).split(";"):
            ac = ac.strip().upper()
            if not ac:
                continue
            r = row.copy()
            r["Acronym"] = ac
            expanded_rows.append(r)
    if expanded_rows:
        core_table = pd.DataFrame(expanded_rows)
    
    core_table = core_table.set_index("Acronym", drop=False)
    plot_mta_class_pies(authors_data, core_table)
    plot_stacked_by_year(authors_data, core_table)
    plot_conference_pies(core_table)
    #plot_author_pyramid()
    plot_excellence_theory_applied_pies(authors_data)
    plot_mtmt_ratings_comparison()

if __name__ == '__main__':
    main()
