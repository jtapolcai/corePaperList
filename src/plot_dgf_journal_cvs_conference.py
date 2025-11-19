#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DFG publication types scatter plot
Reads a semicolon-separated CSV at doc/figures/abra_DFG_publikacios_tipusok.csv and
creates an x-y scatter where x = Folyóiratcikk, y = Konferencia cikk, and labels are the first column.
"""

from typing import Optional
import pandas as pd
import matplotlib.pyplot as plt

# try:
#     import tikzplotlib
#     HAS_TIKZPLOTLIB = True
# except Exception as e:
#     HAS_TIKZPLOTLIB = False
#     tikzplotlib = None
#     print(f"Note: tikzplotlib not available ({e}). TikZ export will be skipped.")


# Optional label overlap avoidance
try:
    from adjustText import adjust_text
    HAS_ADJUST_TEXT = True
except Exception as e:
    HAS_ADJUST_TEXT = False
    _adjust_text = None
    print(f"Note: adjustText not available ({e}). Labels may overlap.")


def plot_dgf(csv_path: str = "doc/figures/abra_DFG_publikacios_tipusok.csv"):
    """Create the DFG publication types scatter plot from CSV.

    CSV is expected to be semicolon-separated with columns:
    - 0: Label (e.g., Tudományterület)
    - 1: Folyóiratcikk (x-axis)
    - 2: Konferencia cikk (y-axis)

    Returns a matplotlib Figure.
    """
    # Load CSV
    df = pd.read_csv(csv_path, sep=';', engine='python')

    # Identify columns robustly
    label_col = df.columns[0]
    x_col = 'Folyóiratcikk' if 'Folyóiratcikk' in df.columns else df.columns[1]
    y_col = 'Konferencia cikk' if 'Konferencia cikk' in df.columns else df.columns[2]

    # Ensure numeric
    df['_x'] = pd.to_numeric(df[x_col], errors='coerce')
    df['_y'] = pd.to_numeric(df[y_col], errors='coerce')
    df_valid = df.dropna(subset=['_x', '_y'])

    labels = df_valid[label_col].astype(str).tolist()
    xs = df_valid['_x'].astype(float).tolist()
    ys = df_valid['_y'].astype(float).tolist()

    # Plot
    fig, ax = plt.subplots(figsize=(12, 8))
    scatter = ax.scatter(xs, ys, c='#1f77b4', alpha=0.75, s=50, edgecolors='white', linewidths=0.5)

    # Labels - use annotate with proper arrow configuration
    texts = []
    for x, y, label in zip(xs, ys, labels):
        txt = ax.annotate(label, xy=(x, y), xytext=(0, 0), 
                         textcoords='offset points',
                         fontsize=8, ha='center', va='center',
                         bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                                   edgecolor='gray', linewidth=0.5, alpha=0.85),
                         arrowprops=dict(arrowstyle='->', color='gray', lw=0.5, 
                                       alpha=0.6, shrinkA=0, shrinkB=3,
                                       connectionstyle='arc3,rad=0'))
        texts.append(txt)

    if HAS_ADJUST_TEXT and adjust_text is not None and texts:
        # adjustText will reposition labels to avoid overlaps
        adjust_text(texts,
                    expand_points=(1.5, 1.5),
                    expand_text=(1.2, 1.2),
                    force_points=(0.5, 0.5),
                    force_text=(0.5, 0.5),
                    ax=ax)

    # Axes and styling
    ax.set_xlabel('Folyóiratcikkek száma', fontsize=12)
    ax.set_ylabel('Konferenciacikkek száma', fontsize=12)
    ax.set_title('DFG publikációs típusok: folyóirat vs. konferencia', fontsize=14, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.4)
    fig.tight_layout()

    return fig


def generate_latex_table(csv_path: str = "doc/figures/abra_DFG_publikacios_tipusok.csv"):
    """Generate a 5x5 LaTeX table grouping fields by journal/conference publication counts.
    
    Returns:
        str: LaTeX table code
    """
    # Load CSV
    df = pd.read_csv(csv_path, sep=';', engine='python')
    
    # Identify columns
    label_col = df.columns[0]
    x_col = 'Folyóiratcikk' if 'Folyóiratcikk' in df.columns else df.columns[1]
    y_col = 'Konferencia cikk' if 'Konferencia cikk' in df.columns else df.columns[2]
    
    print (f"Generating LaTeX table using x_col='{x_col}', y_col='{y_col}', label_col='{label_col}'")
    # Convert to numeric
    df['_x'] = pd.to_numeric(df[x_col], errors='coerce')
    df['_y'] = pd.to_numeric(df[y_col], errors='coerce')
    df_valid = df.dropna(subset=['_x', '_y'])
    
  
    # Create 5x5 grid to collect field names
    # grid[conference_value][journal_value] = list of fields
    grid = {i: {j: [] for j in range(1, 6)} for i in range(1, 6)}
    
    for _, row in df_valid.iterrows():
        x_val = int(row['_x'])
        y_val = int(row['_y'])
        field_name = row[label_col]
        
        if 1 <= x_val <= 5 and 1 <= y_val <= 5:
            grid[y_val][x_val].append(field_name)
        else:
            print(f"Warning: Skipping field '{field_name}' with out-of-bounds values x={x_val}, y={y_val}")
    
    # Build LaTeX table
    latex_lines = []
    latex_lines.append(r"\begin{table}[htbp]")
    latex_lines.append(r"  \centering \scriptsize")
    latex_lines.append(r"  \caption{DFG tudományterületek publikációs típusok szerint csoportosítva. ")
    latex_lines.append(r"    A sorok a konferenciacikkek prioritását (1-5), az oszlopok a folyóiratcikkek ")
    latex_lines.append(r"    prioritását jelzik (1: legalacsonyabb, 5: legmagasabb).}")
    latex_lines.append(r"  \label{tab:dfg_publication_grid}")
    latex_lines.append(r"  \footnotesize")
    latex_lines.append(r"  \begin{tabular}{l|l|p{2.3cm}|p{2.3cm}|p{2.3cm}|p{2.3cm}|p{2.3cm}|}")
    latex_lines.append(r"    \hline")
    latex_lines.append(r"     & \multicolumn{5}{c|}{\textbf{Folyóiratcikkek prioritása}} \\")
    latex_lines.append(r"     & & \textbf{1} & \textbf{2} & \textbf{3} & \textbf{4} & \textbf{5} \\")
    latex_lines.append(r"    \hline")
    
    # Iterate from conference value 5 down to 1 (top to bottom in table)
    first_column= r"\multirow{5}{*}{\rotatebox{90}{\textbf{Konferenciacikkek prioritása}}}"
    for conf_val in range(5, 0, -1):
        row_cells = [f"{first_column}&\\textbf{{{conf_val}}}"]
        first_column=""
        # Iterate all journal priority columns 1..5
        for jour_val in range(1, 6):
            fields = grid[conf_val][jour_val]
            if fields:
                # Join multiple fields with line breaks, make text smaller
                cell_content = ", ".join([f"{f}" for f in fields])
                row_cells.append(cell_content)
            else:
                row_cells.append("")
        
        latex_lines.append("    " + " & ".join(row_cells) + r" \\")
        latex_lines.append(r"    \cline{2-7}")
    
    latex_lines.append(r"  \end{tabular}")
    latex_lines.append(r"\end{table}")
    
    return "\n".join(latex_lines)


if __name__ == "__main__":
    import os
    
    # Generate and save plot
    fig = plot_dgf()
    os.makedirs('doc/figures', exist_ok=True)
    output_path = 'doc/figures/dfg_publication_types.png'
    fig.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Plot saved to {output_path}")
    
    # Generate and save LaTeX table
    latex_table = generate_latex_table()
    latex_path = 'doc/figures/dfg_publication_types_table.tex'
    with open(latex_path, 'w', encoding='utf-8') as f:
        f.write(latex_table)
    print(f"LaTeX table saved to {latex_path}")
    
    # Show plot
    #plt.show()
    