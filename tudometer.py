# mtmt-ből töltsük a szerzőt
import datetime
import json
from os import path
import requests
import time
import xmltodict
import sys

from google_author_sheet import download_author_google_sheet, remove_accents, generate_author_google_sheet #, count_papers_by_author
from run_every_day import process_paper #,query_DBLP, count_papers_by_author

mtmt_id = 10000140
mtmt_id = 10001225

def find_dblp_in_google_sheets(mtmt_id):
    from google_author_sheet import download_author_google_sheet,remove_accents, count_papers_by_author, generate_author_google_sheet, fix_encoding, get_year_range, parse_affiliation, is_year_range

    authors_data=download_author_google_sheet()

    for author,data in authors_data.items():
        if 'mtmt_id' in data and data['mtmt_id']!='' and int(data['mtmt_id'])==int(mtmt_id):
            return author, data        
    return None, None

def query_DBLP_author(dblp_url, author, force=False):
    # we save the reuslts as dblp/author_name.json
    author_safe = remove_accents(author).replace(" ", "_")
    file_path = path.join("dblp", "{}.json".format(author_safe))

    if not force and path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data
            except Exception as e:
                print("Error loading {}: {}".format(file_path,e))

    try:
        print("Fetching: {} {}.xml".format(author, dblp_url))
        response = requests.get(dblp_url+".xml")

        if response.status_code != 200:
            raise Exception("HTTP error {}".format(response.status_code))
        #with open("debug_dblp_response.html", "wb") as f:
        #    f.write(response.content)
        data = xmltodict.parse(response.content)
        #data = response.json()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data
    except Exception as e:
        print("Error fetching {}: {}".format(dblp_url,e))
        return None

def find_mtmt_papers_by_title_of_author(title_orig, mtmt_id):
    title = title_orig.strip(' .')
    title =  title.replace(' ', '%20')
    url = f"https://m2.mtmt.hu/api/publication?format=json&cond=title;eq;{title}"
    response_ = requests.get(url, timeout=10)
    if response_.status_code == 200:
        response=response_.json()
        if "content" in response:
            papers=response["content"]
            for paper in papers:                
                if "authorships" in paper:
                    for author in paper["authorships"]:
                        if "author" in author:
                            mtmt_authors=author["author"]
                            if "label" in mtmt_authors:
                                if mtmt_authors["mtid"]==mtmt_id:
                                    return True
                            else:
                                if mtmt_authors["mtid"]==mtmt_id:
                                    return True
        else:
            print(f"⚠️ no content in {response}")
    else:
        print(f"⚠️ HTTP {response.status_code} error when querying MTMT for title {title_orig}")
    return False


def compare_dblp_to_mtmt_paper(paper, mtmt_record):
    title=""
    if "article" in paper:
        title = paper["article"].get("title", "")
    if "inproceedings" in paper:
        title = paper["inproceedings"].get("title", "")
    if title!="":
        if title.endswith('.'):
            title=title[:-1]
        if find_mtmt_papers_by_title_of_author(title, mtmt_record.get("mtid", "")):
            return True
    return False

def compare_dblp_to_mtmt_record(dblp_info, mtmt_record):
    dblp_record=query_DBLP_author(dblp_info.get("url", ""), author=dblp_info.get("author", "author_name"), force=True)
    with open("dblp_record.json", "w", encoding="utf-8") as f:
        json.dump(dblp_record, f, indent=2, ensure_ascii=False)
    # next check if there is a matchnig paper:
    papers=dblp_record.get("dblpperson", {}).get("r", [])
    if isinstance(papers, list):
        for paper in papers:
            if compare_dblp_to_mtmt_paper(paper, mtmt_record):
                return dblp_record
    else:
        if compare_dblp_to_mtmt_paper(papers, mtmt_record):
            return dblp_record
    return None

def find_dblp_by_name(mtmt_record):
    with open("mtmt_record.json", "w", encoding="utf-8") as f:
        json.dump(mtmt_record, f, indent=2, ensure_ascii=False)
    family_name = mtmt_record.get("familyName", "")
    given_name = mtmt_record.get("givenName", "")
    name = f"{given_name} {family_name}".strip()
    name_for_search = name.replace(' ', '+')
    url = f"https://dblp.org/search/author/api?q={name_for_search}&format=json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
                result = response.json()
                hits = result.get("result", {}).get("hits", {}).get("hit", [])
                for hit in hits:
                    dblp_info = hit.get("info", {})
                    dblp_record= compare_dblp_to_mtmt_record(dblp_info, mtmt_record)
                    if dblp_record:
                        return dblp_record
        else:
                print(f"HTTP hiba DBLP keresésnél {name}: {response.status_code}")
    except Exception as e:
            print(f"Hiba DBLP keresésnél {name}: {e}")
    return None

def get_mtmt_record(mtmt_id):
    mtmt_url = f"https://m2.mtmt.hu/api/author/{mtmt_id}?format=json"
    try:
        response = requests.get(mtmt_url, timeout=10)
        if response.status_code == 200:
            result = response.json()
            author_record = result.get("content", {})
            return author_record
        else:
            print(f"HTTP hiba MTMT URL lekérésnél {mtmt_id}: {response.status_code}")
    except Exception as e:
        print(f"Hiba MTMT URL lekérésnél {mtmt_id}: {e}")
    return None


def categorize(val):
    # Kulcsszavak kategorizáláshoz
    theory_kw = ["matematik", "elmélet", "gráf", "logika", "kombinatórik","kombinatorik","tudomány","algoritmus","operációkutatás","geometria","algebra","theory","matematika","formális","statisztika"]
    practical_kw = ["info", "hálózat", "távközl", "szoftver", "gép", "tanulás", "vision", "képfeld","intelligencia","technológia","technika","mérnök","robot","fizika","protokol","adat","internet","network","routing","szintézis","blockchain","rendszer","engineering","fuzz","idősor","fonetika","nyelv","műszaki","modellezés"]
    s = val.lower()
    if any(k in s for k in theory_kw):
        return "theory"   # elméleti
    if any(k in s for k in practical_kw):
        return "applied"   # gyakorlati
    return ""


def parse_last_modified(val):
    if val is None:
        return None
    # epoch (int/float)
    try:
        if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
            ts = int(val)
            if ts > 1e12:  # milliseconds
                ts = ts / 1000
            return datetime.datetime.fromtimestamp(ts)
    except Exception:
        pass
    # ISO-like string
    if isinstance(val, str):
        s = val.strip()
        try:
            return datetime.datetime.fromisoformat(s)
        except Exception:
            # try YYYY-MM-DD prefix
            try:
                return datetime.datetime.strptime(s[:10], "%Y-%m-%d")
            except Exception:
                return None
    return None

def is_active_in_mtmt(mtmt_record):
    now = datetime.datetime.now(datetime.timezone.utc)  # make 'now' timezone-aware (UTC)
    dt = parse_last_modified(mtmt_record.get("lastModified"))
    if dt is None:
        return ""
    # normalize dt to timezone-aware UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    age_years = (now - dt).total_seconds() / (365.25 * 24 * 3600)
    if age_years >= 3:
        return "inactive"
    return ""

def location_of_affiliation(dblp_record,mtmt_record):
    dblp_affiliations = ""
    if "note" in dblp_record:
        for note in dblp_record["note"]:
            if "affiliation" in note:
                affil = note["affiliation"].lower()
                if "@label" in note:
                    years = note["@label"].lower()
                    if dblp_affiliations!="":
                        dblp_affiliations+="; "
                    dblp_affiliations+=f"{affil} ({years})"
                    if not "since" in years:
                        continue
                dblp_affiliations=f"{affil}"
                if "budapest" in affil or "hungary" in affil or "magyarország" in affil or "szeged" in affil or "egyetem" in affil or "renyi":
                    return dblp_affiliations,"hungary"
                else:
                    return dblp_affiliations,"abroad"
    return dblp_affiliations,""

def check_paper(paper_dict, rank_name, first_author_pid, hungarian_affil, name_prefix,venues, authors_data, author):
    if "inproceedings" in paper_dict:
        paper = paper_dict["inproceedings"]
    elif "article" in paper_dict:
        paper = paper_dict["article"]
    else:
        return
    authors = paper.get("author", [])
    if first_author_pid!=None:
        if isinstance(authors, list) and len(authors)>1 and authors[0].get("@pid", "")!=first_author_pid[1:]:
            return False
    foreign_papers=None
    if hungarian_affil=="abroad":
        foreign_papers={}
    key, record, search_log = process_paper(paper_dict, rank_name, venues, foreign_papers=foreign_papers)
    if search_log.strip()!="" and search_log.strip()!="Skip as not inproceedings":
        print(search_log)
    if key:
        authors_data[author][name_prefix+"paper_count"+rank_name] += 1
        acronym = paper.get("booktitle", "")
        year = paper.get("year", "")
        venue_year=f"{acronym}{year} "
        authors_data[author][name_prefix+"papers"+rank_name]+=venue_year

def count_papers_by_author(author,data,rank_name, dblp_record, first_author_only=False, hungarian_affil=False, name_prefix=''):
    first_author_pid = None
    if first_author_only:
        first_author_pid = data.get("dblp_url", "")
    authors_data[author][name_prefix+"papers"+rank_name] = ""
    authors_data[author][name_prefix+"paper_count"+rank_name] = 0
    with open('core_{}_conferences_classified.json'.format(rank_name), 'r', encoding='utf-8') as f:
        venues = {k.upper(): v for k, v in json.load(f).items()}
    
    papers_found = dblp_record.get("r", {})
    #affil = data.get("affiliations", [])
    if isinstance(papers_found, dict):
        check_paper(papers_found, rank_name, first_author_pid,hungarian_affil,name_prefix,venues, authors_data, author)
    else:
        for paper in papers_found:
            check_paper(paper, rank_name, first_author_pid,hungarian_affil,name_prefix,venues, authors_data, author)

def count_CORE_papers_by_author(author,data, dblp_record=None):
    for rank_name in ["Astar","A","B","C"]:
        print(f"Counting {rank_name} papers for {author}...")
        count_papers_by_author(author,data,rank_name, dblp_record)
        count_papers_by_author(author,data,rank_name, dblp_record, first_author_only=True, name_prefix='first_author_')
        count_papers_by_author(author,data,rank_name, dblp_record, hungarian_affil=True, name_prefix='hungarian_')


if __name__ == "__main__":
    if len(sys.argv)>1:
        mtmt_id = sys.argv[1]

    author, data = find_dblp_in_google_sheets(mtmt_id)
    if author:
        print(f"DBLP azonosító a Google táblázatban: {author} - {data.get('dblp_url','N/A')}")
    else:
        print("Nincs DBLP azonosító a Google táblázatban, MTMT alapján keresünk...")
        mtmt_record = get_mtmt_record(mtmt_id)
        if mtmt_record:
            dblp_record = find_dblp_by_name(mtmt_record)
            if dblp_record:
                with open("dblp_record.json", "w", encoding="utf-8") as f:
                    json.dump(dblp_record, f, indent=2, ensure_ascii=False)
                dblp_person = dblp_record.get("dblpperson", {})
                name= dblp_person.get("@name", "")
                dblp_url = "/"+dblp_person.get("@pid", "")
                mtmt_id = mtmt_record.get("mtid", "")
                topic = mtmt_record.get("auxName", "")
                category = categorize(topic)
                status = is_active_in_mtmt(mtmt_record)
                works, affiliations = location_of_affiliation(dblp_person, mtmt_record)
                alias = dblp_person.get("alias", [])
                mtmt_name = mtmt_record.get("label", "")
                authors_data = {}
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
                count_CORE_papers_by_author(name, authors_data, dblp_person)
                print(authors_data)
                generate_author_google_sheet(authors_data, print_only=True, no_processing=True)
                print(f"DBLP rekord megtalálva: {name} - {dblp_url}")
            else:
                print("Nincs DBLP rekord megtalálva a név alapján.")
        else:
            print("Nem sikerült lekérni az MTMT rekordot.")
