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
import pandas as pd
from google_author_sheet import download_author_google_sheet,remove_accents, count_papers_by_author, generate_author_google_sheet, fix_encoding, get_year_range, parse_affiliation, is_year_range
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
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  Missing file: {path}")
        return None


def plot_conference_pies():
    """Plot two pie charts side-by-side for Core A* and Core A conferences.
    Each pie shows: [Elméleti — van cikk, Elméleti — nincs cikk, Gyakorlati — van cikk, Gyakorlati — nincs cikk]
    Colors are fixed as requested in BASE_COLORS.
    """
    labels = ["Elméleti — van cikk", "Elméleti — nincs cikk", "Gyakorlati — van cikk", "Gyakorlati — nincs cikk"]
    colors = BASE_COLORS[:]  # user-requested 4 colors in order

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    for ax, rank in zip(axes, ["Astar", "A"]):
        # load conference classification and papers
        confs = load_json(f"core_{rank}_conferences_classified.json") or {}
        papers = load_json(f"hungarian_papers_core{rank}.json") or {}

        # normalize conference keys and build set of venues that have at least one hungarian paper
        confs_up = {k.upper(): v for k, v in confs.items()}
        venues_with_papers = set()
        for p in papers.values():
            v = (p.get("venue") or "").upper()
            if v:
                venues_with_papers.add(v)

        # counters
        th_with = th_without = pr_with = pr_without = 0
        for conf_name, info in confs.items():
            mta = info.get("mta_class")
            if mta is None:
                continue
            # conf_name in file may differ in case from venues in papers
            conf_key = conf_name.upper()
            has_hun = conf_key in venues_with_papers
            if int(mta) == 3:
                if has_hun:
                    th_with += 1
                else:
                    if "CORE2020" in info["YearsListed"]:
                        th_without += 1
            elif int(mta) == 6:
                if has_hun:
                    pr_with += 1
                else:
                    if "CORE2020" in info["YearsListed"]:
                        pr_without += 1

        sizes = [th_with, th_without, pr_with, pr_without]
        # draw pie
        wedges, texts, autotexts = ax.pie(sizes, colors=colors, startangle=90,
                                         wedgeprops={"edgecolor": "white"}, autopct=lambda pct: f"{int(round(pct/100*sum(sizes)))}",
                                         pctdistance=0.75, textprops={"fontsize": fs})
        ax.set_title(f"Core {rank} konferenciák", fontsize=fs)
        ax.legend([f"{lab}: {sizes[i]}" for i, lab in enumerate(labels)], loc="lower center", bbox_to_anchor=(0.5, -0.25), ncol=1, fontsize=fs)

    outpath = os.path.join(FIG_DIR, "conference_core_Astar_A_pie.png")
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved conference pies to: {outpath}")


def plot_mta_class_pies():
    """Plot distribution of papers per MTA class for Core A* and Core A (pie charts).
    Uses reserved colors for III and VI classes to keep consistent appearance.
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    reserved = {INFORMATIKA[3]: COLOR_III, INFORMATIKA[6]: COLOR_VI}
    counter={}
    ranks=["Astar", "A"]
    for ax, rank in zip(axes, ranks):
        papers = load_json(f"hungarian_papers_core{rank}.json") or {}
        confs = load_json(f"core_{rank}_conferences_classified.json") or {}
        confs_up = {k.upper(): v for k, v in confs.items()}

        cnt = Counter()
        for p in papers.values():
            venue = (p.get("venue") or "").upper()
            m = confs_up.get(venue, {}).get("mta_class")
            key = INFORMATIKA.get(m, f"{m}") if m is not None else "Unknown"
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
        ax.set_title(f"CORE {rank} — tudományági cikkek", fontsize=fs)
        counter[rank]=cnt


    # shared legend with counts
    legend_items = []
    for lab in sorted({l for c in counter.values() for l in c.keys()}, key=lambda x: (0, int(x)) if x.isdigit() else (1, x)):
        total = sum(counter[r][lab] for r in ranks)
        legend_items.append(f"{lab}: {total}")
    fig.legend(legend_items, loc="lower center", ncol=3, fontsize=fs)
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    outpath = "figures/core_Astar_A_class_pies.png"
    plt.rcParams.update({'font.size': fs}) 
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    #plt.tight_layout(rect=(0, 0.03, 1, 1))
    #plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved MTA-class pies to: {outpath}")


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


def plot_stacked_by_year():
    """Create stacked bar chart of papers per year and MTA class for Core A* and Core A.
    Colors are aligned across ranks: III uses COLOR_III, VI uses COLOR_VI, others sampled.
    """
    ranks = ["Astar", "A"]
    for rank in ranks:
        papers = load_json(f"hungarian_papers_core{rank}.json") or {}
        confs = load_json(f"core_{rank}_conferences_classified.json") or {}
        confs_up = {k.upper(): v for k, v in confs.items()}

        by_year = defaultdict(Counter)
        for p in papers.values():
            year = p.get("year")
            if year is None:
                continue
            try:
                y = int(year)
            except Exception:
                continue
            venue = (p.get("venue") or "").upper()
            m = confs_up.get(venue, {}).get("mta_class")
            lab = str(m) if m is not None else "Unknown"
            by_year[y][lab] += 1

        if not by_year:
            print(f"No year data for CORE {rank}")
            continue

        df = pd.DataFrame.from_dict({y: dict(c) for y, c in by_year.items()}, orient='index').fillna(0).sort_index()
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
        outpath = os.path.join(FIG_DIR, f'core_{rank}_by_year.png')
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


def plot_author_pyramid():
    """Draw mirrored bar chart (pyramid) for authors by paper-count thresholds.
    Expects authors_data_merged.json or authors_data.json where authors have
    fields 'paper_countAstar' and 'paper_countA' and optional 'category' equal to 'theory' or 'applied'.
    """
    authors_data = load_json("authors_data_merged.json")
    if authors_data is None:
        authors_data = load_json("authors_data.json") or {}
    # Küszöbök, amikre összegezni akarjuk
    thresholds = [1,2,3,4,5,10]

    for first_author_only in [True,False]:
        print(f"\n\nFirst author only: {first_author_only}\n")
        author_type = "first" if first_author_only else "all"
        for rank_name in ["Astar", "A"]:
            rank_name_=rank_name.replace("star","*" )
            # Számlálók
            theory_counts = []
            practical_counts = []
            theory_counts_inactive = []
            practical_counts_inactive = []
            count_papers_by_author(authors_data,rank_name=rank_name, first_author_only=first_author_only)
            for min_paper in thresholds:
                # Eredmények kiírása + összesítés
                sum_cat3 = []
                sum_cat6 = []
                sum_cat3_inactive = []
                sum_cat6_inactive = []
                for name, data in authors_data.items():
                    if data["paper_count{}".format(rank_name)]>=min_paper:
                        if "category" in data and data["category"].strip() != "":
                            cat = data["category"]
                            if "status" in data and data["status"] == "inactive":
                                if cat=="theory":
                                    sum_cat3_inactive.append(name)
                                if cat=="applied":
                                    sum_cat6_inactive.append(name)
                            if cat=="theory":
                                sum_cat3.append(name)
                            if cat=="applied":
                                sum_cat6.append(name)
                            #if cat==0:
                            #    print(f"⚠️ Nem kategorizált: {name} ({aux_name})")


                theory_counts.append(len(sum_cat3))
                practical_counts.append(len(sum_cat6))
                theory_counts_inactive.append(len(sum_cat3_inactive))
                practical_counts_inactive.append(len(sum_cat6_inactive))
                print(f"\nÖsszesítés (legalább {min_paper} cikk, első szerzőként):")
                print(f"Elméleti informatika aktív: {[x for x in sum_cat3 if x not in sum_cat3_inactive]}")
                print(f"Elméleti informatika inaktív: {sum_cat3_inactive}")
                print(f"Gyakorlati informatika aktív: {[x for x in sum_cat6 if x not in sum_cat6_inactive]}")
                print(f"Gyakorlati informatika inaktív: {sum_cat6_inactive}")

            # Piramis plot (mirrored horizontal bars)
            y = np.arange(len(thresholds))
            # számítsuk ki az aktív és inaktív darabszámokat
            theory_total = np.array(theory_counts)
            theory_inactive = np.array(theory_counts_inactive)
            theory_active = theory_total - theory_inactive

            practical_total = np.array(practical_counts)
            practical_inactive = np.array(practical_counts_inactive)
            practical_active = practical_total - practical_inactive

            fig, ax = plt.subplots(figsize=(14, 14))
            # Rajzolás sorrendje: először a külső (inaktív, világos) szegmens, majd a belső (aktív, sötét)
            # Bal oldal (negatív irány): a külső inaktív rész megy -total -> -active, majd a belső aktív -active -> 0
            ax.barh(y, theory_inactive, left=-theory_total, color="#F78484")  # külső, világos
            ax.barh(y, theory_active, left=-theory_active, color="#f63d04", label="Elméleti (III)")  # belső, sötét

            # Jobb oldal (pozitív irány): belső aktív 0 -> active, külső inaktív active -> total
            ax.barh(y, practical_active, left=0, color="#0f53db", label="Alkalmazott (VI)")  # belső, sötét
            ax.barh(y, practical_inactive, left=practical_active, color="#79a4fa")  # külső, világos

            # Tengelyek, címkék
            ax.set_yticks(y)
            ax.set_yticklabels([f"≥{t} {rank_name_} cikk" for t in thresholds])
            xmax= max(max(theory_counts), max(practical_counts))
            xmax=((xmax // 20) + 1) * 20  # round up to next multiple of 20
            if xmax<100:
                step=20
            else:
                step=50
            ax.set_xticks(range(-xmax, xmax, step))
            ax.set_xticklabels([str(abs(x)) for x in range(-xmax, xmax, step)])
            ax.set_xlabel("Szerzők száma")
            #ax.set_title("Szerzők elméleti vs gyakorlati megoszlása (piramis)")
            ax.legend(loc="upper right")

            # Annotációk a bárokra
            for i, (lt, li, rt, ri) in enumerate(zip(theory_counts, theory_counts_inactive, practical_counts, practical_counts_inactive)):
                ax.text(-lt - 0.5, i, f"{lt} ({li})", va='center', ha='right', color='black')
                ax.text(rt + 0.5, i, f"{rt} ({ri})", va='center', ha='left', color='black')

            # Tisztább x-tengely feliratok
            #ax.set_xlim(min(left)*1.1, max(right)*1.1)
            #ax.set_xlim(-85, 85) 
            plt.tight_layout()
            outfile=f"figures/author_distribution_{rank_name}_{author_type}.png"
            plt.savefig(outfile)
            print(f"{outfile} is saved")
            #plt.show()


def main():
    mpl.rcParams.update({'font.size': 14})
    plot_conference_pies()
    plot_mta_class_pies()
    plot_stacked_by_year()
    plot_author_pyramid()


if __name__ == '__main__':
    main()
