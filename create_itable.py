import json
import pandas as pd
import os
import requests
from urllib.parse import urlparse
from pathlib import Path

# Download favicons if not already present
logo_dir = Path("logos")
logo_dir.mkdir(exist_ok=True)

logo_map = {
    "mta_att": "https://mta.hu",
    "mtmt": "https://m2.mtmt.hu",
    "dblp": "https://dblp.org",
    "core": "https://www.core.edu.au"
}

def download_favicon(name, url):
    """Download favicon for a given URL if not already present"""
    logo_path = logo_dir / f"{name}_logo.png"
    if logo_path.exists():
        print(f"✓ {name} logo already exists")
        return str(logo_path)
    
    try:
        # Try to get favicon from /favicon.ico
        favicon_url = f"{url}/favicon.ico"
        response = requests.get(favicon_url, timeout=10)
        if response.status_code == 200:
            with open(logo_path, 'wb') as f:
                f.write(response.content)
            print(f"✓ Downloaded {name} logo from {favicon_url}")
            return str(logo_path)
    except Exception as e:
        print(f"✗ Could not download {name} logo: {e}")
    
    return None

# Download all favicons
print("Downloading favicons...")
for name, url in logo_map.items():
    download_favicon(name, url)

# Load the JSON file
print("\nLoading author data...")
with open('full_authors_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total authors: {len(data)}")

def safe_get(rec, key, default=""):
    """Safely get value from record"""
    val = rec.get(key, default)
    if val is None:
        return default
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    # Format floats to 2 decimal places
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)

def create_info_icon(tooltip_text):
    """Create an info icon with tooltip"""
    if not tooltip_text or tooltip_text == "":
        return ""
    escaped = tooltip_text.replace('"', '&quot;').replace("'", "&#39;").replace('\n', '<br>')
    return f'<span class="tooltip-container">ℹ️<span class="tooltip-text">{escaped}</span></span>'

def create_logo_links(rec):
    """Create small logo links for DBLP, MTMT, MTA"""
    links = []
    if rec.get("dblp_url_"):
        links.append(f'<a href="{rec["dblp_url_"]}" target="_blank"><img src="logos/dblp_logo.png" class="small-logo" alt="DBLP"/></a>')
    if rec.get("mtmt_id_"):
        links.append(f'<a href="{rec["mtmt_id_"]}" target="_blank"><img src="logos/mtmt_logo.png" class="small-logo" alt="MTMT"/></a>')
    if rec.get("mta_att_id_"):
        links.append(f'<a href="{rec["mta_att_id_"]}" target="_blank"><img src="logos/mta_att_logo.png" class="small-logo" alt="MTA"/></a>')
    return " ".join(links)

def create_image_cell(rec):
    """Create image cell with click to enlarge"""
    img_url = safe_get(rec, "mta_image_", "")
    if img_url and img_url != "":
        return f'<img src="{img_url}" class="author-thumb" onclick="window.open(\'{img_url}\', \'_blank\')" style="cursor:pointer;"/>'
    return ""

# Prepare rows for DataFrame
rows = []
for author_name, rec in data.items():
    # Build affiliation info tooltip
    affil_parts = []
    if rec.get("affiliations_"):
        affil_parts.append(safe_get(rec, "affiliations_"))
    if rec.get("mtmt_affiliations_"):
        affil_parts.append(f"MTMT: {safe_get(rec, 'mtmt_affiliations_')}")
    if rec.get("mta_elerhetosegek"):
        affil_parts.append(f"MTA: {safe_get(rec, 'mta_elerhetosegek')}")
    affil_tooltip = "<br>".join(affil_parts)
    
    # Build topic info tooltip
    topic_parts = []
    for key in ["mta_topic", "mta_bizottság", "mta_szervezeti_tagsagok"]:
        val = safe_get(rec, key)
        if val:
            topic_parts.append(val)
    topic_tooltip = "<br>".join(topic_parts)
    
    # Build career info tooltip
    career_parts = []
    for key in ["Years Since PhD", "mta_tud_fokozat", "mta_foglalkozas"]:
        val = safe_get(rec, key)
        if val:
            career_parts.append(val)
    career_tooltip = "<br>".join(career_parts)
    
    row = {
        # Columns 1-12: Author info
        "Kép": create_image_cell(rec),
        "Név": safe_get(rec, "dblp_author_name"),
        "Linkek": create_info_icon(f"MTMT név: {safe_get(rec, 'mtmt_name')}") + " " + create_logo_links(rec),
        "Magyar affil": safe_get(rec, "institution"),
        "Munkahely": safe_get(rec, "works"),
        "": create_info_icon(affil_tooltip),  # Empty header for info column
        "Itthon": safe_get(rec, "status"),
        " ": create_info_icon(safe_get(rec, "location")),  # Empty header for info column
        "Téma": safe_get(rec, "category"),
        "  ": create_info_icon(topic_tooltip),  # Empty header for info column
        "Karrier": safe_get(rec, "Career Length"),
        "   ": create_info_icon(career_tooltip),  # Empty header for info column
        
        # Columns 13-16: Aggregate metrics
        "Core A* ekv.": safe_get(rec, "Core A* equivalent"),
        "Journal D1 ekv.": safe_get(rec, "mtmt_journal D1 eqvivalents_"),
        "Hung. Core A* ekv.": safe_get(rec, "Hungarian Core A* equivalent"),
        "First Author Core A*": safe_get(rec, "First Author Core A* equivalent"),
        
        # Columns 17-26: Core papers
        "Core A*": safe_get(rec, "paper_countA*"),
        "    ": create_info_icon(safe_get(rec, "papersA*")),
        "Core A": safe_get(rec, "paper_countA"),
        "     ": create_info_icon(safe_get(rec, "papersA")),
        "Core B": safe_get(rec, "paper_countB"),
        "      ": create_info_icon(safe_get(rec, "papersB")),
        "Core C": safe_get(rec, "paper_countC"),
        "       ": create_info_icon(safe_get(rec, "papersC")),
        "Core no": safe_get(rec, "paper_countno_rank"),
        "        ": create_info_icon(safe_get(rec, "papersno_rank")),
        
        # Columns 27-36: Hungarian Core papers
        "Hung. A*": safe_get(rec, "hungarian_paper_countA*"),
        "         ": create_info_icon(safe_get(rec, "hungarian_papersA*")),
        "Hung. A": safe_get(rec, "hungarian_paper_countA"),
        "          ": create_info_icon(safe_get(rec, "hungarian_papersA")),
        "Hung. B": safe_get(rec, "hungarian_paper_countB"),
        "           ": create_info_icon(safe_get(rec, "hungarian_papersB")),
        "Hung. C": safe_get(rec, "hungarian_paper_countC"),
        "            ": create_info_icon(safe_get(rec, "hungarian_papersC")),
        "Hung. no": safe_get(rec, "hungarian_paper_countno_rank"),
        "             ": create_info_icon(safe_get(rec, "hungarian_papersno_rank")),
        
        # Columns 37-46: First author Core papers
        "First A*": safe_get(rec, "first_author_paper_countA*"),
        "              ": create_info_icon(safe_get(rec, "first_author_papersA*")),
        "First A": safe_get(rec, "first_author_paper_countA"),
        "               ": create_info_icon(safe_get(rec, "first_author_papersA")),
        "First B": safe_get(rec, "first_author_paper_countB"),
        "                ": create_info_icon(safe_get(rec, "first_author_papersB")),
        "First C": safe_get(rec, "first_author_paper_countC"),
        "                 ": create_info_icon(safe_get(rec, "first_author_papersC")),
        "First no": safe_get(rec, "first_author_paper_countno_rank"),
        "                  ": create_info_icon(safe_get(rec, "first_author_papersno_rank")),
        
        # Columns 47-54: MTMT metrics
        "D1 journal": safe_get(rec, "mtmt_rank_D1_"),
        "Q1 journal": safe_get(rec, "mtmt_rank_Q1_"),
        "Q2 journal": safe_get(rec, "mtmt_rank_Q2_"),
        "Q3 journal": safe_get(rec, "mtmt_rank_Q3_"),
        "Q4 journal": safe_get(rec, "mtmt_rank_Q4_"),
        "MTMT journal pubs": safe_get(rec, "mtmt_journal_publications"),
        "MTMT conf pubs": safe_get(rec, "mtmt_conference_publications"),
        "Hivatkozások": safe_get(rec, "mtmt_total_citations"),
    }
    rows.append(row)

# Create DataFrame
df = pd.DataFrame(rows)

print(f"Created DataFrame with {len(df)} rows and {len(df.columns)} columns")

# Generate HTML with custom styling
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Author Statistics</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 10px;
            font-size: 12px;
        }}
        .author-thumb {{
            max-width: 40px;
            max-height: 40px;
            border-radius: 3px;
        }}
        .small-logo {{
            width: 14px;
            height: 14px;
            margin: 0 1px;
            vertical-align: middle;
        }}
        /* Tooltip styles */
        .tooltip-container {{
            position: relative;
            display: inline-block;
            cursor: help;
            font-size: 13px;
            color: #666;
        }}
        .tooltip-text {{
            visibility: hidden;
            width: 400px;
            max-width: 90vw;
            background-color: #333;
            color: #fff;
            text-align: left;
            border-radius: 6px;
            padding: 10px;
            position: fixed;
            z-index: 9999;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 11px;
            line-height: 1.5;
            white-space: normal;
            word-wrap: break-word;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            pointer-events: none;
        }}
        .tooltip-container:hover .tooltip-text {{
            visibility: visible;
            opacity: 0.95;
        }}
        /* Ensure tooltip cell doesn't clip */
        table.dataTable tbody td:has(.tooltip-container) {{
            overflow: visible !important;
            position: relative;
        }}
        table.dataTable {{
            font-size: 11px;
            line-height: 1.3;
            border-collapse: collapse;
        }}
        table.dataTable thead th {{
            background-color: #f0f0f0;
            font-weight: bold;
            padding: 4px 5px;
            white-space: nowrap;
            font-size: 11px;
            /* Allow header tooltips to overflow */
            overflow: visible;
        }}
        table.dataTable tbody td {{
            padding: 3px 5px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        table.dataTable tbody tr {{
            height: 30px;
        }}
        table.dataTable tfoot th {{
            background-color: #e8e8e8;
            padding: 3px;
        }}
        table.dataTable tfoot input,
        table.dataTable tfoot select {{
            width: 100%;
            box-sizing: border-box;
            padding: 3px;
            font-size: 10px;
        }}
        /* Header tooltip adjustments */
        table.dataTable thead th .tooltip-container {{
            color: inherit;
            font-size: inherit;
        }}
        /* Narrow columns for info icons */
        table.dataTable thead th:empty,
        table.dataTable thead th:not(:has(text)) {{
            width: 25px;
            min-width: 25px;
            max-width: 25px;
            padding: 2px;
        }}
        table.dataTable tbody td:has(.info-icon) {{
            text-align: center;
            padding: 2px;
        }}
    </style>
    <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css">
    <script type="text/javascript" src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script type="text/javascript" src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
</head>
<body>
    <h1>Author Statistics</h1>
    {table}
    <script>
        $(document).ready(function() {{
            var table = $('table').DataTable({{
                "pageLength": 100,
                "order": [[12, "desc"]],  // Sort by Core A* ekv. descending
                "scrollX": true,
                "scrollY": "calc(100vh - 200px)",
                "scrollCollapse": true,
                "autoWidth": false,
                "initComplete": function() {{
                    // Define which columns should have filters (by column name)
                    var filterableColumns = [
                        'Név',
                        'Magyar affil',
                        'Munkahely', 
                        'Itthon',
                        'Téma',
                        'Karrier'
                    ];
                    
                    // Add column filters in footer
                    this.api().columns().every(function() {{
                        var column = this;
                        var title = $(column.header()).text().trim();
                        
                        // Skip columns not in filterable list
                        if (!filterableColumns.includes(title)) {{
                            $(column.footer()).html('');
                            return;
                        }}
                        
                        // Create select dropdown for text columns with limited unique values
                        var uniqueValues = column.data().unique().sort();
                        if (uniqueValues.length <= 20 && uniqueValues.length > 1) {{
                            var select = $('<select><option value="">Összes</option></select>')
                                .appendTo($(column.footer()).empty())
                                .on('change', function() {{
                                    var val = $.fn.dataTable.util.escapeRegex($(this).val());
                                    column.search(val ? '^' + val + '$' : '', true, false).draw();
                                }});
                            
                            uniqueValues.each(function(d) {{
                                if (d) {{
                                    select.append('<option value="' + d + '">' + d + '</option>');
                                }}
                            }});
                        }} else {{
                            // Create text input for other columns
                            $('<input type="text" placeholder="Szűrés..." style="width:100%"/>')
                                .appendTo($(column.footer()).empty())
                                .on('keyup change', function() {{
                                    if (column.search() !== this.value) {{
                                        column.search(this.value).draw();
                                    }}
                                }});
                        }}
                    }});
                }}
            }});
            
            // Position tooltips near mouse cursor
            $(document).on('mousemove', '.tooltip-container', function(e) {{
                var tooltip = $(this).find('.tooltip-text');
                tooltip.css({{
                    'left': e.pageX + 15 + 'px',
                    'top': e.pageY - 10 + 'px'
                }});
            }});
        }});
    </script>
</body>
</html>
"""

# Convert DataFrame to HTML table with footer
table_html = df.to_html(index=False, escape=False, classes='display')

# Add footer with column names for filters
footer_html = '<tfoot><tr>'
for col in df.columns:
    footer_html += f'<th>{col}</th>'
footer_html += '</tr></tfoot>'

# Insert footer before </table>
table_html = table_html.replace('</table>', footer_html + '</table>')

# Insert into template
full_html = html_template.format(table=table_html)

# Save to file
output_file = 'authors_table.html'
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(full_html)

print(f"\n✓ Interactive table saved to {output_file}")
print(f"  Open it in a browser to view the table.")