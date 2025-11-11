# -*- coding: utf-8 -*-
# compatible with python 3.5
import requests
import re
import xmltodict
import json
from collections import defaultdict
from urllib.parse import quote
import os
import pandas as pd
import google_author_sheet
import classify_author
import dblp_utils
import classify_paper #import core_rank, classify_paper, process_paper, all_authors, no_page_is_given


import sys

if "--force" in sys.argv:
    force = True
    print("Force downloading DBLP records (takes a few minutes)")
else:
    force = False


#url = "https://docs.google.com/spreadsheets/d/124qQX0h0CqPZZhBJiUT7myNqonp4dLJ4uyYZTtfauZI/export?format=csv"

pid_to_name = {}
authors_data = None


def author_string(author_field):
    """Backward compatibility shim; moved to classify_paper but kept for existing imports."""
    from classify_paper import author_string as _author_string
    return _author_string(author_field)


def get_dblp_record(author_name):
    author_safe = google_author_sheet.remove_accents(author_name).replace(" ", "_")
    file_path = os.path.join("dblp", author_safe+".json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data.get('dblpperson',{})
            except Exception as e:
                print("Error loading {}: {}".format(file_path,e))
    else:
        print("{} not found ".format(file_path))
    return None  


if __name__ == "__main__":
    authors_data=google_author_sheet.download_author_google_sheet()

    # check is author names are all unique
    author_names = [google_author_sheet.remove_accents(name) for name in authors_data.keys()]
    if len(author_names) != len(set(author_names)):
        print("Warning: Duplicate author names found!")

    #step 1: perform DBLP queries
    dblp_utils.cache_DBLP_query(authors_data,force=force)

    dbld_author={}
    
    #step 2: process papers
    search_log = ""
    papers = {}
    for rank_name in ["A*", "A","B","C","no_rank"]:
        papers[rank_name] = {}
    foreign_papers = {}
    short_papers = {}
    for rank_name in ["A*", "A"]:
        foreign_papers[rank_name] = {}
        short_papers[rank_name] = {}

    for author, author_cls in authors_data.items():
        if not author_cls.get("location"):
            search_log += "\n{} is not working in Hungary\n".format(author)
            #continue
        record = get_dblp_record(author)
        if record is None:
            continue
        papers_found = record.get("r", {})
        person = record.get("person", author)
        dbld_author[author]=person
        affil = author_cls.get("affiliations", [])
        search_log += "\n{} {} {}".format(author,len(papers),' '.join(affil) if isinstance(affil, list) else affil)
        if isinstance(papers_found, dict):
            search_log, papers, foreign_papers, short_papers = classify_paper.process_paper(papers_found, papers, search_log, foreign_papers, short_papers)
        else:
            for paper in papers_found:
                search_log, papers, foreign_papers, short_papers = classify_paper.process_paper(paper, papers, search_log, foreign_papers, short_papers)

    # --- Save the log file ---
    with open("log_dblp.txt", "w", encoding="utf-8") as f:
        f.write(search_log)
    
    for rank in ["A*", "A"]:
        rank_name = rank.replace('*','star')
        if foreign_papers:
            with open('already_abroad_papers_core{}.json'.format(rank_name), 'w') as f:
                json.dump(foreign_papers.get(rank, {}), f, indent=2)
        if short_papers:
            with open('short_papers_core{}.json'.format(rank_name), 'w') as f:
                json.dump(short_papers.get(rank, {}), f, indent=2)

    for rank in ["A*", "A","B","C","no_rank"]:
        rank_name=rank.replace('*','star')
        # Mentés
        with open("hungarian_papers_core{}.json".format(rank_name), "w", encoding="utf-8") as f:
            json.dump(papers[rank], f, indent=2, ensure_ascii=False)
        print("Elmentve: hungarian_papers_core{}.json with {} papers".format(rank_name, len(papers[rank])))


        all_keywords = set()
        author_publication_count = defaultdict(int)

        # --- BibTeX rekordok generálása ---

        def convert_to_latex_hungarian(text):
            latex_map = {
                'á': "\\'a", 'é': "\\'e", 'í': "\\'i", 'ó': "\\'o", 'ö': '\\"o', 'ő': '\\H{o}',
                'ú': "\\'u", 'ü': '\\"u', 'ű': '\\H{u}',
                'Á': "\\'A", 'É': "\\'E", 'Í': "\\'I", 'Ó': "\\'O", 'Ö': '\\"O', 'Ő': '\\H{O}',
                'Ú': "\\'U", 'Ü': '\\"U', 'Ű': '\\H{U}'
            }
            # ensure join gets an iterable of str (not Optional[str]) by using a list comprehension
            return ''.join([latex_map.get(c, c) or c for c in text])

        def json_to_bibtex_entry(key, entry, all_keywords):
            #global pid_to_name
            bibkey = key.replace("conf/", "").replace("/", "")[:30]
            authors = entry.get("authors", [])
            author_names = []
            for author, pid in authors:
                author_=pid_to_name.get('/'+pid, author)
                author_publication_count[author_] += 1
                author_names.append(author_)
            authors_bib = convert_to_latex_hungarian(" and ".join(author_names))
            authors_bib = re.sub(r'\d+', '', authors_bib).strip()

            bibtex = "@inproceedings{{{},\n".format(bibkey)
            bibtex += "  author    = {{{}}},\n".format(authors_bib)
            bibtex += "  title     = {{{}}},\n".format(entry.get('title', ''))
            if "venue" in entry:
                bibtex += "  booktitle = {{{}}},\n".format(entry['venue'])
            if "year" in entry:
                bibtex += "  year      = {},\n".format(entry['year'])
            if "ee" in entry: 
                bibtex += "  doi      = {{{}}},\n".format(entry['ee'])
            if "classfiied" in entry:
                for kw in entry["classfiied"]:
                    all_keywords.add(kw)
                keywords = " and ".join(entry["classfiied"])
                bibtex += "  keywords  = {{{}}}\n".format(keywords)
            bibtex += "}"
            return bibtex

        bibtex_entries = []
        all_keywords = set()

        for key, paper in papers[rank].items():
            bibtex_entries.append(json_to_bibtex_entry(key, paper, all_keywords))

        # --- Mentés .bib fájlba ---
        with open("core{}.bib".format(rank_name), "w", encoding="utf-8") as f:
            f.write("\n\n".join(bibtex_entries))

        #print(", ".join(all_keywords))
        import sys
        print(", ".join(all_keywords).encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))


    # Check for pid collisions in all_authors (same pid used for multiple names)
    def check_pid_collisions(all_authors):
        pid_to_names = {}
        for name, pid in all_authors:
            if not pid:
                continue
            pid_to_names.setdefault(pid, set()).add(name)
        collisions = {pid: names for pid, names in pid_to_names.items() if len(names) > 1}
        if not collisions:
            print("✅ No duplicate names for the same PID in all_authors.")
        else:
            print("⚠️ Found PID collisions (same PID used by multiple names):")
            for pid, names in collisions.items():
                print(" PID {} -> {}".format(pid, ", ".join(sorted(names))))

    #check_pid_collisions(all_authors)

    with open('all_authors.json', 'w') as f:
        json.dump(classify_paper.all_authors, f, indent=2)

    with open('papers_with_no_page.json', 'w') as f:
        json.dump(classify_paper.no_page_is_given, f, indent=2)

    google_author_sheet.generate_author_google_sheet(authors_data)

    if False:
        import shutil

        src = "core{}.bib".format(rank_name)
        dst = "/mnt/lendulet_website/wordpress/SVN/core{}.bib".format(rank_name)

        try:
            shutil.copy(src, dst)
            print("copied to {}".format(dst))
        except Exception as e:
            print("failed to copy {}".format(src))