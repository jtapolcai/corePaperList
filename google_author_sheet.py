# -*- coding: utf-8 -*-
# compatible with python 3.5
import csv
import re
#import xml.etree.ElementTree as ET
import json
import io
#from urllib.parse import quote
from unidecode import unidecode
#from collections import Counter
import pandas as pd

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


# remove hungarian accents
def remove_accents(text):
    return unidecode(text)

def fix_encoding(text):
    if isinstance(text, str):
        try:
            # szimulálja a hibás dekódolást -> majd újradekódolja jól
            return text.encode('latin1').decode('utf-8')
        except Exception:
            return text
    return text

def load_table(reader):
    authors_data = {}
    for row in reader:
        name = fix_encoding(row["Author"]).strip()
        alias = fix_encoding(row["DBLP alias"]).strip()
        mtmt_id = row["MTMT id"].strip()
        mtmt_name = fix_encoding(row["MTMT name"]).strip()
        dblp_url = row["DBLP URL"].strip()
        affiliations = [a.strip() for a in fix_encoding(row["Affiliations"]).split(";") if a.strip()]
        category = row.get("Category","").strip()
        status = row.get("MTMT Status","").strip()
        works = row.get("Works","").strip()
        authors_data[name] = {
            "dblp_url": dblp_url,
            "basic_info": {
                "author": name,
                "aliases": {"alias": alias} if alias else {}
            },
            "affiliations": affiliations,
            "mtmt_id": mtmt_id,
            "mtmt_name": mtmt_name,
            "category": category,
            "status": status,
            "works": works
        }
    print("Loaded {} hungarian researcher names.".format(len(authors_data)))
    return authors_data

def generate_author_google_sheet(authors_data):
    for rank_name in ["Astar","A"]:
        count_papers_by_author(authors_data,rank_name)
    collect_dblp_data(authors_data)

    #  JSON mentés
    with open("authors_data_merged.json", "w", encoding="utf-8") as f:
        json.dump(authors_data, f, indent=2, ensure_ascii=False)

    csv_rows = []
    for author, data in authors_data.items():
        paper_count_astar = data["paper_countAstar"] if "paper_countAstar" in data else 0
        papers_astar = data["papersAstar"] if "papersAstar" in data else ""
        paper_count_a = data["paper_countA"] if "paper_countA" in data else 0
        papers_a = data["papersA"] if "papersA" in data else ""
        mtmt_id = data.get("mtmt_id", "")
        mtmt_name = data.get("mtmt_name", "")
        dblp_notes = merge_list_attribute_into_string(data, "note", " + ")
        dblp_urls = merge_list_attribute_into_string(data, "url", " , ")

        csv_rows.append({
            "Author": data["basic_info"]["author"],
            "DBLP URL": data.get("dblp_url", "").replace("https://dblp.org/pid",""),
            "MTMT id":  mtmt_id,
            "Category": data.get("category", ""),
            "MTMT Status": data.get("status", ""),
            "Works": data.get("works",""),
            "Affiliations": "; ".join(data.get("affiliations", [])),
            "Core A*": paper_count_astar,
            "Core A": paper_count_a,
            "Core A* Papers": papers_astar,
            "Core A Papers": papers_a,
            "DBLP alias": data["basic_info"].get("aliases", {}).get("alias", ""),
            "DBLP note": dblp_notes,
            "DBLP urls": dblp_urls,
            "MTMT name": mtmt_name,
        })

    df = pd.DataFrame(csv_rows)
    df.to_csv("authors_data.csv", index=False, encoding="utf-8-sig")

    print(" Kész: authors_data.csv")

def download_author_google_sheet():
    try:
        import requests
        response = requests.get(url)
        if response.status_code == 200:
            content = io.StringIO(response.text)
            reader = csv.DictReader(content)
            authors_data = load_table(reader)
        else:
            print("Failed to load the google sheet with hungarian researchers ({}): {}".format(response.status_code, response.text))
    except Exception as e:
        print("Try loading the local csv with hungarian researchers: {}".format(e))
        with open("authors_data.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            authors_data = load_table(reader)
            

    # --- Processing affiliations, identify the periods the author was working in Hungary ---
    for name, data in authors_data.items():
        aff_texts = data.get("affiliations", [])
        location_entries = []
        institution = None
        department = None
        for aff_text in aff_texts:
            inst_name, years = parse_affiliation(aff_text)
            for inst_key, keywords in institutions.items():
                found = False
                for kw in keywords:
                    if kw in inst_name.lower():
                        loc_label = "Hungary {}".format(years) if years else "Hungary"
                        if loc_label not in location_entries:
                            location_entries.append(loc_label)
                        if institution is None:
                            institution = inst_key
                            if inst_key == "BME":
                                for dep, keys in departments.items():
                                    for kw in keys:
                                        if kw in inst_key:
                                            department = dep
                                            break
                        found = True
                        break
                if found:
                    break
        data["location"] = location_entries
        if institution:
            data["institution"] = institution
        if department:
            data["department"] = department        
    # now authors_data is extended with location, institution and department
    return authors_data

    """# next we handle the aliases, ie. if the author used multiple names, we add both names to the authors_data
    author_classified_with_aliases = {}
    for name, data in authors_data.items():
        key_main = remove_accents(name)
        author_classified_with_aliases[key_main] = data
        aliases = data.get("basic_info", {}).get("aliases", {})
        for alias in aliases.values():
            key_alias = remove_accents(alias)
            author_classified_with_aliases[key_alias] = data"""

def count_papers_by_author(authors_data,rank_name, first_author_only=False):
    pid_to_name = {data["dblp_url"]: name for name, data in authors_data.items()}
    for author, data in authors_data.items():
        authors_data[author]["papers"+rank_name] = ""
        authors_data[author]["paper_count"+rank_name] = 0

    #filename='already_abroad_papers_core{}.json'.format(rank_name)
    #filename='short_papers_core{}.json'.format(rank_name)
    filename='hungarian_papers_core{}.json'.format(rank_name)
    with open(filename, "r", encoding="utf-8") as f:
        papers = json.load(f)
        print("processing {}".format(filename))
    with open("foreign_authors.json", "r", encoding="utf-8") as f:
        foreign_authors = json.load(f)
    unknown_authors=[]
    for key, paper in papers.items():
        authors = paper.get("authors", "")
        acronym = paper.get("venue", "")
        year = paper.get("year", "")
        venue_year = f"{acronym}{year}"
        for author, pid in authors:
            author_ = pid_to_name.get('/'+pid, author)
            #author=fix_encoding(author_)
            #author=remove_accents(author_)
            if author_ in authors_data:
            #    location = authors_data[author]["location"]
                authors_data[author_]["paper_count"+rank_name] += 1
                authors_data[author_]["papers"+rank_name]+=venue_year+" "
            else:
                if author_ not in unknown_authors and author_ not in foreign_authors:
                    unknown_authors.append(author_)
            if first_author_only:
                break
    with open("new_authors.json", "w", encoding="utf-8") as f:
        json.dump(unknown_authors, f, indent=2, ensure_ascii=False)

def collect_dblp_data(authors_data):
    pid_to_name = {data["dblp_url"]: name for name, data in authors_data.items() 
        if "dblp_url" in data and data["dblp_url"]!=""}

    with open("dblp_results_authors_from_xml.json", "r", encoding="utf-8") as f:
        dblp = json.load(f)

    not_found=0
    for author, data in dblp.items():
        if "dblp_url" in data and data["dblp_url"] is not None:
            dblp_=data["dblp_url"].replace("https://dblp.org/pid","")
            if dblp_ in pid_to_name:
                name_=pid_to_name[dblp_]
                if "person_dict" in data:
                    if "note" in data["person_dict"]:
                        authors_data[name_]["note"]=data["person_dict"]["note"]
                    if "url" in data["person_dict"]:
                        authors_data[name_]["url"]=data["person_dict"]["url"]
            # else:
            #    print(f"{author} not found in dblp")
        # else:
        #    print(data)

def merge_list_attribute_into_string(data, field, sep):
    if field not in data:
        return ""
    value = data[field]
    # Ha nem lista, tedd listába
    if not isinstance(value, list):
        value = [value]
    # Ha egy elem, azt adjuk vissza
    if len(value) == 1:
        return value[0]
    return sep.join(value)



# --- Helper functions ---

def get_year_range(inst_key):
    cleaned = inst_key.replace(" ", "")
    match = re.search(r"(\d{0,4})-(\d{0,4})$", cleaned)
    if match:
        from_year, to_year = match.groups()
        from_year = from_year if from_year else ""
        to_year = to_year if to_year else ""
        return "{}-{}".format(from_year, to_year)
    return ""

def parse_affiliation(aff_text):
    years = get_year_range(aff_text)
    if years:
        inst_name = re.split(r"\s*-\s*\d{0,4}-?\d{0,4}$", aff_text.strip())[0]
    else:
        inst_name = aff_text.strip()
    return inst_name, years

def is_year_range(inst_key, year, tolerate=0):
    cleaned = inst_key.strip().replace("–", "-").replace("—", "-").replace(" ", "")
    match = re.search(r"(\d{0,4})-(\d{0,4})$", cleaned)
    if match:
        from_year, to_year = match.groups()
        if from_year and to_year and ( int(to_year) < year - tolerate or int(from_year) > year + tolerate):
            return False
        if from_year and int(from_year) > year + tolerate:
            #print("The paper was published in {} the author was not in Hungary before {}".format(year, from_year))
            return False
        if to_year and int(to_year) < year - tolerate:
            #print("The paper was published in {} the author already left Hungary at {}".format(year, to_year))
            return False
    return True



