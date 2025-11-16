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
import tudometer
import run_every_day
import mtmt_utils
import dblp_utils
import mta_att_utils
import create_author_order
import classify_author

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

field_map = {
    "Author": "dblp_author_name",
    "DBLP URL": "dblp_url",
    "MTMT id": "mtmt_id",
    "MTA ATT id": "mta_att_id",
    'MTA kép' : 'mta_image',
    "MTMT name": "mtmt_name",
    "Category": "category",
    "MTMT Status": "status",
    "Works": "works",
    "Affiliations": "affiliations",
    "Core A*": "paper_countA*",
    "Core A": "paper_countA",
    "Hungarian Core A*": "hungarian_paper_countA*",
    "Hungarian Core A": "hungarian_paper_countA",
    "Core B": "paper_countB",
    "Core C": "paper_countC",
    "No Core": "paper_countno_rank",
    "Hungarian Core A* equivalent": 'Hungarian Core A* equivalent',
    "Core A* equivalent": 'Core A* equivalent',
    "First Author Core A* equivalent": 'First Author Core A* equivalent',
    "Core A* Papers": "hungarian_paper_countA*",
    "Core A Papers": "hungarian_paper_countA",
    "MTMT Journal Publications": "mtmt_journal_publications",
    "MTMT Conference Publications": "mtmt_conference_publications",
    "MTMT Total Citations": "mtmt_total_citations",
    "MTMT Journal D1 Equivalents": "mtmt_journal D1 eqvivalents",
    "MTMT Journal D1": "mtmt_rank_D1",
    "MTMT Journal Q1": "mtmt_rank_Q1",
    "MTMT Journal Q2": "mtmt_rank_Q2",
    "MTMT Journal Q3": "mtmt_rank_Q3",
    "MTMT Journal Q4": "mtmt_rank_Q4",
    "MTMT Affiliations": "mtmt_affiliations",
    "MTA topic": "mta_topic",
    "Kutatási téma": "mta_kutatasi_tema",
    "MTA Bizottság": "mta_bizottság",
    "Elérhetőségek": "mta_elerhetosegek",
    "Tudományos fokozat": "mta_tud_fokozat",
    "Aktuális fokozat": "mta_tud_fokozat",
    "MTA tagság": "mta_tagsag",
    "Aktuális fokozat szakterülete": "mta_topic",
    "Szervezeti tagságok": "mta_szervezeti_tagsagok",
    "Díjak": "mta_dijak",
    "PhD éve": "phd_eve",
    "Foglalkozás": "mta_foglalkozas",
    "Született": "mta_szuletett",
    "Elhunyt": "mta_elhunyt",
    "DBLP alias": "dblp_aliases",
    "Első cikk éve": "first_paper_year",
    "Legutolsó cikk éve": "last_paper_year",
}

def load_table(reader):
    global field_map
    authors_data = {}
    for row in reader:
        name = fix_encoding(row.get("Author", "")).strip()
        if not name:
            continue
        entry = {}
        for src_field, dst_field in field_map.items():
            if src_field in ["DBLP alias", "Affiliations"]:
                if src_field in row and row[src_field].strip():
                    val = [
                        a.strip() for a in fix_encoding(row[src_field]).split(";") if a.strip()
                    ]
            else:
                val = fix_encoding(str(row.get(src_field, "")).strip())
                if src_field=="DBLP URL":
                    val = val.replace("https://dblp.org/pid","")
                if src_field=="MTMT id":
                    val = val.replace("https://m2.mtmt.hu/api/author/", "")
                if src_field=="MTA ATT id":
                    val = val.replace("https://mta.hu/koztestuleti_tagok?PersonId=",'')
                if src_field=="MTA kép":
                    val = val.replace("/static/frontend/imgs/unknown.jpg",'').replace("https://aat.mta.hu/aat/FileData/Get/",'')
            if val:
                entry[dst_field] = val
        authors_data[name] = entry
    
    #classify_author.create_pid_to_name_map(authors_data)
    print(f"Loaded {len(authors_data)} researcher records.")
    return authors_data

def generate_author_google_sheet(authors_data, print_only=False, no_processing=False):
    """
    authors_data: dict, amit a load_table készített
    field_map: eredeti mapping (CSV → authors_data kulcsok)
    print_only: ha True, csak kiírja a sorokat CSV-formátumban stdout-ra
    no_processing: ha True, nem alakítja vissza az URL-eket / listákat

    Visszatérési érték: list of dict (ha print_only=False)
    """
    global field_map
    # fordított mapping: dst_field → src_field
    reverse_map = {dst: src for src, dst in field_map.items()}

    output_rows = []
    classify_author.create_pid_to_name_map(authors_data)
    for name, data in authors_data.items():
        if not no_processing:
            #print("Note: no_processing=False, performing value conversions.")
            if 'dblp_url' in data:
                dblp_record=dblp_utils.get_DBLP_record(data['dblp_url'], name, force=False)
                tudometer.count_CORE_papers_by_author(name, data, dblp_record, print_log=False)
            else:
                print(f"Skipping row {name} as htere is no dblp url in the he google sheet")

        row = {}
        row["_author_name"] = name  # Internal key to map back to authors_data
        missing=[]
        for dst_field, src_field in reverse_map.items():
            if dst_field not in data:
                missing.append(dst_field)
                continue
            val = data[dst_field]
            if src_field == "DBLP URL":
                val = f"https://dblp.org/pid{val}"
            elif src_field == "MTMT id":
                val = f"https://m2.mtmt.hu/api/author/{val}"
            elif src_field == "MTA ATT id":
                if val and val!='-':
                    val = f"https://mta.hu/koztestuleti_tagok?PersonId={val}"
            elif src_field == "MTA kép":
                val=val.replace("https://aat.mta.hu/aat/FileData/Get/",'').replace("/static/frontend/imgs/unknown.jpg",'')
                fix_image={"27514": "42588"}
                if val in fix_image:
                    val=str(fix_image[val])
                if val:
                    val = f"https://aat.mta.hu/aat/FileData/Get/{val}"
                else:
                    val = ""
            # ---- listák visszaalakítása
            if isinstance(val, list):
                val = "; ".join(val)
            row[src_field] = str(val)
            if str(val)!=data[dst_field]:
                data[dst_field+'_'] = val  # frissítés visszafelé is
        
        output_rows.append(row)
        #if len(missing):
        #    print(f"There are missing fileds {missing} in {data}")

    # Use create_author_order to add author order annotation and sort by Core metrics
    # Also adds category-based and age-group-based rankings
    output_rows = create_author_order.prepare_author_order_with_extensions(
        output_rows,
        include_time_since_phd=True,
        include_category_ranks=True,
        include_age_group_ranks=True
    )

    # Copy back "Author Order", category ranks, age group ranks, and other computed fields to authors_data
    for row in output_rows:
        author_name = row.get("_author_name")
        if author_name and author_name in authors_data:
            # Copy all ranking and computed columns back to the original dict
            # This includes: Author Order columns, Category ranks, Age Group ranks, Years Since PhD, Age Group classification
            for key, val in row.items():
                if any(keyword in key for keyword in ["Author Order", "Rank", "Years Since PhD", "Career Length"]):
                    # Convert back to authors_data key names if needed
                    if key in field_map:
                        # This is a Google Sheet column name, convert to authors_data key
                        dst_key = field_map[key]
                        authors_data[author_name][dst_key] = val
                    else:
                        # This is already a computed field, keep as is
                        authors_data[author_name][key] = val

    # Save full_authors_data.json AFTER copying back ranking fields
    with open("full_authors_data.json", "w", encoding="utf-8") as f:
        json.dump(authors_data, f, indent=2, ensure_ascii=False)

    df = pd.DataFrame(output_rows)
    # Remove internal tracking column before CSV export
    if "_author_name" in df.columns:
        df = df.drop(columns=["_author_name"])
    
    if print_only:
        for _, row in df.iterrows(): 
            row_str = ""
            for key, value in row.items():
                row_str += f"{value}\t"
            print(row_str)
        print(output_rows)
    else:
        df.to_csv("authors_data.csv", index=False, encoding="utf-8-sig")

        print(" Kész: authors_data.csv")

    print(f"Generated {len(output_rows)} Google Sheet rows.")
    return output_rows


def download_raw_author_google_sheet():
    """Downloads the raw Google Sheet and returns it as a list of dicts (rows)."""
    try:
        import requests
        response = requests.get(url)
        if response.status_code == 200:
            # Force UTF-8 decoding; Google's CSV sometimes lacks explicit charset header
            raw_bytes = response.content
            text = raw_bytes.decode('utf-8', errors='replace')
            content = io.StringIO(text)
            reader = csv.DictReader(content)
            rows = list(reader)
            # Repair mojibake in column names (keys) caused by prior latin1 decoding
            repaired_rows = []
            for r in rows:
                new_r = {}
                for k, v in r.items():
                    repaired_key = fix_encoding(k)
                    new_r[repaired_key] = v
                repaired_rows.append(new_r)
            # Optional: warn if we had to repair something
            if any('Ã' in k for k in rows[0].keys()):
                print("[info] Repaired mojibake in header names.")
            return repaired_rows  # list of dicts
        else:
            print("Failed to load the google sheet with hungarian researchers ({}): {}".format(response.status_code, response.text))
            return []
    except Exception as e:
        #print("Try loading the local csv with hungarian researchers:(connection error {})".format(e))
        with open("authors_data.csv", "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            repaired_rows = []
            for r in rows:
                new_r = {}
                for k, v in r.items():
                    new_r[fix_encoding(k)] = v
                repaired_rows.append(new_r)
            print("Hungarian researchers are loaded from authors_data.csv")
            return repaired_rows  # Convert to list to avoid iterator exhaustion

def download_author_google_sheet():
    reader = download_raw_author_google_sheet()
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

def extend_table_with_tudometer():
    authors_data = download_author_google_sheet()
    i=0
    for name, data in authors_data.items():
        i+=1
        if 'mtmt_id' in data and data['mtmt_id']!='':
            if "mta_att_id" not in data:
                add_row_mtmt_id(data, authors_data, name, comment=f"{i}/{len(authors_data)} {name}")
    
    # Generate the CSV and JSON after all authors are processed
    generate_author_google_sheet(authors_data, print_only=False, no_processing=False)
                
def add_row_mtmt_id(data, authors_data, name, comment=''):
    data_new, dblp_person=tudometer.create_record(data['mtmt_id'])
    if data_new:
        print(f"Processing {comment}. {data_new['dblp_author_name']} mtmt_id={data['mtmt_id']}")
        for key, value in data_new.items():
            if key in data and value!=data[key]:
                print(f" {data_new['dblp_author_name']} {key} {data[key]}!={value}")
                if not key in ['dblp_author_name','affiliations','status','works'] or data[key]=='':
                    print("⚠️ ⚠️  We will overwrite it!")
                    data[key]=data_new[key]
            else:
                data[key]=data_new[key]
        if "mta_att_id" not in data_new or not data_new["mta_att_id"]:
            data["mta_att_id"]='-'
        if name==None:
            name=data_new['dblp_author_name']
        authors_data[name] = data
    return authors_data

def download_records(force=False):
    authors_data = download_author_google_sheet()
    i=0
    for name, data in authors_data.items():
        i+=1
        if 'mtmt_id' in data and data['mtmt_id']!='':
            data,data_pub=mtmt_utils.get_mtmt_record(data['mtmt_id'],force, name) 

def verify_table():
    authors_data = download_author_google_sheet()
    i=0
    for name, data in authors_data.items():
        i+=1
        if 'mtmt_id' in data and data['mtmt_id']!='':
            mtmt_record,pub_rec=mtmt_utils.get_mtmt_record(data['mtmt_id'],name) 
            if 'dblp_url' in data and data['dblp_url']!='':
                dblp_record=dblp_utils.get_DBLP_record(data['dblp_url'], name, force=False)
                if dblp_record and mtmt_record: 
                    if not dblp_utils.is_same_dblp_and_mtmt_records(dblp_record, mtmt_record,pub_rec):
                        print(f"❌ DBLP and MTMT records do NOT match for {name} (MTMT ID: {data['mtmt_id']})")
                    #else:
                    #    print(f"✅ DBLP and MTMT records match for {name} (MTMT ID: {data['mtmt_id']})")
                    #if data.get("mta_att_id") and data["mta_att_id"]!='-':
                    #    att_record=mta_att_utils.get_mta_att_row(data['mta_att_id'], name)

if __name__ == "__main__":
    verify_table()
    #download_records(False)
    #extend_table_with_tudometer()
    #verify_table_conversions()