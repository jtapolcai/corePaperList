
# 🇭🇺 Tool for Listing Core A* and Core A Conference Papers with Hungarian Affiliations

This tool generates a curated list of research papers authored by researchers affiliated with Hungarian institutions, published at top-tier **CORE A\*/A** conferences.

---

## 📚 Data Source

The data is sourced from the [DBLP](https://dblp.org) database and includes only those papers that meet the following criteria:

- Officially published in the **conference proceedings**
- At least **6 pages long**  
  _(4 pages minimum for **SODA**, **STOC**, and **FOCS**)_

This **page-length filter** is used to exclude:
- Short papers
- Work-in-progress submissions
- Demonstrations
- Extended abstracts
- Position papers
- Posters

Only **fully accepted, peer-reviewed conference papers** are included.

---

## 🔍 Filtering Options

You can filter the list by:

### 🧑‍💼 Author  
- Only authors with **at least 5 listed papers** are shown

### 🏛️ Affiliation Type
- `all_hungarian`: All authors are affiliated with Hungarian institutions
- `mostly_hungarian`: At least half of the authors are affiliated with Hungarian institutions
- `international`: Includes at least one Hungarian-affiliated author

### 🎓 Institution
e.g. BME, ELTE, Rényi Institute, SZTE, etc.

---

## ⚙️ How the List is Generated

The list is built using a [curated spreadsheet of Hungarian researchers]([https://dblp.org](https://docs.google.com/spreadsheets/d/124qQX0h0CqPZZhBJiUT7myNqonp4dLJ4uyYZTtfauZI/edit?usp=sharing)), which contains:
- Institutional affiliations (past and present)
- Optionally, the **years** of affiliation, which are used to determine **relevance in time**

A script processes this spreadsheet and queries **DBLP** to collect publication metadata.  
Only entries matching the **conference and page count criteria** are included.

---

## 💡 Want to Help?

If you'd like to contribute to the Hungarian researcher spreadsheet:

- ✅ You can suggest **corrections or additions** directly by leaving comments.
- ✉️ For **edit access**, email: `janos.tapolcai [at] gmail.com`.

If you know of a paper that **should be on the list but is missing**, please contact me.  
I’ll investigate why it was skipped during the data collection process.

---

## 🛠️ Running the Tool

To generate the latest list, run:

```bash
python3 run_every_day.py
```

it will generate two bibtex files: `coreA.bib`	and `coreAstar.bib` 

---

## 📁 Required Files

| File | Description |
|------|-------------|
| `core_Astar_conferences_classified.json` | List of CORE A\* conferences |
| `core_A_conferences_classified.json`     | List of CORE A conferences |
| `dblp_results_authors_from_xml.json`     | Author metadata parsed from DBLP |
| `foreign_authors.json`                   | Helper file for filtering (non-essential) |
| `google_author_sheet.py`                | Script to download and parse author spreadsheet |
