import os
import json
from functools import lru_cache

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

_json_cache = {}


def _resolve_path(path: str) -> str:
    # If path is absolute, return as is
    if os.path.isabs(path):
        return path
    # Try results/ first
    candidate = os.path.join(RESULTS_DIR, path)
    if os.path.exists(candidate):
        return candidate
    # else try relative to repo root
    candidate = os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
    return candidate


def load_json(path: str):
    """Load JSON file with caching. Path can be a filename or relative path.
    Prefers files under results/.
    """
    resolved = _resolve_path(path)
    if resolved in _json_cache:
        return _json_cache[resolved]
    try:
        with open(resolved, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _json_cache[resolved] = data
            return data
    except FileNotFoundError:
        return None


def save_json(path: str, data):
    """Save JSON file into results/ directory and update cache."""
    # Always write into RESULTS_DIR to centralize outputs
    out_path = os.path.join(RESULTS_DIR, os.path.basename(path))
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _json_cache[out_path] = data
    return out_path


def load_text(path: str):
    resolved = _resolve_path(path)
    try:
        with open(resolved, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None


def save_text(path: str, text: str):
    out_path = os.path.join(RESULTS_DIR, os.path.basename(path))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return out_path
