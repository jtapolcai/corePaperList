"""
Download and parse the DBLP XML dump to refresh author publication caches.

Usage:
    python -m src.update_from_dump [--force]

Logic:
    1. HEAD the dump URL → read Last-Modified.
    2. Compare with .dblp_dump_timestamp (stored after last successful run).
    3. If not newer and not --force → exit 0 with "already up to date".
    4. Download the gzipped dump (streaming, no full-RAM load).
    5. SAX-parse it; for each <inproceedings>/<article> record:
         - match authors by @pid (exact) when present,
         - otherwise fall back to normalised name matching.
    6. Write per-author JSON files to dblp/ (same format as dblp_utils).
    7. Save the new timestamp.

Error estimation (name-only fallback):
    - Unique names → 0% false positives.
    - Homonym names (suffix "0001" in CSV) → possible false positives;
      these are flagged in the log.
"""

import csv
import gzip
import html.entities
import json
import os
import re
import sys
import time
import unicodedata
import xml.sax
import xml.sax.handler
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import urlopen, Request

# Pre-build a bytes→bytes entity substitution map for all standard HTML entities.
# DBLP's DTD uses these (e.g. &aacute; &ouml; &Lbr; …).  We replace them with
# their UTF-8 byte sequences BEFORE feeding chunks to the SAX parser, so the
# parser never sees undefined entities.
_ENTITY_RE = re.compile(rb"&([A-Za-z][A-Za-z0-9]*);")
# The 5 predefined XML entities must be left untouched — the SAX parser
# handles them natively, and replacing &amp; → & produces invalid XML.
_XML_PREDEFINED = {b"amp", b"lt", b"gt", b"apos", b"quot"}
_ENTITY_MAP: dict[bytes, bytes] = {
    name.encode(): chr(cp).encode("utf-8")
    for name, cp in html.entities.name2codepoint.items()
    if name.encode() not in _XML_PREDEFINED
}

def _replace_html_entities(chunk: bytes) -> bytes:
    # XML predefined entities: leave as-is.
    # Known HTML entity → UTF-8 Unicode.
    # Unknown DBLP-specific entity → empty bytes (never leave &foo; in output).
    return _ENTITY_RE.sub(
        lambda m: m.group(0) if m.group(1) in _XML_PREDEFINED
                  else _ENTITY_MAP.get(m.group(1), b""),
        chunk
    )

DUMP_URL = "https://dblp.uni-trier.de/xml/dblp.xml.gz"
TIMESTAMP_FILE = Path(__file__).resolve().parent.parent / ".dblp_dump_timestamp"
DUMP_CACHE    = Path(__file__).resolve().parent.parent / ".dblp_dump_cache.xml.gz"
DBLP_DIR = Path(__file__).resolve().parent.parent / "dblp"
AUTHORS_CSV = Path(__file__).resolve().parent.parent / "authors_data.csv"
LOG_FILE = Path(__file__).resolve().parent.parent / "results" / "log_dump_update.txt"

PUBLICATION_TYPES = {"inproceedings", "article"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalise(name: str) -> str:
    """Lower-case, strip diacritics, remove disambiguation suffixes (0001 …)."""
    name = re.sub(r"\s+\d{4}$", "", name.strip())
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_name.lower().strip()


def pid_from_url(url: str) -> str:
    """Extract '62/567' from 'https://dblp.org/pid/62/567'."""
    m = re.search(r"/pid/(.+?)(?:\.html)?$", url.strip())
    return m.group(1) if m else ""


def load_authors(csv_path: Path):
    """Return two dicts: pid→name  and  normalised_name→name."""
    pid_map = {}   # '62/567' → canonical name
    name_map = {}  # normalised → canonical name  (for fallback)
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("Author", "").strip()
            url  = row.get("DBLP URL", "").strip()
            if not name:
                continue
            pid = pid_from_url(url)
            if pid:
                pid_map[pid] = name
            name_map[normalise(name)] = name
    return pid_map, name_map


# ---------------------------------------------------------------------------
# Freshness check
# ---------------------------------------------------------------------------

def fetch_last_modified() -> datetime | None:
    try:
        req = Request(DUMP_URL, method="HEAD")
        req.add_header("User-Agent", "NKFIH-author-tool/1.0 (mailto:tapolcai@tmit.bme.hu)")
        with urlopen(req, timeout=20) as resp:
            lm = resp.headers.get("Last-Modified", "")
            return parsedate_to_datetime(lm) if lm else None
    except Exception as e:
        print(f"[WARN] HEAD request failed: {e}")
        return None


def load_stored_timestamp() -> datetime | None:
    if TIMESTAMP_FILE.exists():
        try:
            ts = TIMESTAMP_FILE.read_text().strip()
            return datetime.fromisoformat(ts)
        except Exception:
            pass
    return None


def save_timestamp(dt: datetime):
    TIMESTAMP_FILE.write_text(dt.isoformat())


# ---------------------------------------------------------------------------
# SAX handler
# ---------------------------------------------------------------------------

class DblpHandler(xml.sax.handler.ContentHandler):
    def __init__(self, pid_map: dict, name_map: dict):
        self.pid_map   = pid_map   # pid  → canonical_name
        self.name_map  = name_map  # norm → canonical_name
        # accumulated per author: canonical_name → list of record dicts
        self.records: dict[str, list] = {n: [] for n in pid_map.values()}
        for n in name_map.values():
            self.records.setdefault(n, [])

        self._in_pub   = False
        self._pub_type = None
        self._current  = {}        # fields of the current record
        self._authors  = []        # (pid_or_None, name) pairs
        self._field    = None      # which text field we're collecting
        self._buf      = []        # character buffer

        self.stats = {"pid_matched": 0, "name_matched": 0, "ambiguous": 0, "processed": 0}

    def startElement(self, tag, attrs):
        if tag in PUBLICATION_TYPES:
            self._in_pub   = True
            self._pub_type = tag
            self._current  = {"type": tag, "key": attrs.get("key", "")}
            self._authors  = []
            self._field    = None
            self._buf      = []
            return

        if not self._in_pub:
            return

        if tag == "author":
            self._field = "author"
            self._buf   = []
            self._current_author_pid = attrs.get("pid", "")
        elif tag in ("title", "year", "booktitle", "journal", "pages", "doi", "ee", "url", "volume", "number"):
            self._field = tag
            self._buf   = []

    def characters(self, content):
        if self._in_pub and self._field:
            self._buf.append(content)

    def endElement(self, tag):
        if not self._in_pub:
            return

        if tag == "author":
            raw_name = "".join(self._buf).strip()
            self._authors.append((self._current_author_pid, raw_name))
            self._field = None
            self._buf   = []
            return

        if tag in ("title", "year", "booktitle", "journal", "pages", "doi", "ee", "url", "volume", "number"):
            self._current[tag] = "".join(self._buf).strip()
            self._field = None
            self._buf   = []
            return

        if tag in PUBLICATION_TYPES:
            self._in_pub = False
            self._flush_record()

    def _flush_record(self):
        matched_names = set()

        for pid, raw_name in self._authors:
            # 1. PID match (exact)
            if pid and pid in self.pid_map:
                matched_names.add(self.pid_map[pid])
                self.stats["pid_matched"] += 1
                continue
            # 2. Name fallback
            norm = normalise(raw_name)
            if norm in self.name_map:
                matched_names.add(self.name_map[norm])
                self.stats["name_matched"] += 1

        if not matched_names:
            return

        record = dict(self._current)
        record["authors"] = [name for _, name in self._authors]
        self.stats["processed"] += 1

        for canonical in matched_names:
            self.records[canonical].append(record)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(force: bool = False):
    DBLP_DIR.mkdir(exist_ok=True)
    LOG_FILE.parent.mkdir(exist_ok=True)

    # --- freshness check ---
    remote_dt = fetch_last_modified()
    stored_dt = load_stored_timestamp()

    if remote_dt:
        print(f"Dump Last-Modified : {remote_dt.isoformat()}")
    if stored_dt:
        print(f"Last processed     : {stored_dt.isoformat()}")

    if not force and remote_dt and stored_dt and remote_dt <= stored_dt:
        print("Dump nem változott — nincs mit frissíteni.")
        return

    # --- load author list ---
    pid_map, name_map = load_authors(AUTHORS_CSV)
    print(f"Szerzők: {len(pid_map)} PID-del, {len(name_map)} névvel összesen")

    # --- download dump (skip if cached) ---
    if DUMP_CACHE.exists():
        print(f"Letöltött dump megvan: {DUMP_CACHE}")
    else:
        print(f"Letöltés: {DUMP_URL}  (~3.5 GB, egyszeri művelet)")
        req_dl = Request(DUMP_URL)
        req_dl.add_header("User-Agent", "NKFIH-author-tool/1.0 (mailto:tapolcai@tmit.bme.hu)")
        tmp = DUMP_CACHE.with_suffix(".tmp")
        with urlopen(req_dl, timeout=600) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            with open(tmp, "wb") as f:
                downloaded = 0
                bar_width = 40
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct  = downloaded / total
                        done = int(bar_width * pct)
                        bar  = "#" * done + "-" * (bar_width - done)
                        print(f"\r  [{bar}] {pct*100:5.1f}%  {downloaded/1e9:.2f}/{total/1e9:.2f} GB",
                              end="", flush=True)
                    else:
                        print(f"\r  {downloaded/1e9:.2f} GB", end="", flush=True)
        tmp.rename(DUMP_CACHE)
        print(f"\nLetöltve: {DUMP_CACHE}")

    # --- parse cached dump ---
    print("Parse...")
    handler = DblpHandler(pid_map, name_map)
    parser  = xml.sax.make_parser()
    parser.setContentHandler(handler)

    t0 = time.time()
    with gzip.open(DUMP_CACHE, "rb") as gz:
        buf_size = 1 << 20  # 1 MB chunks
        tail = b""
        while True:
            raw = gz.read(buf_size)
            if not raw:
                if tail:
                    parser.feed(_replace_html_entities(tail))
                break
            chunk = tail + raw
            tail  = chunk[-20:]
            chunk = chunk[:-20]
            parser.feed(_replace_html_entities(chunk))

    elapsed = time.time() - t0
    print(f"Feldolgozva {elapsed:.0f}s alatt.")
    print(f"  PID alapú egyezés : {handler.stats['pid_matched']}")
    print(f"  Név alapú egyezés : {handler.stats['name_matched']}")
    print(f"  Mentett rekord    : {handler.stats['processed']}")

    # --- save per-author cache ---
    saved = 0
    for canonical_name, pubs in handler.records.items():
        if not pubs:
            continue
        safe = re.sub(r"[^\w]", "_", normalise(canonical_name))
        out  = DBLP_DIR / f"{safe}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"dblpperson": {"r": pubs}}, f, indent=2, ensure_ascii=False)
        saved += 1

    print(f"Elmentve {saved} szerző cache-be → dblp/")

    # --- log ambiguous (name-only matched homonyms) ---
    log_lines = ["DBLP dump frissítés log", f"Dátum: {datetime.now(timezone.utc).isoformat()}", ""]
    if handler.stats["name_matched"] > 0:
        log_lines.append(f"FIGYELEM: {handler.stats['name_matched']} rekord névegyezéssel lett hozzárendelve (nem PID alapján).")
        log_lines.append("Ellenőrizd a 0001/0002 suffixű szerzőket!")
    LOG_FILE.write_text("\n".join(log_lines), encoding="utf-8")

    # --- save timestamp ---
    if remote_dt:
        save_timestamp(remote_dt)
    else:
        save_timestamp(datetime.now(timezone.utc))

    print("Kész.")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
