
# 🇭🇺 Tool for Listing CORE Ranked Conference Papers with Hungarian Affiliations

This tool generates a curated list of research papers authored by researchers affiliated with Hungarian institutions, published at **CORE A\*, A, B, and C** ranked conferences.

---

## 📚 Data Source

The data is sourced from the [DBLP](https://dblp.org) database and includes only those papers that meet the following criteria:

- Officially published in the **conference proceedings**
- **Page-length and venue filtering** to exclude:
  - Short papers (< 6 pages for A\*, < 5 pages for A, < 4 pages for B/C)
  - Workshops, companion volumes, forums, demos, and posters (automatically detected)
  - Work-in-progress submissions and extended abstracts
  - Papers with `@` in venue name (workshop indicator)
  - Crossref patterns indicating workshops (e.g., `/w`, `/fo`, `/workshops`)

### 🆕 Advanced Workshop/Companion Detection

The tool now automatically identifies and downgrades:
- **Workshop papers** (e.g., `SESENA@ICSE`, `conf/re/2023w`)
- **Companion volumes** (e.g., `ICSE (Companion Volume)`)
- **Forum papers** (e.g., `CAiSE Forum`, `conf/caise/2011fo`)
- **Demo/Poster tracks** (e.g., `INFOCOM Workshops`, `CVPR Workshops`)

Papers are automatically downgraded by **one CORE level**:
- A\* workshops → **CORE B**
- A workshops → **CORE C**
- B workshops → **CORE C**

Only **fully accepted, peer-reviewed main conference papers** are included in their original rank.

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
I'll investigate why it was skipped during the data collection process.

---

## 🐛 Troubleshooting

### DBLP Cache Issues
If you see outdated data or missing papers:
```bash
python run_every_day.py --force
```
This forces re-download of all DBLP author records.

### MTMT Cache
The MTMT mapping script caches results in `results/papers_in_mtmt_*.json`. To force re-query:
```bash
python src/map_core_papers_to_mtmt.py force
```

### Module Import Errors
Ensure you're in the project root and using the virtual environment:
```bash
cd corePaperList
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Missing Plots
Install optional dependencies:
```bash
pip install mpld3 adjustText
```

---

## 📝 Recent Changes (2024-11)

### Major Improvements
- ✅ **Workshop/Companion Detection**: Automatic identification via venue name, crossref patterns, and `@` symbol
- ✅ **Multi-CORE Support**: Extended from A*/A to include B and C rankings
- ✅ **Short Paper Reasons**: Each downgraded paper includes explanation in `short_paper_reason` field
- ✅ **Centralized Results**: All outputs moved to `results/` directory
- ✅ **Interactive Visualizations**: Added mpld3 support for hover tooltips
- ✅ **CSV Export**: Workshop reclassifications exported to `reclassified_workshop_papers.csv`

### Bug Fixes
- Fixed PID matching for author classification
- Fixed module import duplication issues
- Resolved JSON syntax errors in configuration files
- Corrected short paper tracking to use original rank before degradation

### Statistics
- **252 papers** reclassified due to workshop/companion/forum detection:
  - A\* → B: 57 papers
  - A → C: 195 papers (193 workshops + 2 forums)
- Current counts: **294 A\*, 699 A, 1142 B, 1727 C** papers

---

## 🛠️ Running the Tool

### Main Pipeline

Generate the complete paper list with all CORE rankings:

```bash
python run_every_day.py
```

Use `--force` to bypass DBLP cache and re-download all author records:

```bash
python run_every_day.py --force
```

**Outputs:**
- `results/coreAstar.bib`, `results/coreA.bib`, `results/coreB.bib`, `results/coreC.bib` (BibTeX files)
- `results/hungarian_papers_core{Astar,A,B,C,no_rank}.json` (JSON files with full metadata)
- `results/short_papers_core{Astar,A}.json` (Papers downgraded due to page count/workshop detection)
- `results/reclassified_workshop_papers.csv` (CSV export of workshop/companion papers)

### Additional Scripts

**Update charts and statistics:**
```bash
python src/generate_chart.py
```

**Map papers to MTMT database:**
```bash
python src/map_core_papers_to_mtmt.py
```

**Interactive HTML plots** (requires mpld3):
```bash
pip install mpld3
python run_every_day.py
```
Opens `figures/journal_vs_conference_interactive.html` with author tooltips.

---

## 📊 New Features

### 🔍 Short Paper Tracking
- Each downgraded paper includes a `short_paper_reason` field explaining why:
  - `"Page count X < limit Y"`
  - `"Venue contains 'WORKSHOP' keyword"`
  - `"Crossref 'conf/re/2023w' indicates workshop/companion/forum"`
  - `"No page information available"`

### 📈 Enhanced Visualization
- **Interactive plots** with author names on hover (mpld3)
- **SJR rating histograms** for journal versions
- **LaTeX tables** automatically generated for reports
- **CSV exports** for further analysis

### 🗂️ Centralized Results
All outputs now saved to `results/` directory:
- JSON paper lists by rank
- BibTeX files
- MTMT mapping data
- Workshop reclassification reports

---

## 📁 Project Structure

```
corePaperList/
├── run_every_day.py          # Main pipeline script
├── tudometer.py              # Paper counting utilities
├── src/                      # Source modules
│   ├── classify_paper.py    # Core ranking & workshop detection
│   ├── classify_author.py   # Author affiliation classification
│   ├── google_author_sheet.py # Google Sheets integration
│   ├── dblp_utils.py        # DBLP API utilities
│   ├── generate_chart.py    # Visualization generation
│   ├── map_core_papers_to_mtmt.py # MTMT database mapping
│   └── ...
├── inputs/                   # Configuration files
│   ├── core_table.csv       # CORE rankings by year
│   └── no_hungarian_affil_list.txt # Exclusion list
├── results/                  # Output directory
│   ├── hungarian_papers_*.json
│   ├── short_papers_*.json
│   ├── core*.bib
│   └── ...
├── dblp/                     # Cached DBLP author records
└── figures/                  # Generated plots
```

---

## 📁 Key Configuration Files

| File | Description |
|------|-------------|
| `inputs/core_table.csv` | CORE rankings by conference and year (dblp_venue, Acronym, YearsListed) |
| `inputs/no_hungarian_affil_list.txt` | Paper titles to exclude (no Hungarian affiliation) |
| Author spreadsheet | [Google Sheets](https://docs.google.com/spreadsheets/d/124qQX0h0CqPZZhBJiUT7myNqonp4dLJ4uyYZTtfauZI/edit?usp=sharing) with Hungarian researchers |
