# -*- coding: utf-8 -*-
"""Author ordering and Core rank annotation utilities.

This module handles:
- Core rank calculations (A*, A, B, C conference/journal ranks)
- Author order determination in Google Sheet (sorted by Core equivalents)
- Multi-criteria sorting and position annotation

Terminology:
- "Core Rank" = the CORE conference ranking (A*, A, B, C)
- "Author Order" = the position/order of authors in the generated sheet
"""
from typing import List, Dict, Callable, Tuple, Optional

# Keys expected in rows produced by generate_author_google_sheet (after enrichment):
PRIMARY_SORT_KEYS = ["Core A* equivalent", 
                     "Hungarian Core A* equivalent", 
                     "First Author Core A* equivalent"]


def _safe_int(val) -> int:
    try:
        if val is None:
            return 0
        if isinstance(val, (int, float)):
            return int(val)
        s = str(val).strip()
        if s == "":
            return 0
        return int(float(s))  # handles "12.0"
    except Exception:
        return 0


def compute_author_order_positions(values: List[int]) -> List[int]:
    """Given a list of numeric values, return 1-based standard rank author order positions.
    Example: [10, 8, 8, 8, 5] -> [1, 2, 2, 2, 5]
    Equal values get the same rank, but the next rank accounts for the number of tied items.
    This determines the display order in the Google Sheet.
    """
    # Create list of (value, original_index) pairs
    indexed_values = [(v, i) for i, v in enumerate(values)]
    # Sort by value descending
    indexed_values.sort(key=lambda x: x[0], reverse=True)
    
    # Assign ranks using standard ranking (1,2,2,2,5)
    ranks = [0] * len(values)
    current_rank = 1
    for i, (val, orig_idx) in enumerate(indexed_values):
        if i > 0 and indexed_values[i-1][0] != val:
            # Different value from previous, update rank to current position + 1
            current_rank = i + 1
        ranks[orig_idx] = current_rank
    
    return ranks


def add_author_order_columns(rows: List[Dict[str, str]], extra_orderers: Optional[Dict[str, Callable[[Dict[str, str]], int]]] = None) -> List[Dict[str, str]]:
    """Annotate each row dict with author order columns based on predefined Core metrics.

    extra_orderers: mapping from column name (e.g., 'Institution Order') to a lambda(row)->int score.
    Returns the mutated list (for chaining).
    """
    if not rows:
        return rows
    if extra_orderers is None:
        extra_orderers = {}

    # Collect columns for primary Core metrics
    numeric_columns: Dict[str, List[int]] = {}
    for key in PRIMARY_SORT_KEYS:
        numeric_columns[key] = [_safe_int(r.get(key)) for r in rows]

    # Compute author order positions and store (Note: "Rank" here means Core rank column annotation)
    for key, values in numeric_columns.items():
        positions = compute_author_order_positions(values)
        pos_col = f"{key} Author Order"
        for r, pos in zip(rows, positions):
            r[pos_col] = str(pos)

    # Apply optional extra orderers
    for col_name, func in extra_orderers.items():
        scores = []
        for r in rows:
            try:
                scores.append(int(func(r)))
            except Exception:
                scores.append(0)
        positions = compute_author_order_positions(scores)
        order_col = f"{col_name} Author Order"
        score_col = f"{col_name} Score"
        for r, score, pos in zip(rows, scores, positions):
            r[score_col] = str(score)
            r[order_col] = str(pos)

    return rows


def sort_by_core_metrics(rows: List[Dict[str, str]], priority: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Sort rows by a priority list of Core metric columns (descending each).
    Falls back gracefully if a column is missing.
    priority defaults to PRIMARY_SORT_KEYS.
    This determines final author order in the sheet.
    """
    if not rows:
        return rows
    if priority is None:
        priority = PRIMARY_SORT_KEYS

    def sort_key(row: Dict[str, str]) -> Tuple[int, ...]:
        return tuple(_safe_int(row.get(k)) for k in priority)

    return sorted(rows, key=sort_key, reverse=True)


def order_and_annotate(rows: List[Dict[str, str]], extra_orderers: Optional[Dict[str, Callable[[Dict[str, str]], int]]] = None,
                       priority: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Convenience pipeline: add author order annotation columns then return sorted copy."""
    if extra_orderers is None:
        extra_orderers = {}
    if priority is None:
        priority = PRIMARY_SORT_KEYS
    add_author_order_columns(rows, extra_orderers=extra_orderers)
    return sort_by_core_metrics(rows, priority=priority)

# ---------------------------------------------------------------------------
# Extended ranking helpers (category-wise, time-since-PhD, custom group ranks)
# ---------------------------------------------------------------------------

def _safe_year(val) -> Optional[int]:
    try:
        if val is None:
            return None
        s = str(val).strip()
        if s == "":
            return None
        return int(float(s))
    except Exception:
        return None

def add_time_since_phd(rows: List[Dict[str, str]], phd_key: str = "PhD éve",
                       target_key: str = "Years Since PhD", current_year: Optional[int] = None) -> List[Dict[str, str]]:
    """Compute years since PhD (inclusive of current year) for each row.
    Missing / invalid values yield 0. Returns mutated list.
    """
    if current_year is None:
        from datetime import datetime
        current_year = datetime.now().year
    for r in rows:
        y = _safe_year(r.get(phd_key))
        if y is None or y > current_year:
            r[target_key] = "0"
        else:
            r[target_key] = str(current_year - y)
    return rows

def add_group_core_ranks(rows: List[Dict[str, str]], group_key: str, score_key: str,
                         rank_col: Optional[str] = None, score_transform: Optional[Callable[[Dict[str, str]], int]] = None) -> List[Dict[str, str]]:
    """Add Core ranks within each group defined by group_key using score_key (numeric).
    Dense rank (1,2,2,3). score_transform(row) -> int can override raw score.
    Note: "rank" here refers to position within the group based on Core metrics.
    """
    if not rows:
        return rows
    if rank_col is None:
        rank_col = f"{group_key} {score_key} Group Core Rank"
    # Build groups
    groups: Dict[str, List[Tuple[Dict[str, str], int]]] = {}
    for r in rows:
        g = str(r.get(group_key, ""))
        raw = score_transform(r) if score_transform else _safe_int(r.get(score_key))
        groups.setdefault(g, []).append((r, raw))
    # Rank inside each group
    for g, items in groups.items():
        scores = [s for _, s in items]
        positions = compute_author_order_positions(scores)
        for (row, _score), pos in zip(items, positions):
            row[rank_col] = str(pos)
    return rows

def add_category_core_rank(rows: List[Dict[str, str]], category_key: str = "Category",
                            score_key: str = "Core A* equivalent",
                            rank_col: str = "Category Core Rank") -> List[Dict[str, str]]:
    """Convenience: rank authors within their category by Core A* equivalent score."""
    return add_group_core_ranks(rows, group_key=category_key, score_key=score_key, rank_col=rank_col)

def determine_age_group(years_since_phd: int) -> str:
    """Determine age group based on years since PhD.
    Categories: [0-5], [5-10], [10-20], [20+]
    """
    if years_since_phd < 0:
        return "unknown"
    elif years_since_phd <= 5:
        return "0-5 év"
    elif years_since_phd <= 10:
        return "5-10 év"
    elif years_since_phd <= 20:
        return "10-20 év"
    else:
        return "20+ év"

def add_age_group_column(rows: List[Dict[str, str]], phd_years_key: str = "Years Since PhD",
                         target_key: str = "Age Group") -> List[Dict[str, str]]:
    """Add age group classification based on years since PhD."""
    for r in rows:
        years = _safe_int(r.get(phd_years_key, "0"))
        r[target_key] = determine_age_group(years)
    return rows

def add_all_category_ranks(rows: List[Dict[str, str]], category_key: str = "Category") -> List[Dict[str, str]]:
    """Add rankings within category for all three main Core metrics."""
    metrics = [
        ("Core A* equivalent", "Category Core A* Rank"),
        ("Hungarian Core A* equivalent", "Category Hungarian Core A* Rank"),
        ("First Author Core A* equivalent", "Category First Author Core A* Rank")
    ]
    for score_key, rank_col in metrics:
        add_group_core_ranks(rows, group_key=category_key, score_key=score_key, rank_col=rank_col)
    return rows

def add_all_age_group_ranks(rows: List[Dict[str, str]], age_group_key: str = "Age Group") -> List[Dict[str, str]]:
    """Add rankings within age group for all three main Core metrics."""
    metrics = [
        ("Core A* equivalent", "Age Group Core A* Rank"),
        ("Hungarian Core A* equivalent", "Age Group Hungarian Core A* Rank"),
        ("First Author Core A* equivalent", "Age Group First Author Core A* Rank")
    ]
    for score_key, rank_col in metrics:
        add_group_core_ranks(rows, group_key=age_group_key, score_key=score_key, rank_col=rank_col)
    return rows

def prepare_author_order_with_extensions(rows: List[Dict[str, str]],
                                          include_time_since_phd: bool = True,
                                          include_category_ranks: bool = True,
                                          include_age_group_ranks: bool = True,
                                          current_year: Optional[int] = None) -> List[Dict[str, str]]:
    """Pipeline adding author order annotations + optional extended Core ranks.
    Returns mutated list for chaining.
    
    Args:
        rows: List of author data rows
        include_time_since_phd: Add "Years Since PhD" column
        include_category_ranks: Add rankings within category (applied/theory) for all metrics
        include_age_group_ranks: Add rankings within age group ([0-5], [5-10], [10-20], [20+])
        current_year: Year for PhD calculation (defaults to current year)
    """
    order_and_annotate(rows)  # base author order + sorting
    
    if include_time_since_phd:
        add_time_since_phd(rows, current_year=current_year)
        # Add age group classification (needed for age group ranks)
        add_age_group_column(rows)
    
    if include_category_ranks:
        add_all_category_ranks(rows)
    
    if include_age_group_ranks:
        if not include_time_since_phd:
            # Need to compute years since PhD first
            add_time_since_phd(rows, current_year=current_year)
            add_age_group_column(rows)
        add_all_age_group_ranks(rows)
    
    return rows
