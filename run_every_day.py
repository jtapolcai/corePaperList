# -*- coding: utf-8 -*-
# compatible with python 3.5
import requests
import csv
import re
import xmltodict
#import xml.etree.ElementTree as ET
import unicodedata
import json
from collections import defaultdict
import io
from urllib.parse import quote
import time
import os
from unidecode import unidecode
from google_author_sheet import download_author_google_sheet,remove_accents, generate_author_google_sheet, fix_encoding, get_year_range, parse_affiliation, is_year_range

import sys

if "--force" in sys.argv:
    force = True
else:
    force = False

print("Force downloading DBLP records (takes a few minutes)")

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
                  "Continuous Time Associative Bandit Problems.",
                  "Negative Hyper-Resolution for Proving Statements Containing Transitive Relations", 
                   "Analysis of Second-Order Markov Reward Models.",
                  "On the Role of Mathematical Language Concept in the Theory of Intelligent Systems.",
                  "Definition Theory as Basis for a Creative Problem Solver.",
                  "Integrating Declarative Knowledge Programming Styles and Tools in a Structured Object AI Environment.",
                  "Parameter Estimation of Geometrically Sampled Fractional Brownian Traffic"
                ]
short_paper_list = ["Mining Hypernyms Semantic Relations from Stack Overflow.",
                    "Embedding-based Automated Assessment of Domain Models.",
                    "Towards Efficient Evaluation of Rule-based Permissions for Fine-grained Access Control in Collaborative Modeling.",
                    "Towards the Formal Verification of SysML v2 Models.",
                    "Driving Requirements Evolution by Engineers&apos; Opinions.",
                    "AI Simulation by Digital Twins: Systematic Survey of the State of the Art and a Reference Framework.",
                    "Participatory and Collaborative Modeling of Sustainable Systems: A Systematic Review.",
                    "Tight Bounds for Planar Strongly Connected Steiner Subgraph with Fixed Number of Terminals (and Extensions)."
                    ]
no_hungarian_affil =[
                    "Text2VQL: Teaching a Model Query Language to Open-Source Language Models with ChatGPT.",
                    "Multi-step Iterative Automated Domain Modeling with Large Language Models.",
                    "Automated Domain Modeling with Large Language Models: A Comparative Study.",
                    "Prompting or Fine-tuning? A Comparative Study of Large Language Models for Taxonomy Construction.",
                    "Digital Twins for Cyber-Biophysical Systems: Challenges and Lessons Learned.",
                    "Collaborative Model-Driven Software Engineering: A Systematic Update.",
                    "Modeling the Engineering Process of an Agent-based Production System: An Exemplar Study.",
                    "Modeling and Enactment Support for Early Detection of Inconsistencies in Engineering Processes.",
                    "Towards Automated Test Scenario Generation for Assuring COLREGs Compliance of Autonomous Surface Vehicles.",
                    "A Convergent O(n) Temporal-difference Algorithm for Off-policy Learning with Linear Function Approximation.",
                    "Undirected Connectivity in O(log ^1.5 n) Space",
                    "Matching Nuts and Bolts in O(n log n) Time (Extended Abstract).",
                    "On Determinism versus Non-Determinism and Related Problems (Preliminary Version)",
                    "Storing a Sparse Table with O(1) Worst Case Access Time",
                    "Approximating  Minimum Cuts in (",
                    "The Exponential-Time Complexity of Counting (Quantum) Graph Homomorphisms.",

]
doi_short_paper_list = ["FINDINGS-ACL","ICDMW5","ACL-SRW" ]

def has_worked_in_hungary(author_name):
    global authors_data
    author_name_=remove_accents(author_name)
    author_info = authors_data.get(author_name_)
    if author_info:
        if "location" in author_info:
            if len(author_info["location"])>0:
                return True
    return False

def classify_author(author_name, pid, year):
    global authors_data, pid_to_name
    if pid!="" and "/"+pid in pid_to_name:
        author_name_=pid_to_name["/"+pid]  
        #author_name_ = remove_accents(author_name)
        author_info = authors_data.get(author_name_)
        if author_info:
            for location in author_info["location"]:
                if "Hungary" in location and is_year_range(location, year):
                    return {
                        "location": "Hungary",
                        "institution": author_info.get("institution", "Unknown"),
                        "department": author_info.get("department", "Unknown"),
                        "category": author_info.get("category", "Unknown")
                    }
    return {
        "location": "Unknown",
        "institution": "Unknown",
        "department": "Unknown",
        "category": "Unknown"
    }

def classify_paper_by_author(author_list, year):
    hungarian = 0
    not_hungarian = 0
    ret = []
    theory = 0
    applied = 0
    for author, pid in author_list:
        author_cls = classify_author(author, pid, year)
        if author_cls["location"] == "Hungary":
            hungarian += 1
            for field in ["institution", "department"]:
                if author_cls[field] != "Unknown":
                    if author_cls[field] not in ret:
                        ret.append(author_cls[field])
        else:
            not_hungarian += 1
        if author_cls["category"] == "theory":
            theory += 1
        elif author_cls["category"] == "applied":
            applied += 1

    if hungarian == 0:
        return ret
    if hungarian <= not_hungarian:
        ret.append("international")
    elif not_hungarian == 0:
        ret.append("all_hungarian")
    else:
        ret.append("mostly_hungarian")
    if theory > applied:
        ret.append("theory")
    else:
        ret.append("applied")
    return ret

def is_short_paper(info, venue):
    limit = 6
    if venue in ["SODA", "STOC", "FOCS"]:
        limit = 3
    if venue in ["MoDELS"]:
        limit = 7
    if venue in ["WWW"]:
        limit = 8
    if "Workshop" in venue:
        return True
    title = info.get("title", "N/A")
    if isinstance(title, dict):
        title = title.get("text", "N/A")
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
        # they accept posters only
        if venue in ["ICML", "NeurIPS", "ICLR"]:# , "ACL", "EMNLP", "COLING", "IJCAI"
            return False 
        #print("no page is given!")
        return True
    for doi_ in doi_short_paper_list:
        if doi_ in info.get("doi", ""):
            return True
    return False

all_authors=[]

def process_paper(paper,venues,search_log,foreign_papers,short_papers,rank_name):
    global all_authors, no_hungarian_affil, pid_to_name
    if "inproceedings" not in paper:
        return None, None, search_log + "\n Skip as not inproceedings"
    info = paper["inproceedings"]
    #info=hit.get("info")
    #if hit.get("@id", "")=="7172350":
    #    print("itt")
    #type = info.get("type")
    #if type!="Conference and Workshop Papers":
    #    return None, None, search_log
    title = info.get("title", "N/A")
    venue = info.get("booktitle", "")
    if venue.upper() not in venues:
        return None, None, search_log
    year = int(info.get("year", 0))
    if not is_year_range(venues[venue.upper()]["YearsInterval"], year, 0): 
        return None, None, search_log + "Skip as {} is not in the right year {}".format(venue, year)

    record = {}
    key = info.get("@key", "")
    record["key"] = key
    record["title"] = title
    record["venue"] = venue
    record["year"] = str(year)
    record["pages"] = info.get("pages", "")
    record["doi"] = info.get("doi", "")
    record["ee"] = info.get("ee", "")
    record["url"] = info.get("url", "")


    # Authors
    author_list_raw = info.get("author", [])
    if isinstance(author_list_raw, list):
        author_list = [] #a.get("text", "") for a in author_list_raw]
        ######
        for a in author_list_raw:
            author_name=a.get("#text", "")
            author_did=a.get("@pid", "")
            if (author_name,author_did) not in all_authors:
                all_authors.append((author_name,author_did))
            author_list.append((author_name,author_did))
    else:
        author_list = [(author_list_raw.get("#text", ""), author_list_raw.get("@pid", ""))]

    
    record["authors"] = author_list
    authors_str = ", ".join([a[0] for a in author_list])
    ptype = classify_paper_by_author(author_list, year)
    record["classfiied"] = ptype

    paper_str = "{} {} {} - {} ".format(venue, year, authors_str, title)

    if info.get("title", "") in no_hungarian_affil:
        foreign_papers[key] = record
        return None, None, search_log + "\n Skip as not hungarian affiliation {}".format(info.get("title", ""))
    
    if len(ptype)==0:
        foreign_papers[key] = record
        return None, None, search_log + "\n Warning! no hungarian authors {}".format(paper_str)

    if rank_name!='B' and rank_name!='C' and is_short_paper(info, venue):
        short_papers[key] = record
        return None, None, search_log + "\n Skip as too short {}".format(paper_str)

    return key, record, search_log + "\n Add {}".format(paper_str)


authors_data=download_author_google_sheet()

# check is author names are all unique
author_names = [remove_accents(name) for name in authors_data.keys()]
if len(author_names) != len(set(author_names)):
    print("Warning: Duplicate author names found!")

pid_to_name = {}
for name, data in authors_data.items():
    pid = data.get("dblp_url", "").strip()
    if pid != "":
        if pid in pid_to_name:
            print("Warning: Duplicate DBLP PID {} found for authors {} and {}".format(pid, pid_to_name[pid], name))
        else:
            pid_to_name[pid] = name



def query_DBLP(authors_data,force): 
    os.makedirs("dblp", exist_ok=True)

    full_log = ""
    counter = 0

    for author, author_cls in authors_data.items():
        if not author_cls.get("location"):
            full_log += "{} is not working in Hungary\n".format(author)
            continue

        # we save the reuslts as dblp/author_name.json
        author_safe = remove_accents(author).replace(" ", "_")
        output_path = os.path.join("dblp", "{}.json".format(author_safe))

        if not force and os.path.exists(output_path):
            #print(f"Skip {author} (already exists)")
            continue

        author_query = remove_accents(author)
        if "dblp_url" in author_cls and author_cls.get("dblp_url", "").strip() != "":
            pid = author_cls.get("dblp_url", "").strip()
            url = "https://dblp.org/pid{}.xml".format(pid)
        else:
            print("No pid for {}, using name search".format(author))
            url = "https://dblp.org/search/publ/api?q=author:{}&h=1000&format=xml".format(quote(author_query))
        
        try:
            print("Fetching: {}".format(author))
            time.sleep(0.5)
            response = requests.get(url)
            counter += 1

            if counter % 50 == 0:
                print("Pause after {} queries".format(counter))
                time.sleep(30)
            if counter % 1000 == 0:
                print("Too many queries – exiting")
                break

            if response.status_code != 200:
                raise Exception("HTTP error {}".format(response.status_code))

            data = xmltodict.parse(response.content)
            #data = response.json()
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print("Error with {}: {}".format(author,e))
            time.sleep(20)

    # Log mentése
    with open("dblp_fetch_log.txt", "w", encoding="utf-8") as f:
        f.write(full_log)

    print("DBLP JSON lekérések kész, elmentve: dblp/")


##################
#step 1: perform DBLP queries
query_DBLP(authors_data,force=force)

dbld_author={}
#step 2: process papers
for rank_name in ["Astar", "A","B","C"]:
    print("Search for Core {} papers".format(rank_name))

    # Konferencia lista betöltése
    with open('core_{}_conferences_classified.json'.format(rank_name), 'r', encoding='utf-8') as f:
        venues = {k.upper(): v for k, v in json.load(f).items()}
        #json.load(f)
    for tollerance in [0,100]:
        papers = {}
        foreign_papers = {}
        short_papers = {}
        search_log = ""

        for author, author_cls in authors_data.items():
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
                    record = data.get("dblpperson", {})
                    papers_found = record.get("r", {})
                    person = record.get("person", author)
                except Exception as e:
                    print("Error loading {}: {}".format(path,e))
                    continue
            dbld_author[author]=person
            affil = author_cls.get("affiliations", [])
            search_log += "\n{} {} {}".format(author,len(papers),' '.join(affil) if isinstance(affil, list) else affil)
            #if "Laszlo Kovacs"==author:
            #    print("itt", len(hits))
            if isinstance(papers_found, dict):
                key, record, search_log = process_paper(papers_found, venues, search_log, foreign_papers, short_papers, rank_name)
                if key and key not in papers:
                    papers[key] = record
            else:
                for paper in papers_found:
                    key, record, search_log = process_paper(paper, venues, search_log, foreign_papers, short_papers, rank_name)
                    if key and key not in papers:
                        papers[key] = record
            # and foreign papers:

        # Mentés
        with open("parsed_core_{}_papers_{}.json".format(rank_name, tollerance), "w", encoding="utf-8") as f:
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
        global pid_to_name
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
            for author, pid in authors:
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
with open('dblp_authors.json'.format(rank_name), 'w') as f:
        json.dump(dbld_author, f, indent=2)

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

check_pid_collisions(all_authors)

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