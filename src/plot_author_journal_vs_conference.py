#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot Journal vs Conference Publications
Creates an x-y scatter plot comparing MTMT journal D1 equivalents vs Hungarian Core A* equivalent.
"""

import json
import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statistics import mean
import csv



def is_in_CORE_field(row):
    if "mta_topic" in row:
        szakterulet = row["mta_topic"]
        if szakterulet and szakterulet.strip()!="":
            potential_keywords =["számítástudomány", "informatika", "operációkutatás","algoritmuselmélet","számítógép","Computer science","mesterséges intelligencia", ]
            szakterulet_lower = szakterulet.lower()
            for keyword in potential_keywords:
                if keyword in szakterulet_lower:
                    return True
    else:
        return True
    return False

# Try to import adjustText for automatic label positioning
try:
    from adjustText import adjust_text as _adjust_text
    HAS_ADJUST_TEXT = True
except ImportError as e:
    HAS_ADJUST_TEXT = False
    _adjust_text = None
    print(f"Note: adjustText not available ({e}). Labels may overlap.")

from plot_dgf_journal_cvs_conference import plot_dgf

# Try to import tikzplotlib for TikZ export (optional)
# try:
#     import tikzplotlib
#     HAS_TIKZPLOTLIB = True
# except Exception as e:
#     HAS_TIKZPLOTLIB = False
#     tikzplotlib = None
#     print(f"Note: tikzplotlib not available ({e}). TikZ export will be skipped.")

def load_authors_data():
    """Load full_authors_data.json with all author information."""
    try:
        with open("results/full_authors_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: results/full_authors_data.json not found. Please run google_author_sheet.py first.")
        return None

def extract_data_points(authors_data):
    """Extract x, y coordinates, names, and work location from authors_data."""
    hungary_x, hungary_y, hungary_names = [], [], []
    company_x, company_y, company_names = [], [], []
    abroad_x, abroad_y, abroad_names = [], [], []
    
    for name, data in authors_data.items():
        if not is_in_CORE_field(data):
            continue
        # Get x value: mtmt_journal D1 equivalents
        x_val = data.get("mtmt_journal D1 eqvivalents", None)
        
        # Get y value: Hungarian Core A* equivalent
        #y_val = data.get("Hungarian Core A* equivalent", None)
        y_val = data.get("Core A* equivalent", None)
        
        # Get work location
        works = data.get("works", "").lower()
        
        # Skip if either value is missing or zero/empty
        if x_val is None or y_val is None:
            continue
        
        try:
            x_val = float(x_val)
            y_val = float(y_val)
        except (ValueError, TypeError):
            continue
        
        # Skip zero values for log scale
        if x_val <= 0 or y_val <= 0:
            continue
        
        # Categorize by work location
        if "hungary" in works:
            hungary_x.append(x_val)
            hungary_y.append(y_val)
            hungary_names.append(name)
        elif "company" in works:
            company_x.append(x_val)
            company_y.append(y_val)
            company_names.append(name)
        elif "abroad" in works:
            abroad_x.append(x_val)
            abroad_y.append(y_val)
            abroad_names.append(name)
        else:
            # Default to abroad if not specified
            abroad_x.append(x_val)
            abroad_y.append(y_val)
            abroad_names.append(name)
    
    return {
        'hungary': (hungary_x, hungary_y, hungary_names),
        'company': (company_x, company_y, company_names),
        'abroad': (abroad_x, abroad_y, abroad_names)
    }

def save_data_to_csv(data_points, output_dir="doc/figures"):
    """Save scatter plot data points to CSV files for TikZ plotting."""
    if output_dir:  # Only create directory if path is not empty
        os.makedirs(output_dir, exist_ok=True)
    
    # Save data for each category
    for category in ['hungary', 'company', 'abroad']:
        x_vals, y_vals, names = data_points[category]
        if not x_vals:
            continue
            
        csv_path = os.path.join(output_dir, f"journal_vs_conference_{category}.csv")
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['x', 'y', 'name'])
            for x, y, name in zip(x_vals, y_vals, names):
                writer.writerow([x, y, name])
        
        print(f"Saved {len(x_vals)} data points to {csv_path}")

def generate_tikz_plot(output_dir="doc/figures"):
    """Generate TikZ/PGFPlots code for the scatter plot."""
    tikz_code = r"""\begin{figure}[htbp]
  \centering
  \begin{tikzpicture}
    \begin{loglogaxis}[
      width=0.9\textwidth,
      height=0.7\textwidth,
      xlabel={MTMT Journal D1 Equivalents},
      ylabel={Core A* Equivalent},
      title={Journal Publications vs Conference Publications},
      legend pos=north west,
      grid=both,
      grid style={line width=.1pt, draw=gray!10},
      major grid style={line width=.2pt,draw=gray!50},
      xmin=0.1, xmax=1000,
      ymin=0.1, ymax=1000,
    ]
    
    % Hungary (green)
    \addplot[
      only marks,
      mark=*,
      mark size=2pt,
      color=green!70!black,
      opacity=0.6
    ] table[x=x, y=y, col sep=comma] {figures/journal_vs_conference_hungary.csv};
    \addlegendentry{Hungary}
    
    % Company (yellow)
    \addplot[
      only marks,
      mark=*,
      mark size=2pt,
      color=yellow!80!black,
      opacity=0.6
    ] table[x=x, y=y, col sep=comma] {figures/journal_vs_conference_company.csv};
    \addlegendentry{Company}
    
    % Abroad (red)
    \addplot[
      only marks,
      mark=*,
      mark size=2pt,
      color=red!70!black,
      opacity=0.6
    ] table[x=x, y=y, col sep=comma] {figures/journal_vs_conference_abroad.csv};
    \addlegendentry{Abroad}
    
    \end{loglogaxis}
  \end{tikzpicture}
  \caption{Folyóirat-publikációk vs konferenciacikkek szerzők szerint. Az egyes szerzők munkahelyük szerint vannak színezve (zöld: Magyarország, sárga: cég, piros: külföld).}
  \label{fig:journal_vs_conference}
\end{figure}
"""
    
    tikz_path = os.path.join(output_dir, "journal_vs_conference_plot.tex")
    with open(tikz_path, 'w', encoding='utf-8') as f:
        f.write(tikz_code)
    
    print(f"TikZ plot code saved to {tikz_path}")

def create_plot(data_points, author_label=False):
    """Create scatter plot with log scales and author name annotations.
    
    If author_label=True, also generates an interactive HTML plot with mpld3.
    """
    fig, ax = plt.subplots(figsize=(10, 7))
    
    # Collect all text annotations for automatic adjustment
    texts = []
    

    sum_x = sum(data_points['hungary'][0]) + sum(data_points['company'][0]) + sum(data_points['abroad'][0])
    sum_y = sum(data_points['hungary'][1]) + sum(data_points['company'][1]) + sum(data_points['abroad'][1])
    ratios = [sum_y / sum_x for sum_x, sum_y in [(sum(data_points['hungary'][0]), sum(data_points['hungary'][1])),
                                                   (sum(data_points['company'][0]), sum(data_points['company'][1])),
                                                   (sum(data_points['abroad'][0]), sum(data_points['abroad'][1]))] if sum_x > 0]
    avg_ratio = mean(ratios) if ratios else 0
    print(f"Total sum of x values: {sum_x}")
    print(f"Total sum of y values: {sum_y}")
    print(f"Average y/x ratio across categories: {avg_ratio:.3f}")
    
    # Generate interactive HTML with mpld3 if author_label=True
    # This will be done after creating the matplotlib figure
    # Store scatter plot objects for mpld3
    scatter_objects = []
    scatter_labels = []
    
    # Plot each category with different colors and add name annotations
    # Use much smaller marker size for interactive plot (s=5) vs static (s=50)
    marker_size = 5 if author_label else 50
    
    if data_points['hungary'][0]:  # Check if there's data
        scatter_hungary = ax.scatter(data_points['hungary'][0], data_points['hungary'][1], 
                  c='green', alpha=0.6, s=marker_size, label='Hungary')
        scatter_objects.append(scatter_hungary)
        scatter_labels.append([f"{name}<br>Journal D1: {x:.2f}<br>Core A*: {y:.2f}" 
                               for x, y, name in zip(data_points['hungary'][0], 
                                                     data_points['hungary'][1], 
                                                     data_points['hungary'][2])])
    
    if data_points['company'][0]:
        scatter_company = ax.scatter(data_points['company'][0], data_points['company'][1], 
                  c='yellow', alpha=0.6, s=marker_size, label='Company', edgecolors='black', linewidth=0.5)
        scatter_objects.append(scatter_company)
        scatter_labels.append([f"{name}<br>Journal D1: {x:.2f}<br>Core A*: {y:.2f}" 
                               for x, y, name in zip(data_points['company'][0], 
                                                     data_points['company'][1], 
                                                     data_points['company'][2])])
    
    if data_points['abroad'][0]:
        scatter_abroad = ax.scatter(data_points['abroad'][0], data_points['abroad'][1], 
                  c='red', alpha=0.6, s=marker_size, label='Abroad')
        scatter_objects.append(scatter_abroad)
        scatter_labels.append([f"{name}<br>Journal D1: {x:.2f}<br>Core A*: {y:.2f}" 
                               for x, y, name in zip(data_points['abroad'][0], 
                                                     data_points['abroad'][1], 
                                                     data_points['abroad'][2])])
    
    # Set scale for both axes
    # For interactive HTML (mpld3), use linear scale as mpld3 doesn't handle log scale well
    if not author_label:
        ax.set_xscale('log')
        ax.set_yscale('log')
        xlabel_text = 'MTMT Journal D1 Equivalents (log scale)'
        ylabel_text = 'Hungarian Core A* Equivalent (log scale)'
    else:
        # Linear scale for interactive HTML
        xlabel_text = 'MTMT Journal D1 Equivalents'
        ylabel_text = 'Hungarian Core A* Equivalent'
    
    # Labels and title with larger fonts
    ax.set_xlabel(xlabel_text, fontsize=16)
    ax.set_ylabel(ylabel_text, fontsize=16)
    ax.set_title('Journal Publications vs Conference Publications\n(Color by Work Location)', fontsize=18, fontweight='bold')
    
    # Increase tick label size
    ax.tick_params(axis='both', which='major', labelsize=14)
    ax.tick_params(axis='both', which='minor', labelsize=12)
    
    # Add grid for better readability
    ax.grid(True, which="both", ls="-", alpha=0.2)
    
    # Add legend with larger font
    ax.legend(loc='best', framealpha=0.9, fontsize=14)
    
    # Tight layout
    plt.tight_layout()
    
    # Generate interactive HTML with mpld3 if author_label=True
    if author_label:
        try:
            import mpld3
            from mpld3 import plugins
            
            print(f"\nGenerating interactive HTML with mpld3...")
            print(f"  Scatter objects: {len(scatter_objects)}")
            
            # Add interactive tooltips to each scatter plot using the stored objects
            for scatter, tooltip_labels in zip(scatter_objects, scatter_labels):
                print(f"  Adding tooltip for {len(tooltip_labels)} points")
                tooltip = plugins.PointHTMLTooltip(scatter, tooltip_labels,
                                                   voffset=10, hoffset=10,
                                                   css="""
                                                   .mpld3-tooltip {
                                                       background: white;
                                                       border: 1px solid #ccc;
                                                       border-radius: 5px;
                                                       padding: 10px;
                                                       font-size: 16px;
                                                       font-family: Arial, sans-serif;
                                                       box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
                                                   }
                                                   """)
                plugins.connect(fig, tooltip)
            
            # Save interactive HTML
            output_html = 'figures/journal_vs_conference_interactive.html'
            os.makedirs('figures', exist_ok=True)
            
            # Generate HTML with mpld3
            html_string = mpld3.fig_to_html(fig)
            
            # Add custom CSS to make circles smaller
            # Note: We don't override zoom behavior to preserve tooltip functionality
            custom_script = """
            <script>
            (function() {
                // Wait for mpld3 to finish rendering
                setTimeout(function() {
                    var svg = d3.select("#fig01");
                    if (svg.empty()) return;
                    
                    // Set very small radius for all circles
                    var circles = svg.selectAll("circle.mpld3-path");
                    circles.attr("r", 1.5);  // Very small fixed radius
                }, 500);
            })();
            </script>
            
            <style>
            /* Additional CSS to ensure small circles */
            circle.mpld3-path {
                r: 1.5;
            }
            </style>
            """
            
            # Insert custom script before closing </body> tag
            html_string = html_string.replace('</body>', custom_script + '</body>')
            
            # Write modified HTML
            with open(output_html, 'w', encoding='utf-8') as f:
                f.write(html_string)
            
            print(f"Interactive HTML plot saved to {output_html}")
            print(f"  Total data points with tooltips: {sum(len(labels) for labels in scatter_labels)}")
            
        except ImportError as e:
            print(f"Warning: mpld3 not available ({e}). Skipping interactive HTML generation.")
            print("Install with: pip install mpld3")
        except Exception as e:
            print(f"Warning: Error generating mpld3 HTML ({e}). Continuing with static plot.")
    
    return fig

def main(authors_data):

    
    print("Extracting data points...")
    data_points = extract_data_points(authors_data)
    
    # Print statistics
    total_points = (len(data_points['hungary'][0]) + 
                   len(data_points['company'][0]) + 
                   len(data_points['abroad'][0]))
    
    print(f"Data points by category:")
    print(f"  Hungary: {len(data_points['hungary'][0])} authors")
    print(f"  Company: {len(data_points['company'][0])} authors")
    print(f"  Abroad: {len(data_points['abroad'][0])} authors")
    print(f"  Total: {total_points} authors")
    
    if total_points == 0:
        print("Warning: No valid data points found. Make sure authors have both mtmt_journal D1 eqvivalents and Hungarian Core A* equivalent values.")
        return
    
    print("Creating plot...")
    fig = create_plot(data_points)
    
    # Save figure as PNG
    output_file = "results/journal_vs_conference_plot.png"
    fig.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Plot saved to {output_file}")
    
    # Save data points to CSV files
    print("\nSaving data to CSV files...")
    save_data_to_csv(data_points)
    
    # Generate TikZ plot code
    print("Generating TikZ plot code...")
    generate_tikz_plot()
    
    # Create interactive HTML plot with labels (this also creates matplotlib figure)
    print("\nCreating interactive Plotly HTML with names")
    fig_interactive = create_plot(data_points, author_label=True)
    
    # Save the matplotlib version with labels too
    output_file_labels = "results/journal_vs_conference_plot_with_labels.png"
    fig_interactive.savefig(output_file_labels, dpi=300, bbox_inches='tight')
    print(f"Plot with labels saved to {output_file_labels}")
    
    # Show plot windows at the end
    #plt.show()
#     try:
#         print("Converting to Plotly...")
#         import plotly.tools as tls
#         import plotly.io as pio
#         import plotly.express as px
# fig = px.scatter(df, x="x", y="y")
# fig.write_html("fig.html")
#         plotly_fig = tls.mpl_to_plotly(fig)
#         pio.write_html(plotly_fig, file="figures/journal_vs_conference_plot.html", auto_open=True)
#         print("Plotly HTML saved to figures/journal_vs_conference_plot.html")
#     except ImportError as e:
#         print(f"Error importing plotly.tools: {e}. Skipping Plotly HTML generation.")
#         return


## plot_dgf moved to plot_dgf_journal_cvs_conference.py

if __name__ == "__main__":
    """Main execution function."""
    print("Loading author data...")
    authors_data = load_authors_data()
    print(f"Loaded {len(authors_data)} authors")
    main(authors_data)
