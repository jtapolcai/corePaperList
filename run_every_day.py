# -*- coding: utf-8 -*-
# compatible with python 3.5
import requests
import csv
import re
import xmltodict
import unicodedata
import json
from collections import defaultdict
import io
from urllib.parse import quote
import time
import os
from unidecode import unidecode
import pandas as pd
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

short_paper_rank ={
    'A*': 'B',
    'A': 'C',
    'B': 'C',
    'C': 'C'
}

def load_list_from_file(filename):
    """Load a list from a file in the inputs/ directory"""
    path = os.path.join("inputs", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    else:
        print(f"File {path} not found. Please create it with the appropriate content.")
    return []

# papers that must be considered as main track papers
regular_paper_list = load_list_from_file("regular_paper_list.txt")

# papers that must be considered as short track papers
short_paper_list = load_list_from_file("short_paper_list.txt")

# papers that must be excluded from having Hungarian affiliation
no_hungarian_affil = load_list_from_file("no_hungarian_affil_list.txt")

# doi of short papers
doi_short_paper_list = load_list_from_file("doi_short_paper_list.txt")

no_page_is_given =[]

pid_to_name = {}

core_table = pd.read_csv("inputs/core_table.csv")
core_table = core_table.set_index("Acronym", drop=False)

def core_rank(venue, pub_year):
    global core_table, acronym_index
    last_rank = "no_rank"
    venue=remove_numbers_and_parentheses(venue).upper()
    # 2) nézzük, van-e ilyen acronym az indexben
    if venue not in core_table.index:
        return "no_rank"

    # 3) vegyük ki a sort
    acronym_row = core_table.loc[venue]
    core_ranks=acronym_row["YearsListed"].split(", ")
    first_year= None
    for cr in core_ranks:
        parts = cr.split("_")
        if len(parts)!=2:
            print("core_rank: invalid core rank entry: {}".format(cr))
            continue
        year = int(parts[0].replace("CORE", "").replace("ERA", ""))
        rank = parts[1]
        if first_year is None:
            first_year = year
            if pub_year <= first_year:
                # we assume it had the same rank before
                return rank
        if pub_year < year:
            if year==2013 and rank=="A*":
                # the previous rank was ERA, which had not A* rank
                return rank
            return last_rank
        last_rank=rank
    return last_rank

  

def remove_numbers_and_parentheses(text: str) -> str:
    original = text
    # (1), (23) stb. eltávolítása a zárójellel együtt
    text = re.sub(r'\(\d+\)', '', text)
    # maradék számok eltávolítása
    text = re.sub(r'\d+', '', text)
    # felesleges dupla szóközök eltávolítása
    text = re.sub(r'\s{2,}', ' ', text).strip()
    #if text != original:
    #    print(f"Módosítva: Eredeti: '{original}'  Új:       '{text}'")
    return text

def get_int(text: str):
    if any(c.isalpha() for c in text):
        if 'vol' in text:
            text = text.split('vol')[0]
            if any(c.isalpha() for c in text):
                print("Non-numeric page numbers detected :{}".format(text))    
                return 0
            else:
                return int(text)
        print("Non-numeric page numbers detected :{}".format(text))
        return 0
    else:
        return int(text)
    
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

def classify_paper_by_author(author_list, year, ignore_affiliations=False):
    hungarian = 0
    not_hungarian = 0
    ret = []
    theory = 0
    applied = 0
    for author, pid in author_list:
        if not ignore_affiliations:
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
    if not ignore_affiliations:
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

def is_short_paper(info, venue, rank_name):
    global no_page_is_given
    limit = 6
    if rank_name!='B' and rank_name!='C':
        limit = 4
    if venue in ["SODA", "STOC", "FOCS"]:
        limit = 3
    if venue in ["MoDELS"]:
        limit = 7
    if venue in ["WWW"]:
        limit = 8
    if "Workshop" in venue:
        print("Workshop detected, treat as short paper: {}".format(info.get("title", "N/A")))
        return True
    title = info.get("title", "N/A")
    if isinstance(title, dict):
        title = title.get("text", "N/A")
    for title in regular_paper_list:
        if title.startswith(title):
            return False
    for title in short_paper_list:
        if title.startswith(title):
            return True
    pages_str = info.get("pages", "")
    if pages_str != "" and (":" in pages_str or "-" in pages_str):
        if ":" not in pages_str:
            pages = re.split(r"[-:]", pages_str)
            if len(pages) > 1 and pages[1] != "":
                pagenum = get_int(pages[1]) - get_int(pages[0])
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
        if venue in ["ICML", "NeurIPS", "ICLR","INTERSPEECH","BMVC"]:# , "ACL", "EMNLP", "COLING", "IJCAI"
            return False
        if rank_name=='B' or rank_name=='C':
            return False
        print("no page is given for  ({}):{} {} {} {}, treat as short paper".format(rank_name, venue, info.get("year", "N/A"),author_string(info.get("author", [])),info.get("title", "N/A")))
        if info.get("title", "N/A") not in no_page_is_given:
            no_page_is_given.append(info.get("title", "N/A"))
        return True
    for doi_ in doi_short_paper_list:
        if doi_ in info.get("doi", ""):
            return True
    return False

all_authors=[]

def author_string(author_field):
    if isinstance(author_field, list):
        author_names = []
        for a in author_field:
            if isinstance(a, dict):
                author_name = a.get("#text", "")
            else:
                author_name = str(a)
            author_names.append(author_name)
        return ", ".join(author_names)
    elif isinstance(author_field, dict):
        return author_field.get("#text", "")
    else:
        return str(author_field)

def classify_paper(paper, search_log=""):
    global all_authors, no_hungarian_affil, pid_to_name, short_paper_rank

    if "inproceedings" not in paper:
        return None, None, None, False, False, search_log + "\n Skip as not inproceedings"
    info = paper["inproceedings"]

    foreign_paper=False
    short_paper=False

    title = info.get("title", "N/A")
    venue = info.get("booktitle", "")
    year = int(info.get("year", 0))
    rank=core_rank(venue, year)
    #venue=remove_numbers_and_parentheses(venue)
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
        author_list = [] 
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
        foreign_paper = True
        search_log +="\n No hungarian affiliation {}".format(info.get("title", ""))
    
    if len(ptype)==0:
        foreign_paper = True
        search_log +="\n No hungarian authors {}".format(paper_str)

    if rank=="no_rank":
        return key, record, rank, False, False, search_log + "\n no rank for venue {}".format(venue)
    
    if is_short_paper(info, venue, rank):
        short_paper = True
        search_log +="\n Short paper {}".format(paper_str)
        rank=short_paper_rank[rank]
    else:
         search_log += "\n Full paper {}".format(paper_str)

    return key, record, rank, foreign_paper, short_paper, search_log

def process_paper(paper, papers, search_log="", foreign_papers=None, short_papers=None):
    key, record, rank, foreign_paper, short_paper, search_log=classify_paper(paper, search_log)
    if not rank: # no rank
        return search_log, papers, foreign_papers, short_papers
    rank_name=rank.replace("*","star")
    if key and rank_name in papers and key not in papers[rank_name]:
        papers[rank_name][key] = record
    if foreign_paper and foreign_papers is not None and rank_name in foreign_papers:
        if key and key not in foreign_papers[rank_name]:
            foreign_papers[rank_name][key] = record
    if short_paper and short_papers is not None and rank_name in short_papers:
        if key and key not in short_papers[rank_name]:
            short_papers[rank_name][key] = record
    return search_log, papers, foreign_papers, short_papers

def get_dblp_record(author_name):
    author_safe = remove_accents(author_name).replace(" ", "_")
    path = os.path.join("dblp", author_safe+".json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                record = data.get("dblpperson", {})
                return record
            except Exception as e:
                print("Error loading {}: {}".format(path,e))
    else:
        print("{} not found ".format(path))
    return None    

def query_DBLP(authors_data,force): 
    os.makedirs("dblp", exist_ok=True)

    full_log = ""
    counter = 0

    for author, author_cls in authors_data.items():
        #if not author_cls.get("location"):
        #    full_log += "{} is not working in Hungary\n".format(author)
        #    continue

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

if __name__ == "__main__":
    authors_data=download_author_google_sheet()

    # check is author names are all unique
    author_names = [remove_accents(name) for name in authors_data.keys()]
    if len(author_names) != len(set(author_names)):
        print("Warning: Duplicate author names found!")

    for name, data in authors_data.items():
        pid = data.get("dblp_url", "").strip()
        if pid != "":
            if pid in pid_to_name:
                print("Warning: Duplicate DBLP PID {} found for authors {} and {}".format(pid, pid_to_name[pid], name))
            else:
                pid_to_name[pid] = name

    #step 1: perform DBLP queries
    query_DBLP(authors_data,force=force)

    dbld_author={}
    
    #step 2: process papers
    search_log = ""
    papers = {}
    for rank_name in ["Astar", "A","B","C","no_rank"]:
        papers[rank_name] = {}
    foreign_papers = {}
    short_papers = {}
    for rank_name in ["Astar", "A"]:
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
        #if "Laszlo Kovacs"==author:
        #    print("itt", len(hits))
        if isinstance(papers_found, dict):
            search_log, papers, foreign_papers, short_papers = process_paper(papers_found, papers, search_log, foreign_papers, short_papers)
        else:
            for paper in papers_found:
                search_log, papers, foreign_papers, short_papers = process_paper(paper, papers, search_log, foreign_papers, short_papers)

    # --- Save the log file ---
    with open("log_dblp.txt", "w", encoding="utf-8") as f:
        f.write(search_log)
    
    for rank_name in ["Astar", "A"]:   
        with open('already_abroad_papers_core{}.json'.format(rank_name), 'w') as f:
            json.dump(foreign_papers[rank_name], f, indent=2)
        with open('short_papers_core{}.json'.format(rank_name), 'w') as f:
            json.dump(short_papers[rank_name], f, indent=2)

    for rank_name in ["Astar", "A","B","C","no_rank"]:
        # Mentés
        with open("hungarian_papers_core{}.json".format(rank_name), "w", encoding="utf-8") as f:
            json.dump(papers[rank_name], f, indent=2, ensure_ascii=False)
        print("Elmentve: hungarian_papers_core{} with {} papers.json".format(rank_name, len(papers[rank_name])))


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

        for key, paper in papers[rank_name].items():
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

    with open('all_authors.json'.format(rank_name), 'w') as f:
            json.dump(all_authors, f, indent=2)

    with open('papers_with_no_page.json'.format(rank_name), 'w') as f:
            json.dump(no_page_is_given, f, indent=2)

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