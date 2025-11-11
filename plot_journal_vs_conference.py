#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot Journal vs Conference Publications
Creates an x-y scatter plot comparing MTMT journal D1 equivalents vs Hungarian Core A* equivalent.
"""

import json
import matplotlib.pyplot as plt
import numpy as np

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
        # Get x value: mtmt_journal D1 equivalents
        x_val = data.get("mtmt_journal D1 eqvivalents", None)
        
        # Get y value: Hungarian Core A* equivalent
        y_val = data.get("Hungarian Core A* equivalent", None)
        
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

def create_plot(data_points):
    """Create scatter plot with log scales and author name annotations."""
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Plot each category with different colors and add name annotations
    if data_points['hungary'][0]:  # Check if there's data
        ax.scatter(data_points['hungary'][0], data_points['hungary'][1], 
                  c='green', alpha=0.6, s=50, label='Hungary')
        # Add name annotations for Hungary
        for x, y, name in zip(data_points['hungary'][0], data_points['hungary'][1], data_points['hungary'][2]):
            ax.annotate(name, (x, y), fontsize=7, alpha=0.7, 
                       xytext=(3, 3), textcoords='offset points')
    
    if data_points['company'][0]:
        ax.scatter(data_points['company'][0], data_points['company'][1], 
                  c='yellow', alpha=0.6, s=50, label='Company', edgecolors='black', linewidth=0.5)
        # Add name annotations for Company
        for x, y, name in zip(data_points['company'][0], data_points['company'][1], data_points['company'][2]):
            ax.annotate(name, (x, y), fontsize=7, alpha=0.7,
                       xytext=(3, 3), textcoords='offset points')
    
    if data_points['abroad'][0]:
        ax.scatter(data_points['abroad'][0], data_points['abroad'][1], 
                  c='red', alpha=0.6, s=50, label='Abroad')
        # Add name annotations for Abroad
        for x, y, name in zip(data_points['abroad'][0], data_points['abroad'][1], data_points['abroad'][2]):
            ax.annotate(name, (x, y), fontsize=7, alpha=0.7,
                       xytext=(3, 3), textcoords='offset points')
    
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
    
    # Save figure
    output_file = "journal_vs_conference_plot.png"
    fig.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Plot saved to {output_file}")
    
    # Show plot
    plt.show()

if __name__ == "__main__":
    main()
