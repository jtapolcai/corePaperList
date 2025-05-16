# -*- coding: utf-8 -*-
# compatible with python 3.5
import requests
import csv
import re
import xml.etree.ElementTree as ET
import unicodedata
import json
from collections import defaultdict
import io
from urllib.parse import quote
import time
import os
from unidecode import unidecode
from google_author_sheet import download_author_google_sheet,remove_accents, generate_author_google_sheet, fix_encoding, get_year_range, parse_affiliation, is_year_range

url = "https://docs.google.com/spreadsheets/d/124qQX0h0CqPZZhBJiUT7myNqonp4dLJ4uyYZTtfauZI/export?format=csv"

#the list of hungarian research institutions
institutions = {
    "BME": ["bme", "budapest university of technology", "műegyetem"],
    "ELTE": ["elte", "loránd eötvös", "eötvös loránd university"],
    "SZTE": ["szte", "szegedi tudományegyetem", "university of szeged"],
    "ÓE": ["óbudai egyetem", "obuda university"],
    "SZTAKI": ["sztaki", "institute for computer science and control"],
    "PPKE": ["ppke", "pázmány", "peter pazmany", "pazmany peter"],
    "Corvinus": ["corvinus"],
    "Rényi": ["rényi", "renyi", "alfréd rényi", "renyi alfréd", "rényi alfréd institute", "renyi institute","ranki"],
    "Ericsson": ["ericsson", "ericsson research"],
    "Hungary": ["mta", "hungarian", "hungary","budapest","debrecen"],
}
# for BME we have 3 departments
departments = {
    "BME-TMIT": ["bme-tmit", "department of telecommunications and media informatics","telecommunications and artificial intelligence"],
    "BME-HIT": ["bme-hit", "department of networked systems and services"],
    "BME-MIT": ["bme-mit", "department of measurement and information systems"]
}

regular_paper_list=["FERO: Fast and Efficient", 
                  "Horn Belief Contraction", 
                  "Consistent Scene Graph Generation by Constraint Optimization", 
                  "Massively Multilingual Sparse Word Representations",
                  "Understanding Packet Pair Separation Beyond the Fluid Model: The Key Role of Traffic Granularity",
                  "You are what you like! Information leakage through users' Interests",
                  "Fooling a Complete Neural Network Verifier",
                  "Fast classification using sparse decision DAGs",
                  "Continuous Time Associative Bandit Problems." 
                ]
short_paper_list = ["Mining Hypernyms Semantic Relations from Stack Overflow"]

doi_short_paper_list = ["FINDINGS-ACL","ICDMW5","ACL-SRW" ]

def has_worked_in_hungary(author_name):
    global author_classified_with_aliases
    author_name_=remove_accents(author_name)
    author_info = author_classified_with_aliases.get(author_name_)
    if author_info:
        if "location" in author_info:
            if len(author_info["location"])>0:
                return True
    return False

def classify_author(author_name, year):
    global author_classified_with_aliases
    author_name_ = remove_accents(author_name)
    author_info = author_classified_with_aliases.get(author_name_)
    if author_info:
        for location in author_info["location"]:
            if "Hungary" in location and is_year_range(location, year):
                return {
                    "location": "Hungary",
                    "institution": author_info.get("institution", "Unknown"),
                    "department": author_info.get("department", "Unknown")
                }
    return {
        "location": "Unknown",
        "institution": "Unknown",
        "department": "Unknown"
    }

def classify_paper_by_author(author_list, year):
    hungarian = 0
    not_hungarian = 0
    ret = []
    for author in author_list:
        author_cls = classify_author(author, year)
        if author_cls["location"] == "Hungary":
            hungarian += 1
            for field in ["institution", "department"]:
                if author_cls[field] != "Unknown":
                    if author_cls[field] not in ret:
                        ret.append(author_cls[field])
        else:
            not_hungarian += 1
    if hungarian == 0:
        return ret
    if hungarian <= not_hungarian:
        ret.append("international")
    elif not_hungarian == 0:
        ret.append("all_hungarian")
    else:
        ret.append("mostly_hungarian")
    return ret

def is_short_paper(info, venue):
    limit = 6
    if venue in ["SODA", "STOC", "FOCS"]:
        limit = 3
    if venue in ["WWW"]:
        limit = 8
    if "Workshop" in venue:
        return True
    title = info.get("title", "N/A")
    for title_ in regular_paper_list:
        if title.startswith(title_):
            return False
    for title_ in short_paper_list:
        if title.startswith(title_):
            return True
    pages_str = info.get("pages", "")
    if pages_str != "":
        if ":" not in pages_str:
            pages = re.split(r"[-:]", pages_str)
            if len(pages) > 1 and pages[1] != "":
                pagenum = int(pages[1]) - int(pages[0])
                if pagenum < limit:
                    return True
            else:
                #print("single page!")
                return True
        else:
            parts = re.split(r"[-–]", pages_str)
            if len(parts) > 1:
                try:
                    start = int(re.findall(r"\d+", parts[0])[-1])
                    end = int(re.findall(r"\d+", parts[1])[-1])
                    pagenum = end - start + 1
                    if pagenum < limit:
                        return True
                except Exception:
                    return True  # Ha nem sikerült a konverzió, legyen short paper
            else:
                return True  # Egyoldalas vagy nem értelmezhető
    else:
        #print("no page is given!")
        return True
    for doi_ in doi_short_paper_list:
        if doi_ in info.get("doi", ""):
            return True
    return False

all_authors=[]
def process_paper(hit,venues,search_log,foreign_papers,short_papers):
    global all_authors
    info=hit.get("info")
    type = info.get("type")
    if type!="Conference and Workshop Papers":
        return None, None, search_log
    title = info.get("title", "N/A")
    if title.lower()=="Masked Latent Semantic Modeling: an Efficient Pre-training Alternative to Masked Language Modeling.".lower():
        print("itt")
    venue = info.get("venue", "")
    if venue.upper() not in venues:
        return None, None, search_log
    year = int(info.get("year", 0))
    if not is_year_range(venues[venue.upper()]["YearsInterval"], year, 0): ### tollerate was 1
        return None, None, search_log + "Skip as {} is not in the right year {}".format(venue, year)

    record = {}
    key = info.get("key", "")
    record["key"] = key
    record["title"] = title
    record["venue"] = venue
    record["year"] = str(year)
    record["pages"] = info.get("pages", "")
    record["doi"] = info.get("doi", "")
    record["ee"] = info.get("ee", "")
    record["url"] = info.get("url", "")

    # Authors
    author_list_raw = info.get("authors", {}).get("author", [])
    if isinstance(author_list_raw, list):
        author_list = [a.get("text", "") for a in author_list_raw]
        ######
        for a in author_list_raw:
            author_name=a.get("text", "")
            author_did=a.get("@pid", "")
            if (author_name,author_did) not in all_authors:
                all_authors.append((author_name,author_did))
    else:
        author_list = [author_list_raw.get("text", "")]

    
    record["authors"] = author_list
    authors_str = ", ".join(author_list)
    ptype = classify_paper_by_author(author_list, year)
    record["classfiied"] = ptype

    paper_str = "{} {} {} - {} ".format(venue, year, authors_str, title)

    if len(ptype)==0:
        foreign_papers[key] = record
        return None, None, search_log + "\n Warning! no hungarian authors {}".format(paper_str)

    if is_short_paper(info, venue):
        short_papers[key] = record
        return None, None, search_log + "\n Skip as too short {}".format(paper_str)

    return key, record, search_log + "\n Add {}".format(paper_str)


authors_data=download_author_google_sheet()

# next we handle the aliases, ie. if the author used multiple names, we add both names to the authors_data
author_classified_with_aliases = {}
for name, data in authors_data.items():
    key_main = remove_accents(name)
    author_classified_with_aliases[key_main] = data
    aliases = data.get("basic_info", {}).get("aliases", {})
    for alias in aliases.values():
        key_alias = remove_accents(alias)
        author_classified_with_aliases[key_alias] = data

with open("author_classified_with_aliases.json", "w", encoding="utf-8") as f:
    json.dump(author_classified_with_aliases, f, indent=2, ensure_ascii=False)


def query_DBLP(author_classified_with_aliases,force): 
    os.makedirs("dblp", exist_ok=True)

    author_list = list(author_classified_with_aliases.items())
    full_log = ""
    counter = 0
    i = 0

    while i < len(author_list):
        author, author_cls = author_list[i]

        if not author_cls.get("location"):
            full_log += "{} is not working in Hungary\n".format(author)
            i += 1
            continue

        author_safe = remove_accents(author).replace(" ", "_")
        output_path = os.path.join("dblp", "{}.json".format(author_safe))

        if not force and os.path.exists(output_path):
            #print(f"Skip {author} (already exists)")
            i += 1
            continue

        author_query = remove_accents(author)
        url = "https://dblp.org/search/publ/api?q=author:{}&h=1000&format=json".format(quote(author_query))

        try:
            print("Fetching: {}".format(author))
            time.sleep(0.5)
            response = requests.get(url)
            counter += 1

            if counter % 100 == 0:
                print("Pause after {} queries".format(counter))
                time.sleep(10)
            if counter % 1000 == 0:
                print("Too many queries – exiting")
                break

            if response.status_code != 200:
                raise Exception("HTTP error {}".format(response.status_code))

            data = response.json()
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            i += 1

        except Exception as e:
            print("Error with {}: {}".format(author,e))
            time.sleep(20)

    # Log mentése
    with open("dblp_fetch_log.txt", "w", encoding="utf-8") as f:
        f.write(full_log)

    print("DBLP JSON lekérések kész, elmentve: dblp/")


##################
#step 1: perform DBLP queries
query_DBLP(author_classified_with_aliases,False)

#step 2: process papers
for rank_name in ["Astar", "A"]:
    print("Search for Core {} papers".format(rank_name))

    # Konferencia lista betöltése
    with open('core_{}_conferences_classified.json'.format(rank_name), 'r', encoding='utf-8') as f:
        venues = {k.upper(): v for k, v in json.load(f).items()}
        #json.load(f)

    papers = {}
    foreign_papers = {}
    short_papers = {}
    search_log = ""

    for author, author_cls in author_classified_with_aliases.items():
        if not author_cls.get("location"):
            search_log += "\n{} is not working in Hungary\n".format(author)
            continue
        author_safe = remove_accents(author).replace(" ", "_")
        path = os.path.join("dblp", author_safe+".json")
        if not os.path.exists(path):
            print("{} not found ".format(path))
            continue

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                hits = data.get("result", {}).get("hits", {}).get("hit", [])
            except Exception as e:
                print("Error loading {}: {}".fromat(path,e))
                continue

        affil = author_cls.get("affiliations", [])
        search_log += "\n{} {} {}".format(author,len(hits),' '.join(affil) if isinstance(affil, list) else affil)
        if "Akos K. Matszangosz"==author:
            print("itt")
        for hit in hits:
            key, record, search_log = process_paper(hit, venues, search_log, foreign_papers, short_papers)
            if key and key not in papers:
                papers[key] = record

    # Mentés
    with open("parsed_core_{}_papers.json".format(rank_name), "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)
    print("Elmentve: parsed_core_{}_papers.json".format(rank_name))


                        
    print("Number of papers found {}".format(len(papers)))
    # --- Save the log file ---
    with open("log_{}_dblp.txt".format(rank_name), "w", encoding="utf-8") as f:
        f.write(search_log)
    with open('already_abroad_papers_core{}.json'.format(rank_name), 'w') as f:
        json.dump(foreign_papers, f, indent=2)
    with open('short_papers_core{}.json'.format(rank_name), 'w') as f:
        json.dump(short_papers, f, indent=2)
    with open('hungarian_papers_core{}.json'.format(rank_name), 'w') as f:
        json.dump(papers, f, indent=2)

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
        return ''.join(latex_map.get(c, c) for c in text)

    def json_to_bibtex_entry(key, entry, all_keywords):
        bibkey = key.replace("conf/", "").replace("/", "")[:30]
        authors = entry.get("authors", [])
        for author in authors:
            author_publication_count[author] += 1

        authors_bib = convert_to_latex_hungarian(" and ".join(authors))
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

    for key, paper in papers.items():
        bibtex_entries.append(json_to_bibtex_entry(key, paper, all_keywords))

    # --- Mentés .bib fájlba ---
    with open("core{}.bib".format(rank_name), "w", encoding="utf-8") as f:
        f.write("\n\n".join(bibtex_entries))

    #print(", ".join(all_keywords))
    import sys
    print(", ".join(all_keywords).encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))


    if True:
        #print("\n📊 Szerzők legalább 5 publikációval:")
        author_list=""
        for author, count in sorted(author_publication_count.items(), key=lambda x: -x[1]):
            if count >= 5 and has_worked_in_hungary(author):
                #print("{}: {count} publikáció".format(author))
                if author_list!="":
                    author_list+="|"
                author_list+=author
    else:
        # --- Mohó lefedő szerzői lista generálása ---
        from collections import defaultdict

        # 1. építsük fel: melyik szerző melyik cikkekben szerepel
        author_to_papers = defaultdict(set)
        paper_to_authors = {}

        for key, paper in papers.items():
            authors = paper.get("authors", [])
            paper_to_authors[key] = authors
            for author in authors:
                author_to_papers[author].add(key)

        # 2. Mohó algoritmus: minden cikkből legyen egy szerző, minél kevesebb szerzővel
        uncovered_papers = set(papers.keys())
        selected_authors = set()

        while uncovered_papers:
            # Válasszuk ki azt a szerzőt, aki a legtöbb még lefedetlen cikkben szerepel
            best_author = None
            best_cover = set()
            for author, authored_papers in author_to_papers.items():
                if has_worked_in_hungary(author):
                    cover = authored_papers & uncovered_papers
                    if len(cover) > len(best_cover):
                        best_author = author
                        best_cover = cover
            if not best_author:
                break  # nem találtunk további fedezést (elméletileg nem fordulhat elő)

            selected_authors.add(best_author)
            uncovered_papers -= best_cover

        # 3. Kiírás
        #print("\n✅ Lefedéshez kiválasztott minimális szerzőhalmaz (mohó):")
        #for author in sorted(selected_authors):
        #    print(" - {}".format(author))
        #print("📦 Összesen {} szerző fedi le az összes cikket.".format(len(selected_authors)))

        author_list=""
        for author in sorted(selected_authors):
            if author_list!="":
                author_list+="|"
            author_list+=re.sub(r'\d+', '', author).strip()

    #print(author_list.encode("utf-8"))
    print(author_list.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))

# Finally, copy result to the worldpress folder
with open('all_authors.json'.format(rank_name), 'w') as f:
        json.dump(all_authors, f, indent=2)

#authors_data = download_author_google_sheet()

generate_author_google_sheet(authors_data)

if False:
    import shutil

    src = "core{}.bib".format(rank_name)
    dst = "/mnt/lendulet_website/wordpress/SVN/core{}.bib".format(rank_name)

    try:
        shutil.copy(src, dst)
        print("copied to {}".format(dst))
    except Exception as e:
        print("failed to copy {}".format(src))