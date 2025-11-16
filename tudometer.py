  # -*- coding: utf-8 -*-
"""
Tudometer - Main module for author record creation and paper counting
Coordinates DBLP, MTMT, and MTA ATT data to build comprehensive author profiles.
"""
import sys
import json
from collections import OrderedDict
from typing import OrderedDict as TOrderedDict
import pandas as pd

# Import utility modules
import dblp_utils
import mtmt_utils
import mta_att_utils
import google_author_sheet 
import run_every_day
import classify_author
import classify_paper


def find_dblp_in_google_sheets(mtmt_id):
    # Load full_authors_data.json which contains all ranking fields
    # try:
    #     with open("full_authors_data.json", "r", encoding="utf-8") as f:
    #         authors_data = json.load(f)
    # except FileNotFoundError:
    #     # Fallback to downloading from Google Sheet (won't have ranking fields)
    #     print("Warning: full_authors_data.json not found, downloading from Google Sheet (ranking fields will be missing)")
    authors_data = google_author_sheet.download_author_google_sheet()
    classify_author.create_pid_to_name_map(authors_data)
    
    for author, data in authors_data.items():
        if 'mtmt_id' in data and data['mtmt_id']!='' and int(data['mtmt_id'])==int(mtmt_id):
            return author, data        
    return None, None


def check_paper(paper_dict, first_author_pid, hungarian_affil, name_prefix, data, print_log=False, first_paper_year=None,last_paper_year=None):
    """The main filtering function of papers. 
       It checks a single paper whether meets the required properties
       and if yes it updates the data accordingly."""
    if "inproceedings" in paper_dict:
        paper = paper_dict["inproceedings"]
    elif "article" in paper_dict:
        paper = paper_dict["article"]
    else:
        return data, first_paper_year, last_paper_year 
    year = paper.get("year", "")
    if first_paper_year is None:
        first_paper_year=int(year)
    elif int(year)<first_paper_year:
        first_paper_year=int(year)  
    if last_paper_year is None:
        last_paper_year=int(year)
    elif int(year)>last_paper_year:
        last_paper_year=int(year)
    authors = paper.get("author", [])
    if first_author_pid!=None:
        if isinstance(authors, list) and len(authors)>1 and authors[0].get("@pid", "")!=first_author_pid[1:]:
            return data, first_paper_year, last_paper_year 
    key, record, rank, foreign_paper, short_paper, search_log=classify_paper.classify_paper(paper_dict)
    if print_log and search_log.strip()!="" and search_log.strip()!="Skip as not inproceedings":
        print(search_log)
    if key:
        if hungarian_affil and foreign_paper:
            return data, first_paper_year, last_paper_year 
        data[name_prefix+"paper_count"+rank] += 1
        acronym = paper.get("booktitle", "")
        venue_year=f"{acronym}{year} "
        data[name_prefix+"papers"+rank]+=venue_year
    return data, first_paper_year, last_paper_year 

def count_papers_by_author(data, dblp_record, first_author_only=False, hungarian_affil=False, name_prefix='', print_log=False):
    """Count papers by author for a given rank.
    """
    first_author_pid = None
    if first_author_only:
        first_author_pid = data.get("dblp_url", "")
    
    if dblp_record is None:
        return data
    
    papers_found = dblp_record.get("r", {})
    first_paper_year=None
    last_paper_year=None
    if isinstance(papers_found, dict):
        data, first_paper_year, last_paper_year =check_paper(papers_found, first_author_pid, hungarian_affil, name_prefix, data, print_log, first_paper_year=first_paper_year,last_paper_year=last_paper_year)
    else:
        for paper in papers_found:
            data, first_paper_year, last_paper_year =check_paper(paper, first_author_pid, hungarian_affil, name_prefix, data, print_log, first_paper_year=first_paper_year,last_paper_year=last_paper_year)
    data["first_paper_year"] = first_paper_year
    data["last_paper_year"] = last_paper_year
    return data


def count_CORE_papers_by_author(author, data, dblp_record=None, print_log=False, force=False):
    """Count papers for all CORE ranks. Loads each rank's venues JSON once and reuses it.
    Also fetches MTMT record if mtmt_id is present in data.
    """
    for rank_name in ["A*","A","B","C","no_rank"]:
        for name_prefix in ['', 'first_author_', 'hungarian_']:
            data[name_prefix+"papers"+rank_name] = ""
            data[name_prefix+"paper_count"+rank_name] = 0
        #if print_log:
        #    print(f"Counting {rank_name} papers for {author}...")
        # Load venues JSON once per rank (not once per call)
        #with open('core_{}_conferences_classified.json'.format(rank_name), 'r', encoding='utf-8') as f:
        #    venues = {k.upper(): v for k, v in json.load(f).items()}
    
    # Fetch MTMT record if mtmt_id is present and get metrics
    if 'mtmt_id' in data and data['mtmt_id']:
        try:
            mtmt_record, pub_rec = mtmt_utils.get_mtmt_record(data['mtmt_id'], force=force, author_name=author)
            if mtmt_record and pub_rec:
                # Get metrics from MTMT and merge into data
                metrics = mtmt_utils.get_metrics(mtmt_record, pub_rec)
                for key, value in metrics.items():
                    if isinstance(value, dict):
                        for subkey, subvalue in value.items():
                            data[f"mtmt_{key}_{subkey}"] = subvalue
                    else:
                        data[f"mtmt_{key}"] = value
                if print_log:
                    print(f"MTMT metrics fetched for {author}: {metrics.get('journal D1 eqvivalents', 0)} D1 eq")
        except Exception as e:
            if print_log:
                print(f"Warning: Could not fetch MTMT record for {author}: {e}")
    
    if dblp_record and 'dblpperson' in dblp_record:
        dblp_record=dblp_record['dblpperson']
    # Pass venues to all 3 calls for this rank
    data=count_papers_by_author(data, dblp_record, print_log=print_log)
    data["Core A* equivalent"] = data["paper_countA*"]+data["paper_countA"]/3+data["paper_countB"]/6+data["paper_countC"]/12
    data=count_papers_by_author(data, dblp_record, first_author_only=True, name_prefix='first_author_', print_log=print_log)
    data["First Author Core A* equivalent"] = data["first_author_paper_countA*"]+data["first_author_paper_countA"]/3+data["first_author_paper_countB"]/6+data["first_author_paper_countC"]/12
    data=count_papers_by_author(data, dblp_record, hungarian_affil=True, name_prefix='hungarian_', print_log=print_log)
    data["Hungarian Core A* equivalent"] = data["hungarian_paper_countA*"]+data["hungarian_paper_countA"]/3+data["hungarian_paper_countB"]/6+data["hungarian_paper_countC"]/12
    return data

def safe_get_value(row, key, default=''):
    """Safely get value from pandas Series, handling NaN and None."""
    if key not in row:
        return default
    val = row[key]
    if pd.isna(val) or val is None:
        return default
    # Ha float, de egész szám, akkor integer-ként kezeljük
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()

def add_mta_att_record(angol_nev, row,  mtmt_id, magyar_nev, data, dblp_record=None, mtmt_record=None, pub_rec=[]):
    """Add MTA ATT record data to the author data.
    
    If dblp_record and mtmt_record are provided, skip the verification step.
    Otherwise, verify that the DBLP and MTMT records correspond to the same author.
    """
    if dblp_record is None or mtmt_record is None:
        print("Missing DBLP or MTMT record, skipping verification.")
    else:
        if not dblp_utils.is_same_dblp_and_mtmt_records(dblp_record, mtmt_record, pub_rec):
            print(f"Warning! {dblp_record.get('@name','')} és {mtmt_record.get('label','')} nem ugyanaz a személy!")
            return False, data
            # Proceed only if both records are present
    if dblp_record and mtmt_record:
        print("Valóban ő az!")                        
        #data_orig = authors_data.get(angol_nev, {})
        """
        image                                             756        1817    2573
        Tudományos osztály                                756        1817    2573
        Aktuális fokozat                                  756        1817    2573
        Publikációs név                                   756        1817    2573
        Hivatalos név                                     756        1817    2573
        Hivatalos név_URL                                 756        1817    2573
        Tudományos bizottság                              756        1817    2573
        Aktuális fokozat szakterülete                     756        1816    2572
        Szervezeti tagságok                               740        1763    2503
        Publikációk                                       716        1709    2425
        Szakterület                                       688        1587    2275
        Elérhetőségek                                     678        1495    2173
        Kutatási téma                                     589        1340    1929
        PhD                                               510        1344    1854
        Foglalkozás                                       457         861    1318
        Született                                         281         890    1171
        Díjak                                             164         327     491
        a műszaki tudomány kandidátusa                      3         324     327
        MTA doktora                                       130         185     315
        Szerkesztői tevékenységek                          80         166     246
        a matematikai tudomány kandidátusa                173           2     175
        levelező tag                                       42          38      80
        rendes tag                                         36          30      66
        Adományozott címek                                 16          47      63
        a műszaki tudomány doktora                          0          52      52
        a matematikai tudomány doktora                     51           1      52
        DLA                                                 0          50      50
        Elhunyt                                             6          16      22
        Székfoglalók                                        8           8      16
        a fizikai tudomány kandidátusa                      0          14      14
        a közlekedéstudomány kandidátusa                    0          10      10
        a kémiai tudomány kandidátusa                       0           9       9
        a közgazdaság-tudomány kandidátusa                  2           3       5
        a közlekedéstudomány doktora                        0           3       3
        a kémiai tudomány doktora                           0           3       3
        a hadtudomány kandidátusa                           1           2       3
        az építőmérnöki tudomány kandidátusa                0           1       1
        fokozat nélküli                                     0           1       1
        külső tag                                           1           0       1
        egyetemi doktor                                     0           1       1
        az építőművészet kandidátusa                        0           1       1
        a fizikai tudomány doktora                          0           1       1
        a tudomány doktora                                  1           0       1
        a nyelvtudomány kandidátusa                         0           1       1
        a művészettörténeti tudomány kandidátusa            0           1       1
        a mezőgazdasági tudomány kandidátusa                0           1       1
        a hadtudomány doktora                               0           1       1
        PhD (Szlovákia)                                     0           1       1
        PhD (Szerbia)                                       0           1       1
        tudományok doktora (Románia)                        0           1       1
        HTML_content                                        0           0       0"""
        class_type = ""
        tud_osztaly = safe_get_value(row, 'Tudományos osztály')
        if tud_osztaly == 'III. Matematikai Tudományok Osztálya':
            class_type = 'theory'
        if tud_osztaly == 'IV. Műszaki Tudományok Osztálya':
            class_type = 'applied'
        if data["category"]!=class_type:
            print(f"{safe_get_value(row, 'Hivatalos név')}  kategóriaja {data['category']} -> mta-ban {class_type} {data['mtmt_name']} ")
            data['category']=class_type
        
        hivatalos_nev_url = safe_get_value(row, 'Hivatalos név_URL')
        data['mta_att_id'] = hivatalos_nev_url.replace("https://mta.hu/koztestuleti_tagok?PersonId=",'')
        data['mta_image'] = safe_get_value(row, 'image')
        data['mta_tud_fokozat'] = safe_get_value(row, 'Aktuális fokozat')
        data['mta_topic'] = safe_get_value(row, 'Aktuális fokozat szakterülete')
        data['mta_bizottság'] = safe_get_value(row, 'Tudományos bizottság')
        data['mta_elerhetosegek'] = safe_get_value(row, 'Elérhetőségek')
        data['mta_szervezeti_tagsagok'] = safe_get_value(row, 'Szervezeti tagságok')
        data['mta_dijak'] = safe_get_value(row, 'Díjak')
        data['mta_kutatasi_tema'] = safe_get_value(row, 'Kutatási téma')
        
        phd_eve = None
        for key in row.index:
            if key and isinstance(key, str) and 'phd' in key.lower():
                val = safe_get_value(row, key)
                if val:
                    phd_eve = val
                    break
        data['phd_eve'] = phd_eve if phd_eve else ''
        
        data['mta_foglalkozas'] = safe_get_value(row, 'Foglalkozás')
        data['mta_szuletett'] = safe_get_value(row, 'Született')
        
        rendes = safe_get_value(row, 'rendes tag')
        levelező = safe_get_value(row, 'levelező tag')
        külső = safe_get_value(row, 'külső tag')
        data['mta_tagsag'] = 'rendes tag' if rendes else 'levelező tag' if levelező else 'külső tag' if külső else ''
        
        data['mta_elhunyt'] = safe_get_value(row, 'Elhunyt')
        
        publikaciok = safe_get_value(row, 'Publikációk')
        if data['mtmt_id']!='' and publikaciok:
            try:
                if int(data['mtmt_id']) != int(mtmt_id):
                    print(f"⚠️ Warning: {safe_get_value(row, 'Hivatalos név')} névhez két különböző MTMT ID tartozik: {data['mtmt_id']} és {mtmt_id}")
                #if int(data['mtmt_id']) != int(mtmt_id) or int(mtmt_id) == int(publikaciok):
                #    print(f"Warning! {safe_get_value(row, 'Hivatalos név')} névvel két MTMT ID van: {mtmt_id} és {data['mtmt_id']} és {publikaciok}")
                    data['mtmt_id'] = str(int(mtmt_id))
            except (ValueError, TypeError):
                pass
        
        data['mtmt_name'] = mtmt_record.get("label", "")
        return True, data
    return False, data

def get_mta_att_row(mtmt_id):
    for output_file in ["vi_osztaly_tagok.csv","iii_osztaly_tagok.csv"]:
        osztaly = pd.read_csv("inputs/"+output_file, encoding='utf-8-sig')
        for idx, row in osztaly.iterrows():
            if 'Publikációk' in row:
                publikaciok = safe_get_value(row, 'Publikációk')
                if publikaciok:
                    try:
                        if int(mtmt_id) == int(publikaciok):
                            return row
                    except (ValueError, TypeError):
                        pass
    return None

def categorize(val):
    theory_kw = ["matematik", "elmélet", "gráf", "logika", "kombinatórik","kombinatorik","tudomány","algoritmus","operációkutatás","geometria","algebra","theory","matematika","formális","statisztika"]
    practical_kw = ["info", "hálózat", "távközl", "szoftver", "gép", "tanulás", "vision", "képfeld","intelligencia","technológia","technika","mérnök","robot","fizika","protokol","adat","internet","network","routing","szintézis","blockchain","rendszer","engineering","fuzz","idősor","fonetika","nyelv","műszaki","modellezés"]
    s = val.lower()
    if any(k in s for k in theory_kw):
        return "theory"
    if any(k in s for k in practical_kw):
        return "applied"
    return ""

def location_of_affiliation(dblp_record,mtmt_record):
    """Extract affiliation info from the dblp_record's note field (person-level affiliations).
    
    This does NOT iterate through all papers; it uses the top-level 'note' metadata
    which is much faster for authors with many publications.
    """
    dblp_affiliations = ""
    if "note" in dblp_record:
        notes = dblp_record["note"]
        # handle both single dict and list of notes
        if isinstance(notes, dict):
            notes = [notes]
        for note in notes:
            if "affiliation" in note:
                affil = note["affiliation"].lower()
                if "@label" in note:
                    years = note["@label"].lower()
                    if dblp_affiliations!="":
                        dblp_affiliations+="; "
                    dblp_affiliations+=f"{affil} ({years})"
                    if "since" not in years:
                        # not current affiliation, keep looking
                        continue
                else:
                    dblp_affiliations=f"{affil}"
                if "budapest" in affil or "hungary" in affil or "magyarország" in affil or "szeged" in affil or "egyetem" in affil or "renyi" in affil:
                    return dblp_affiliations,"hungary"
                else:
                    return dblp_affiliations,"abroad"
    return dblp_affiliations,""

def build_author_record(mtmt_record, pub_rec,dblp_record):
    dblp_person = dblp_record.get("dblpperson", {})
    name= dblp_person.get("@name", "")
    dblp_url = "/"+dblp_person.get("@pid", "")
    mtmt_id = mtmt_record.get("mtid", "")
    topic = mtmt_record.get("auxName", "")
    category = categorize(topic)
    status = mtmt_utils.is_active_in_mtmt(mtmt_record)
    works, affiliations = location_of_affiliation(dblp_person, mtmt_record)
    alias = dblp_person.get("alias", [])
    mtmt_name = mtmt_record.get("label", "")
    print(f"DBLP rekord megtalálva: {name} - {dblp_url}")
    data={
        "dblp_url": dblp_url,
        "dblp_author_name": name,
        "dblp_aliases": alias,
        "affiliations": affiliations,
        "mtmt_id": mtmt_id,
        "mtmt_name": mtmt_name,
        "category": category,
        "status": status,
        "works": works
    }
    row = get_mta_att_row(mtmt_id)
    if row is not None:
        # Pass the already verified dblp_record and mtmt_record to avoid duplicate verification
        ok, data = add_mta_att_record(name, row, mtmt_id, mtmt_name, data, dblp_record=dblp_record, mtmt_record=mtmt_record, pub_rec=pub_rec)
    return data, dblp_person

def create_record(mtmt_id):
    mtmt_record, pub_rec = mtmt_utils.get_mtmt_record(mtmt_id)
    if mtmt_record:
        dblp_record = dblp_utils.find_dblp_by_name(mtmt_record, pub_rec)
        if dblp_record:
            #with open("dblp_record.json", "w", encoding="utf-8") as f:
            #    json.dump(dblp_record, f, indent=2, ensure_ascii=False)
            return build_author_record(mtmt_record, pub_rec,dblp_record)
        else:
            print(f"Nincs DBLP rekord megtalálva a név alapján {mtmt_record.get('label', '')}.")
    else:
        print("Nem sikerült lekérni az MTMT rekordot.")
    return None, None

def pretty_label_map():
    """A belső kulcsokhoz magyar címkék — típusonként rendezve (paper_count → papers → first_author → hungarian)."""
    labels: TOrderedDict[str, str] = OrderedDict([
        # --- Általános adatok ---
        ("dblp_url", "DBLP azonosító"),
        ("dblp_author_name", "DBLP szerzőnév"),
        ("mtmt_name", "MTMT név"),
        ("dblp_aliases", "DBLP alternatív nevek"),
        ("affiliations", "Munkahely(ek), affiliáció"),
        ("mtmt_affiliations", "MTMT affiliációk"),
        ("mtmt_id", "MTMT azonosító"),

        ("status", "MTMT státusz"),
        ("works", "MTMT: művek"),
        ("mta_att_id", "MTA Köztestületi azonosító"),
        ("mta_image", "MTA profilkép"),
        ("mta_tud_fokozat", "Tudományos fokozat"),
        ("mta_topic", "Tudományterület"),
        ("mta_bizottság", "MTA bizottsági tagság"),
        ("mta_elerhetosegek", "Elérhetőségek"),
        ("mta_szervezeti_tagsagok", "MTA szervezeti tagságok"),
        ("mta_dijak", "Díjak, elismerések"),
        ("mta_kutatasi_tema", "Kutatási téma"),
        ("phd_eve", "PhD éve"),
        ("mta_foglalkozas", "Foglalkozás / beosztás"),
        ("mta_szuletett", "Született"),
        ("mta_tagsag", "MTA tagság"),
        ("mta_elhunyt", "Elhunyt"),
        ("mtmt_journal_publications", "MTMT folyóirat közlemények száma"),
        ("mtmt_conference_publications", "MTMT konferencia közlemények száma"),
        ("mtmt_total_citations", "MTMT összes idézet"),
        ("mtmt_rank_D1", "MTMT D1 rangsor"),
        ("mtmt_rank_Q1", "MTMT Q1 rangsor"),
        ("mtmt_rank_Q2", "MTMT Q2 rangsor"),
        ("mtmt_rank_Q3", "MTMT Q3 rangsor"),
        ("mtmt_rank_Q4", "MTMT Q4 rangsor"),
        ("mtmt_journal D1 eqvivalents", "MTMT folyóirat D1 ekvivalensek"),
        ("Core A* equivalent Author Order", "Core A* equivalent szerint az országos sorrendben"),
        ("Hungarian Core A* equivalent Author Order", "Magyar affilicáiós Core A* equivalent szerint az országos sorrendbe"),
        ("First Author Core A* equivalent Author Order", "Első szerzős Core A* equivalent szerint az országos sorrendben"),
        ("Years Since PhD", "PhD megszerzése óta eltelt idő (években)"),
        ("Career Length", "Korcsoport"),
        ("Career Length Core A* Rank", "Korcsoport szerinti Core A* rangsor"),
        ("Career Length Hungarian Core A* Rank", "Korcsoport szerinti magyar affil Core A* rangsor"),
        ("Career Length First Author Core A* Rank", "Korcsoport szerinti első szerzős Core A* rangsor"),
        ("category", "Kategória / terület"),
        ("Category Core A* Rank", "Kategória szerinti Core A* rangsor"),
        ("Category Hungarian Core A* Rank", "Kategória szerinti magyar affil Core A* rangsor"),
        ("Category First Author Core A* Rank", "Kategória szerinti első szerzős Core A* rangsor")
    ])

    # --- Logikai sorrend: előbb paper_count, aztán papers, majd first_author_papers, végül hungarian_papers ---
    ranks = ["A*", "A", "B", "C", "no_rank"]

    for r in ranks:
        labels[f"paper_count{r}"] = f"Core {r} közlemények száma"
    # Összesített mutató
    labels["Core A* equivalent"] = "Core A* equivalent"
    for r in ranks:
        labels[f"papers{r}"] = f"{r} besorolású közlemények"
    for r in ranks:
        labels[f"first_author_paper_count{r}"] = f"Core {r} közlemények száma (első szerző)"
    labels["First Author Core A* equivalent"]="First Author Core A* equivalent"
    for r in ranks:
        labels[f"first_author_papers{r}"] = f"Core {r} közlemények (első szerző)"
    for r in ranks:
        labels[f"hungarian_paper_count{r}"] = f"Core {r} közlemények száma (magyar affil)"
    labels["Hungarian Core A* equivalent"]="Hungarian Core A* equivalent"
    for r in ranks:
        labels[f"hungarian_papers{r}"] = f"{r} közlemények (magyar affil)"
    return labels


def is_empty_value(v):
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    if isinstance(v, (list, tuple, set)) and len(v) == 0:
        return True
    return False


def format_value(k, v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if k == "dblp_url" and v and not v.startswith("http"):
        return "https://dblp.org/pid" + v
    return str(v)

def print_author_hu(name, data: dict):
    labels = pretty_label_map()

    print(f"Személy: {name}")
    print("-" * 60)

    # --- 1️⃣ Kiírás a label_map sorrendjében ---
    for key, label in labels.items():
        if key not in data:
            continue
        value = data[key]
        if is_empty_value(value):
            continue
        print(f"{label}: {format_value(key, value)}")

    # --- 2️⃣ Maradék kulcsok (nincs formázás) ---
    remaining_keys = [k for k in data.keys() if k not in labels and not is_empty_value(data[k])]

    if remaining_keys:
        print("\n--- Egyéb mezők ---")
        for k in remaining_keys:
            print(f"{k}: {format_value(k, data[k])}")

if __name__ == "__main__":
    # for debugging
    mtmt_id = 10017593
    #mtmt_id = 10028156

    if len(sys.argv)>1:
        mtmt_id = sys.argv[1]

    author, data = find_dblp_in_google_sheets(mtmt_id)
    if author and data:
        print(f"DBLP azonosító a Google táblázatban: {author} - {data.get('dblp_url','N/A')}")
        # Preserve specific fields from Google Sheet if they exist (Category, MTMT Status, Works, Affiliations)
        preserve_fields = ['category', 'status', 'works', 'affiliations']
        existing_values = {field: data.get(field, '') for field in preserve_fields}
        
        dblp_person = dblp_utils.get_DBLP_record(data.get('dblp_url',''), author)
        mtmt_record, pub_rec = mtmt_utils.get_mtmt_record(str(mtmt_id))
        record, dblp_person = build_author_record(mtmt_record=mtmt_record, pub_rec=pub_rec, dblp_record=dblp_person)
        # Merge record into data (preserve existing fields from Google Sheet like Rankings)
        if record:
            data.update(record)
            # Restore fields from Google Sheet if they were non-empty
            for field, existing_value in existing_values.items():
                if existing_value:  # Only restore if the original value was non-empty
                    data[field] = existing_value
        record = data  # Use merged data as the record
    else:
        print("Nincs DBLP azonosító a Google táblázatban, MTMT alapján keresünk...")
        record, dblp_person=create_record(str(mtmt_id))
    if record and "dblp_author_name" in record:
        name=record["dblp_author_name"]
        author_data={}
        author_data[name] = count_CORE_papers_by_author(name, record, dblp_person)
        authors_data=google_author_sheet.download_author_google_sheet()
        if name not in authors_data:
            no_processing=False
        else:
            no_processing=True
        authors_data[name]=author_data[name]
        # Generate CSV and JSON with ranking fields, then print the single author
        google_author_sheet.generate_author_google_sheet(authors_data, print_only=False, no_processing=no_processing)
        author_data[name]=authors_data[name] # copy back single author
        print(author_data)
        for key, value in author_data.items():
            print_author_hu(key,value)
