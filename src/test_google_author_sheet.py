import google_author_sheet
import pandas as pd
import csv
import json

def verify_table_conversions():
    # Download original data as list of dicts
    original_table = google_author_sheet.download_raw_author_google_sheet()
    
    # Process data
    authors_data = google_author_sheet.download_author_google_sheet()
    google_author_sheet.generate_author_google_sheet(authors_data, print_only=False, no_processing=False)
    with open("authors_data.csv", "r", encoding="utf-8-sig") as f:
        converted_table = list(csv.DictReader(f))
    
    # Create DataFrames
    original_df = pd.DataFrame(original_table)
    converted_df = pd.DataFrame(converted_table)

    print(f"\nEredeti sorok: {len(original_df)}")
    print(f"Visszakonvertált sorok: {len(converted_df)}")

    # Oszlopok összehasonlítása
    orig_cols = set(original_df.columns)
    conv_cols = set(converted_df.columns)

    print(f"\n{'='*80}")
    print("OSZLOPOK ÖSSZEHASONLÍTÁSA:")
    print(f"{'='*80}")

    missing_in_converted = orig_cols - conv_cols
    extra_in_converted = conv_cols - orig_cols

    if missing_in_converted:
        print(f"\n❌ Hiányzó oszlopok a visszakonvertáltból ({len(missing_in_converted)} db):")
        for col in sorted(missing_in_converted):
            print(f"   - {col}")
    else:
        print("\n✅ Minden eredeti oszlop megvan")

    if extra_in_converted:
        print(f"\n➕ Extra oszlopok a visszakonvertáltban ({len(extra_in_converted)} db):")
        for col in sorted(extra_in_converted):
            print(f"   + {col}")
    else:
        print("\n✅ Nincs extra oszlop")

    # Közös oszlopok
    common_cols = orig_cols & conv_cols
    print(f"\n📊 Közös oszlopok: {len(common_cols)} db")

    # Author alapú összehasonlítás (index)
    print(f"\n{'='*80}")
    print("SZERZŐK (Author) ÖSSZEHASONLÍTÁSA:")
    print(f"{'='*80}")

    # Check if 'Author' column exists in both DataFrames
    if 'Author' not in original_df.columns:
        print("❌ HIBA: 'Author' oszlop hiányzik az eredeti táblázatból!")
        print(f"Elérhető oszlopok: {list(original_df.columns)[:10]}")
        return
    
    if 'Author' not in converted_df.columns:
        print("❌ HIBA: 'Author' oszlop hiányzik a visszakonvertált táblázatból!")
        print(f"Elérhető oszlopok: {list(converted_df.columns)[:10]}")
        return

    orig_authors = set(original_df['Author'].dropna())
    conv_authors = set(converted_df['Author'].dropna())

    missing_authors = orig_authors - conv_authors
    extra_authors = conv_authors - orig_authors

    if missing_authors:
        print(f"\n❌ Hiányzó szerzők ({len(missing_authors)} db):")
        for author in sorted(missing_authors):
            print(f"   - {author}")
    else:
        print("\n✅ Minden szerző megvan")

    if extra_authors:
        print(f"\n➕ Extra szerzők ({len(extra_authors)} db):")
        for author in sorted(extra_authors):
            print(f"   + {author}")

    # Értékek összehasonlítása közös szerzőknél
    print(f"\n{'='*80}")
    print("ÉRTÉKEK ÖSSZEHASONLÍTÁSA (közös szerzőknél):")
    print(f"{'='*80}")

    # Index beállítása Author-ra
    orig_indexed = original_df.set_index('Author')
    conv_indexed = converted_df.set_index('Author')

    common_authors = orig_authors & conv_authors

    differences = {}

    for col in sorted(common_cols):
        if col == 'Author':
            continue
        
        diff_count = 0
        diff_details = []
        
        for author in common_authors:
            if author not in orig_indexed.index or author not in conv_indexed.index:
                continue
                
            orig_val = orig_indexed.loc[author, col] if col in orig_indexed.columns else pd.NA
            conv_val = conv_indexed.loc[author, col] if col in conv_indexed.columns else pd.NA
            
            # Normalizálás összehasonlításhoz
            def _to_str_for_compare(val):
                # If a DataFrame/Series, handle missingness and join values into a single string
                if isinstance(val, (pd.Series, pd.DataFrame)):
                    try:
                        # If all values are NA -> return empty string
                        isna_all = val.isna().all()
                        if isinstance(isna_all, (pd.Series, pd.DataFrame)):
                            # Reduce to a scalar boolean if possible
                            try:
                                if isna_all.all():
                                    return ""
                            except Exception:
                                pass
                        else:
                            # scalar-like (bool / numpy.bool_) is safe to cast
                            if bool(isna_all):
                                return ""
                    except Exception:
                        # Fallback check for mixed types: handle Series/DataFrame or scalar safely
                        try:
                            isa = pd.isna(val)
                            # If it has an 'all' method (Series/DataFrame), call it and coerce to bool safely
                            if hasattr(isa, "all"):
                                try:
                                    if bool(isa.all()):
                                        return ""
                                except Exception:
                                    pass
                            else:
                                # scalar-like result (e.g. numpy.bool_) — coerce to bool
                                try:
                                    if bool(isa):
                                        return ""
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    try:
                        # Convert elements to stripped strings and join with '; '
                        if isinstance(val, pd.DataFrame):
                            # Flatten DataFrame to string representation
                            return val.astype(str).apply(lambda x: x.str.strip()).astype(str).to_string()
                        else:
                            series = val.astype(str).apply(lambda x: x.strip())
                            return "; ".join(series.tolist())
                    except Exception:
                        return str(val).strip()
                else:
                    return str(val).strip() if not pd.isna(val) else ""
            
            orig_str = _to_str_for_compare(orig_val)
            conv_str = _to_str_for_compare(conv_val)
            
            if orig_str != conv_str:
                diff_count += 1
                if diff_count <= 5:  # Csak első 5 példa
                    diff_details.append({
                        'author': author,
                        'original': orig_str[:100],  # Max 100 karakter
                        'converted': conv_str[:100]
                    })
        
        if diff_count > 0:
            differences[col] = {
                'count': diff_count,
                'examples': diff_details
            }

    if differences:
        print(f"\n⚠️  Eltérések találhatók {len(differences)} oszlopban:\n")
        
        for col, info in sorted(differences.items(), key=lambda x: x[1]['count'], reverse=True):
            print(f"\n📌 {col}: {info['count']} eltérés")
            for ex in info['examples']:
                print(f"   Szerző: {ex['author']}")
                print(f"     Eredeti:       '{ex['original']}'")
                print(f"     Visszakonvert: '{ex['converted']}'")
    else:
        print("\n✅ Minden érték egyezik a közös szerzőknél!")

    print(f"\n{'='*80}")
    print("ÖSSZEFOGLALÓ:")
    print(f"{'='*80}")
    print(f"Szerzők: {len(common_authors)} közös, {len(missing_authors)} hiányzik, {len(extra_authors)} extra")
    print(f"Oszlopok: {len(common_cols)} közös, {len(missing_in_converted)} hiányzik, {len(extra_in_converted)} extra")
    if differences:
        print(f"Eltérő értékek: {len(differences)} oszlopban")
    else:
        print("Eltérő értékek: 0")
    print(f"{'='*80}")


def count_papers_by_author(authors_data, rank_name, first_author_only=False, already_abroad_papers=False, name_prefix=''):
    pid_to_name = {data["dblp_url"]: name for name, data in authors_data.items()}
    for author, data in authors_data.items():
        authors_data[author][name_prefix+"papers"+rank_name] = ""
        authors_data[author][name_prefix+"paper_count"+rank_name] = 0

    #filename='already_abroad_papers_core{}.json'.format(rank_name)
    #filename='short_papers_core{}.json'.format(rank_name)
    filename='hungarian_papers_core{}.json'.format(rank_name)
    if already_abroad_papers:
        filename='already_abroad_papers_core{}.json'.format(rank_name)
    with open(filename, "r", encoding="utf-8") as f:
        papers = json.load(f)
        print("processing {}".format(filename))
    with open("foreign_authors.json", "r", encoding="utf-8") as f:
        foreign_authors = json.load(f)
    unknown_authors=[]
    new_papers = {}
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
                authors_data[author_][name_prefix+"paper_count"+rank_name] += 1
                authors_data[author_][name_prefix+"papers"+rank_name]+=venue_year+" "
            else:
                if author_ not in unknown_authors and author_ not in foreign_authors:
                    unknown_authors.append(author_)
                    # record the paper as a new/unmatched paper for this rank
                    try:
                        new_papers[key] = paper
                    except Exception:
                        pass
            if first_author_only:
                break
    with open("new_authors.json", "w", encoding="utf-8") as f:
        json.dump(unknown_authors, f, indent=2, ensure_ascii=False)

    # also write the new/unmatched papers we discovered for this rank
    try:
        out_file = f"new_{rank_name}_papers{name_prefix}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(new_papers, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

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



if __name__ == "__main__":
    verify_table_conversions()