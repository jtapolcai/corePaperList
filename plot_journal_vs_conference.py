#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot Journal vs Conference Publications
Creates an x-y scatter plot comparing MTMT journal D1 equivalents vs Hungarian Core A* equivalent.
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from statistics import mean
import csv
import os

author_label=False

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
HAS_ADJUST_TEXT = False
# try:
#     from adjustText import adjust_text
#     HAS_ADJUST_TEXT = True
# except ImportError as e:
#     HAS_ADJUST_TEXT = False
#     print(f"Note: adjustText not available ({e}). Labels may overlap.")

def load_authors_data():
    """Load full_authors_data.json with all author information."""
    try:
        with open("full_authors_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: full_authors_data.json not found. Please run google_author_sheet.py first.")
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

def create_plot(data_points):
    """Create scatter plot with log scales and author name annotations."""
    fig, ax = plt.subplots(figsize=(14, 10))
    
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
    # Plot each category with different colors and add name annotations
    if data_points['hungary'][0]:  # Check if there's data
        ax.scatter(data_points['hungary'][0], data_points['hungary'][1], 
                  c='green', alpha=0.6, s=50, label='Hungary')
        if author_label:
            # Add name annotations for Hungary
            for x, y, name in zip(data_points['hungary'][0], data_points['hungary'][1], data_points['hungary'][2]):
                text = ax.annotate(name, (x, y), fontsize=6, alpha=0.8, 
                        xytext=(3, 3), textcoords='offset points',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='none', alpha=0.6))
                texts.append(text)
    
    if data_points['company'][0]:
        ax.scatter(data_points['company'][0], data_points['company'][1], 
                  c='yellow', alpha=0.6, s=50, label='Company', edgecolors='black', linewidth=0.5)
        if author_label:
            # Add name annotations for Company
            for x, y, name in zip(data_points['company'][0], data_points['company'][1], data_points['company'][2]):
                text = ax.annotate(name, (x, y), fontsize=6, alpha=0.8,
                        xytext=(3, 3), textcoords='offset points',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='none', alpha=0.6))
                texts.append(text)
    
    if data_points['abroad'][0]:
        ax.scatter(data_points['abroad'][0], data_points['abroad'][1], 
                  c='red', alpha=0.6, s=50, label='Abroad')
        if author_label:
            # Add name annotations for Abroad
            for x, y, name in zip(data_points['abroad'][0], data_points['abroad'][1], data_points['abroad'][2]):
                text = ax.annotate(name, (x, y), fontsize=6, alpha=0.8,
                        xytext=(3, 3), textcoords='offset points',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='none', alpha=0.6))
                texts.append(text)
    
    # Use adjustText if available to prevent label overlap
    if HAS_ADJUST_TEXT and texts:
        adjust_text(texts, arrowprops=dict(arrowstyle='->', color='gray', lw=0.5, alpha=0.5),
                   expand_points=(1.5, 1.5), expand_text=(1.2, 1.2),
                   force_points=(0.5, 0.5), force_text=(0.5, 0.5))
    
    # Set log scale for both axes
    ax.set_xscale('log')
    ax.set_yscale('log')
    
    # Labels and title
    ax.set_xlabel('MTMT Journal D1 Equivalents (log scale)', fontsize=12)
    ax.set_ylabel('Hungarian Core A* Equivalent (log scale)', fontsize=12)
    ax.set_title('Journal Publications vs Conference Publications\n(Color by Work Location)', fontsize=14, fontweight='bold')
    
    # Add grid for better readability
    ax.grid(True, which="both", ls="-", alpha=0.2)
    
    # Add legend
    ax.legend(loc='best', framealpha=0.9)
    
    # Tight layout
    plt.tight_layout()
    
    return fig

def main():
    """Main execution function."""
    print("Loading author data...")
    authors_data = load_authors_data()
    
    if authors_data is None:
        return
    
    print(f"Loaded {len(authors_data)} authors")
    
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
    output_file = "journal_vs_conference_plot.png"
    fig.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Plot saved to {output_file}")
    
    # Save data points to CSV files
    print("\nSaving data to CSV files...")
    save_data_to_csv(data_points)
    
    # Generate TikZ plot code
    print("Generating TikZ plot code...")
    generate_tikz_plot()
    
    # Show plot
    plt.show()

if __name__ == "__main__":
    main()
