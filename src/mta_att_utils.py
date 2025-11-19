# -*- coding: utf-8 -*-
"""
MTA ATT (Magyar Tudományos Akadémia) utilities module
Handles MTA member data from CSV files, safe data extraction, and record merging.
"""
import sys, os
_parent = os.path.dirname(os.path.dirname(__file__))
_src = os.path.dirname(__file__)
if _parent not in sys.path: sys.path.insert(0, _parent)
if _src not in sys.path: sys.path.insert(0, _src)

import pandas as pd


def safe_get_value(row, key, default=''):
    """Safely get value from pandas Series, handling NaN and None.
    
    Args:
        row: pandas Series (DataFrame row)
        key: Column name to retrieve
        default: Default value if missing or NaN
        
    Returns:
        str: Clean string value, empty if NaN/None
    """
    if key not in row:
        return default
    val = row[key]
    if pd.isna(val) or val is None:
        return default
    # If float but integer value, return as int string (no .0)
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


from typing import Optional

def get_mta_att_row(mtmt_id: str, author_name: Optional[str] = None):
    """Find MTA ATT member row by MTMT ID.
    
    Optionally supply author_name (English or Hungarian) for logging; future
    enhancement could cache results per author similarly to MTMT/DBLP.
    
    Args:
        mtmt_id: MTMT identifier to search
        author_name: Optional human-readable name for diagnostics
    Returns:
        pandas Series or None
    """
    if author_name:
        print(f"Searching MTA ATT rows for {author_name} (MTMT {mtmt_id})")
    for output_file in ["vi_osztaly_tagok.csv", "iii_osztaly_tagok.csv"]:
        try:
            osztaly = pd.read_csv(f"inputs/{output_file}", encoding='utf-8-sig')
            for _, row in osztaly.iterrows():
                if 'Publikációk' in row:
                    publikaciok = safe_get_value(row, 'Publikációk')
                    if publikaciok:
                        try:
                            if int(mtmt_id) == int(publikaciok):
                                return row
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            print(f"Error reading {output_file}: {e}")
    return None


def add_mta_att_record(angol_nev, row, mtmt_id, magyar_nev, data, 
                       dblp_record=None, mtmt_record=None, 
                       check_if_dblp_matches_mtmt_func=None):
    """Add MTA ATT record data to the author data dict.
    
    If dblp_record and mtmt_record are provided, skip verification.
    Otherwise, use callback to verify DBLP/MTMT correspondence.
    
    Args:
        angol_nev: English author name
        row: pandas Series with MTA data
        mtmt_id: MTMT identifier
        magyar_nev: Hungarian name
        data: Author data dict to update
        dblp_record: Optional pre-verified DBLP record
        mtmt_record: Optional pre-verified MTMT record
        check_if_dblp_matches_mtmt_func: Callback for verification
        
    Returns:
        tuple: (success: bool, updated_data: dict)
    """
    if dblp_record is None or mtmt_record is None:
        if check_if_dblp_matches_mtmt_func:
            dblp_record, mtmt_record = check_if_dblp_matches_mtmt_func(
                mtmt_id, angol_nev, magyar_nev
            )
        else:
            return False, data
    
    # Proceed only if both records are present
    if dblp_record and mtmt_record:
        print("Valóban ő az!")
        
        # Determine category from MTA class
        class_type = ""
        tud_osztaly = safe_get_value(row, 'Tudományos osztály')
        if tud_osztaly == 'III. Matematikai Tudományok Osztálya':
            class_type = 'theory'
        if tud_osztaly == 'IV. Műszaki Tudományok Osztálya':
            class_type = 'applied'
        
        if data.get("category", "") != class_type and class_type:
            print(f"{safe_get_value(row, 'Hivatalos név')} kategóriája "
                  f"{data.get('category', '')} -> mta-ban {class_type} "
                  f"{data.get('mtmt_name', '')}")
            data['category'] = class_type
        
        # Extract MTA data
        hivatalos_nev_url = safe_get_value(row, 'Hivatalos név_URL')
        data['mta_att_id'] = hivatalos_nev_url.replace(
            "https://mta.hu/koztestuleti_tagok?PersonId=", ''
        )
        data['mta_image'] = safe_get_value(row, 'image')
        data['mta_tud_fokozat'] = safe_get_value(row, 'Aktuális fokozat')
        data['mta_topic'] = safe_get_value(row, 'Aktuális fokozat szakterülete')
        data['mta_bizottság'] = safe_get_value(row, 'Tudományos bizottság')
        data['mta_elerhetosegek'] = safe_get_value(row, 'Elérhetőségek')
        data['mta_szervezeti_tagsagok'] = safe_get_value(row, 'Szervezeti tagságok')
        data['mta_dijak'] = safe_get_value(row, 'Díjak')
        data['mta_kutatasi_tema'] = safe_get_value(row, 'Kutatási téma')
        
        # Find PhD year from any column containing 'phd'
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
        
        # Determine membership type
        rendes = safe_get_value(row, 'rendes tag')
        levelező = safe_get_value(row, 'levelező tag')
        külső = safe_get_value(row, 'külső tag')
        data['mta_tagsag'] = (
            'rendes tag' if rendes else 
            'levelező tag' if levelező else 
            'külső tag' if külső else ''
        )
        
        data['mta_elhunyt'] = safe_get_value(row, 'Elhunyt')
        
        # Validate MTMT ID consistency
        publikaciok = safe_get_value(row, 'Publikációk')
        if data.get('mtmt_id', '') and publikaciok:
            try:
                if int(data['mtmt_id']) != int(mtmt_id):
                    print(f"⚠️ Warning: {safe_get_value(row, 'Hivatalos név')} "
                          f"névhez két különböző MTMT ID tartozik: "
                          f"{data['mtmt_id']} és {mtmt_id}")
                    data['mtmt_id'] = str(int(mtmt_id))
            except (ValueError, TypeError):
                pass
        
        data['mtmt_name'] = mtmt_record.get("label", "")
        return True, data
    return False, data


def load_mta_class_data(class_name="vi_osztaly"):
    """Load MTA class member data from CSV.
    
    Args:
        class_name: 'vi_osztaly' (Engineering) or 'iii_osztaly' (Mathematics)
        
    Returns:
        pandas DataFrame: MTA member data
    """
    file_path = f"inputs/{class_name}_tagok.csv"
    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        return df
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return pd.DataFrame()
