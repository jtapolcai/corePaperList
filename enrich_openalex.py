#!/usr/bin/env python3
"""
Enrich author profiles with OpenAlex data.

For each profile that lacks an openalex_id:
  1. Find their papers (from results/ JSONs) and extract DOIs from the `ee` field.
  2. Query OpenAlex works API by DOI → find the matching author entry.
  3. Fetch full author profile: openalex_id, orcid, h_index, topics.
  4. Fallback: name search if DOI lookup fails.

Run from corePaperList-git/:
  python3 enrich_openalex.py [--dry-run] [--limit N]
"""
import json
import os
import re
import time
import argparse
import unicodedata
from collections import defaultdict

try:
    import requests
except ImportError:
    raise SystemExit("pip install requests")

PROFILES_DIR = "profiles"
RESULTS_DIR = "results"
OA_BASE = "https://api.openalex.org"
# Polite pool: include email so OA prioritises our requests
OA_EMAIL = "tapolcai@tmit.bme.hu"
HEADERS = {"User-Agent": f"corePaperList/1.0 (mailto:{OA_EMAIL})"}
SLEEP = 0.12   # ~8 req/s; OA allows 10
MAX_TOPICS = 25


# ── helpers ──────────────────────────────────────────────────────────────────

def normalize_name(s):
    """Lowercase, strip accents, collapse whitespace."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def extract_doi(paper):
    """Return a bare DOI string (no URL prefix) or '' ."""
    for field in ("doi", "ee", "url"):
        val = (paper.get(field) or "").strip()
        m = re.search(r"10\.\d{4,}/\S+", val)
        if m:
            return m.group(0).rstrip(".,)")
    return ""


def oa_get(path, params=None):
    """GET from OpenAlex, return parsed JSON or None."""
    url = OA_BASE + path
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            print("  Rate limited — sleeping 5s")
            time.sleep(5)
        return None
    except Exception as e:
        print(f"  Request error: {e}")
        return None


def find_by_doi(doi, author_name_norm, dblp_pid):
    """
    Query OA works by DOI, find the authorship entry matching our author.
    Returns (oa_author_id, confidence) or (None, 0).
    """
    data = oa_get(f"/works/doi:{doi}", {"select": "id,authorships"})
    time.sleep(SLEEP)
    if not data or "authorships" not in data:
        return None, 0

    for auth in data["authorships"]:
        oa_author = auth.get("author") or {}
        oa_name = normalize_name(oa_author.get("display_name", ""))
        oa_id = oa_author.get("id", "")

        if not oa_id:
            continue

        # Primary match: name similarity
        name_score = _name_sim(author_name_norm, oa_name)
        if name_score >= 0.85:
            return oa_id, name_score

    return None, 0


def _name_sim(a, b):
    """Simple token-overlap similarity (0–1)."""
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    return len(inter) / max(len(ta), len(tb))


def fetch_author_details(oa_id):
    """Fetch full OA author record; returns dict or None."""
    short_id = oa_id.split("/")[-1]
    data = oa_get(
        f"/authors/{short_id}",
        {"select": "id,display_name,orcid,summary_stats,topics"},
    )
    time.sleep(SLEEP)
    return data


def find_by_name(name, works_count_hint=None):
    """
    Fallback: search OA by display name.
    Returns (oa_author_id, confidence) or (None, 0).
    """
    data = oa_get(
        "/authors",
        {"filter": f"display_name.search:{name}", "select": "id,display_name,works_count", "per_page": 10},
    )
    time.sleep(SLEEP)
    if not data or not data.get("results"):
        return None, 0

    results = data["results"]
    name_norm = normalize_name(name)
    best_id, best_score = None, 0.0

    for r in results:
        oa_name = normalize_name(r.get("display_name", ""))
        sim = _name_sim(name_norm, oa_name)
        wc = r.get("works_count", 0)
        # Boost: if works_count roughly matches our known papers (within 10×)
        wc_boost = 0.0
        if works_count_hint and works_count_hint > 0 and wc > 0:
            ratio = max(works_count_hint, wc) / max(1, min(works_count_hint, wc))
            if ratio < 5:
                wc_boost = 0.05
        score = sim + wc_boost
        if score > best_score:
            best_score = score
            best_id = r["id"]

    if not results:
        return None, 0
    top = results[0]
    top_name = normalize_name(top.get("display_name", ""))
    top_sim = _name_sim(name_norm, top_name)

    # Single result with high name similarity → accept
    if len(results) == 1 and top_sim >= 0.85:
        return top["id"], top_sim

    # Multiple results: accept only if top result has exact name match AND
    # clearly dominates the next (3× more works)
    if len(results) >= 2 and top_sim >= 0.9:
        second = results[1]
        ratio = top.get("works_count", 1) / max(1, second.get("works_count", 0))
        if ratio >= 3:
            return top["id"], top_sim

    return None, 0


# ── build PID → paper list ───────────────────────────────────────────────────

def build_pid_papers():
    """Returns {dblp_pid: [paper_dict, ...]} with DOIs from ee field."""
    pid_papers = defaultdict(list)
    for fname in os.listdir(RESULTS_DIR):
        if not fname.endswith(".json") or fname == "all_authors.json":
            continue
        raw = json.load(open(os.path.join(RESULTS_DIR, fname), encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        for paper in raw.values():
            if not isinstance(paper, dict):
                continue
            doi = extract_doi(paper)
            if not doi:
                continue
            for author in paper.get("authors", []):
                if isinstance(author, list) and len(author) >= 2:
                    pid = author[1]
                    pid_papers[pid].append({"doi": doi, "name": author[0]})
    return pid_papers


# ── main ─────────────────────────────────────────────────────────────────────

def load_profile(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_profile(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def format_topics(topics_raw):
    """Keep top MAX_TOPICS, store as compact list."""
    out = []
    for t in (topics_raw or [])[:MAX_TOPICS]:
        out.append({
            "id":       t["id"].split("/")[-1],
            "name":     t["display_name"],
            "count":    t.get("count", 0),
            "subfield": {
                "id":   t["subfield"]["id"].split("/")[-1],
                "name": t["subfield"]["display_name"],
            },
            "field": {
                "id":   t["field"]["id"].split("/")[-1],
                "name": t["field"]["display_name"],
            },
        })
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N authors")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if already has openalex_id")
    args = parser.parse_args()

    print("Building PID → papers index …")
    pid_papers = build_pid_papers()
    print(f"  {len(pid_papers)} PIDs with DOI-bearing papers")

    profiles = sorted(
        f for f in os.listdir(PROFILES_DIR)
        if f.endswith(".json") and not f.startswith("_")
    )

    stats = {"found_doi": 0, "found_name": 0, "skipped": 0, "failed": 0, "already": 0}
    done = 0

    for fname in profiles:
        path = os.path.join(PROFILES_DIR, fname)
        profile = load_profile(path)

        if profile.get("openalex_id") and not args.force:
            stats["already"] += 1
            continue

        name = profile.get("name", "")
        slug = profile.get("slug", fname[:-5])
        dblp_url = profile.get("dblp_url", "")
        dblp_pid = ""
        m = re.search(r"dblp\.org/pid/(.+?)(?:\.html)?$", dblp_url)
        if m:
            dblp_pid = m.group(1)

        name_norm = normalize_name(name)
        papers = pid_papers.get(dblp_pid, [])

        oa_id = None
        confidence = 0.0
        method = "?"

        # --- Strategy 1: DOI lookup ---
        tried_dois = set()
        for p in papers[:20]:
            doi = p["doi"]
            if doi in tried_dois:
                continue
            tried_dois.add(doi)
            oa_id, confidence = find_by_doi(doi, name_norm, dblp_pid)
            if oa_id:
                method = "doi"
                break

        # --- Strategy 2: name fallback ---
        if not oa_id:
            works_hint = profile.get("core_astar", 0) or 0
            oa_id, confidence = find_by_name(name, works_hint)
            if oa_id:
                method = "name"

        if not oa_id:
            print(f"  FAIL  {name} ({slug})")
            stats["failed"] += 1
            done += 1
            if args.limit and done >= args.limit:
                break
            continue

        # --- Fetch full author record ---
        author_data = fetch_author_details(oa_id)
        if not author_data:
            print(f"  FAIL (fetch) {name}")
            stats["failed"] += 1
            done += 1
            if args.limit and done >= args.limit:
                break
            continue

        short_id = oa_id.split("/")[-1]
        orcid_url = author_data.get("orcid") or ""
        orcid = re.sub(r"^https?://orcid\.org/", "", orcid_url) if orcid_url else ""
        h_index = (author_data.get("summary_stats") or {}).get("h_index")
        topics = format_topics(author_data.get("topics", []))

        print(
            f"  {'DRY ' if args.dry_run else ''}OK [{method}] {name} → {short_id}"
            + (f" ORCID:{orcid}" if orcid else "")
            + f" h={h_index} topics={len(topics)}"
            + f" conf={confidence:.2f}"
        )

        if not args.dry_run:
            profile["openalex_id"] = short_id
            if orcid:
                profile["orcid"] = orcid
            if h_index is not None:
                profile["openalex_h_index"] = h_index
            if topics:
                profile["openalex_topics"] = topics
            save_profile(path, profile)

        if method == "doi":
            stats["found_doi"] += 1
        else:
            stats["found_name"] += 1

        done += 1
        if args.limit and done >= args.limit:
            break

    print()
    print("Summary:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
