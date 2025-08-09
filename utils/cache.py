# utils/cache.py
# simple disk cache for pokemon + related resources with safe writes and retries

import os
import json
import tempfile
from datetime import datetime
import shutil
from glob import glob

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import log_action

# --- paths & flags ---
CACHE_FILE = "data/pokemon_cache.json"
EXTRA_CACHE_FILE = "data/extra_cache.json"
REQUIRED_EXTRA_KEYS = ["species", "evolution", "type", "generation", "species_default"]
ENABLE_VERBOSE_LOGGING = False

# ensure data dir exists
if not os.path.exists("data"):
    os.makedirs("data")

# --- shared http session (retries + timeout) ---
_session = requests.Session()
_retry = Retry(total=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504))
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

def _json_fetch(url: str, timeout: float = 10.0):
    """get json with retry + timeout"""
    r = _session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()

def _atomic_write(path: str, obj: dict):
    """atomically write json (utf-8) to avoid corrupt files on windows"""
    d = os.path.dirname(path) or "."
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=d, delete=False, encoding="utf-8", newline="\n") as tmp:
            json.dump(obj, tmp, separators=(",", ":"), ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, path)
    except Exception as e:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise e

# --- load caches (robust to corruption) ---
try:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            pokemon_cache = json.load(f)
    else:
        pokemon_cache = {}
except Exception as e:
    log_action(f"ERROR loading cache: {e}")
    try:
        bad = f"{CACHE_FILE}.corrupt.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.replace(CACHE_FILE, bad)
        log_action(f"backed up corrupt cache to {bad}")
    except Exception:
        pass
    pokemon_cache = {}

try:
    if os.path.exists(EXTRA_CACHE_FILE):
        with open(EXTRA_CACHE_FILE, "r", encoding="utf-8") as f:
            extra_cache = json.load(f)
    else:
        extra_cache = {}
except Exception as e:
    log_action(f"ERROR loading extra cache: {e}")
    try:
        bad = f"{EXTRA_CACHE_FILE}.corrupt.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.replace(EXTRA_CACHE_FILE, bad)
        log_action(f"backed up corrupt extra cache to {bad}")
    except Exception:
        pass
    extra_cache = {}

# ensure required sections exist
for key in REQUIRED_EXTRA_KEYS:
    extra_cache.setdefault(key, {})

# ensure json files exist on disk
try:
    if not os.path.exists(CACHE_FILE):
        _atomic_write(CACHE_FILE, pokemon_cache)
    if not os.path.exists(EXTRA_CACHE_FILE):
        _atomic_write(EXTRA_CACHE_FILE, extra_cache)
except Exception as e:
    log_action(f"ERROR creating initial cache files: {e}")

# remove stale tmp files (from interrupted writes)
try:
    for p in glob(os.path.join("data", "tmp*")):
        os.remove(p)
        log_action(f"removed stale temp file: {p}")
except Exception:
    pass

# --- public api ---

def set_verbose(on: bool):
    """enable/disable verbose cache logs"""
    global ENABLE_VERBOSE_LOGGING
    ENABLE_VERBOSE_LOGGING = bool(on)

def get_pokemon_cached(name, get_pokemon_fn):
    """cache for pokemon endpoint; preserves existing schema"""
    name = str(name).lower()
    if name in pokemon_cache:
        if ENABLE_VERBOSE_LOGGING:
            log_action(f"CACHE HIT: {name}")
        return pokemon_cache[name]
    log_action(f"CACHE MISS: {name} - Fetching from API")
    data = get_pokemon_fn(name)
    if data:
        pokemon_cache[name] = data
        save_cache()
    return data

def get_species_cached(name, autosave: bool = True):
    """cache for species data"""
    name = str(name).lower()
    if name in extra_cache["species"]:
        if ENABLE_VERBOSE_LOGGING:
            log_action(f"CACHE HIT: species {name}")
        return extra_cache["species"][name]
    from utils.pokeapi import get_species
    data = get_species(name)
    if data:
        extra_cache["species"][name] = data
        if autosave:
            save_extra_cache()
    return data


def get_evolution_chain_cached(species_data):
    """cache for evolution chains keyed by chain url"""
    url = species_data["evolution_chain"]["url"]
    if url in extra_cache["evolution"]:
        if ENABLE_VERBOSE_LOGGING:
            log_action(f"CACHE HIT: evolution {url}")
        return extra_cache["evolution"][url]
    from utils.pokeapi import get_evolution_chain
    data = get_evolution_chain(species_data)
    if data:
        extra_cache["evolution"][url] = data
        save_extra_cache()
    return data

def get_generation_cached(gen_id):
    """cache for generation metadata; stores trimmed payload"""
    key = str(gen_id)
    if key in extra_cache["generation"]:
        if ENABLE_VERBOSE_LOGGING:
            log_action(f"CACHE HIT: generation {key}")
        return extra_cache["generation"][key]
    try:
        data = _json_fetch(f"https://pokeapi.co/api/v2/generation/{gen_id}/")
        cleaned = {
            "id": data.get("id"),
            "name": data.get("name"),
            "pokemon_species": data.get("pokemon_species", []),
        }
        extra_cache["generation"][key] = cleaned
        save_extra_cache()
        return cleaned
    except Exception as e:
        log_action(f"ERROR fetching generation {key}: {e}")
        return None

def get_type_cached(type_name):
    """cache for type damage relations; stores only what's needed"""
    type_name = str(type_name).lower()
    if type_name in extra_cache["type"]:
        if ENABLE_VERBOSE_LOGGING:
            log_action(f"CACHE HIT: type {type_name}")
        return extra_cache["type"][type_name]
    try:
        data = _json_fetch(f"https://pokeapi.co/api/v2/type/{type_name}")
        cleaned = {
            "name": data.get("name", type_name),
            "damage_relations": data.get("damage_relations", {})
        }
        extra_cache["type"][type_name] = cleaned
        save_extra_cache()
        return cleaned
    except Exception as e:
        log_action(f"ERROR fetching type {type_name}: {e}")
        return None

def get_default_variety_cached(species_name: str) -> str:
    """map species -> default pokemon name (single lookup, no disk write)"""
    m = extra_cache.setdefault("species_default", {})
    key = str(species_name).lower()
    if key in m:
        return m[key]
    sp = get_species_cached(key, autosave=False) or {}
    name = key
    try:
        for v in sp.get("varieties", []):
            if v.get("is_default") and v.get("pokemon", {}).get("name"):
                name = v["pokemon"]["name"]
                break
    except Exception:
        pass
    m[key] = name
    return name

def bulk_prime_default_varieties(species_names):
    """batch-resolve species -> default pokemon; single save + single log"""
    m = extra_cache.setdefault("species_default", {})
    added = 0
    out = []
    for s in species_names:
        key = str(s).lower()
        if key in m:
            out.append(m[key]); continue
        sp = get_species_cached(key, autosave=False) or {}
        name = key
        try:
            for v in sp.get("varieties", []):
                if v.get("is_default") and v.get("pokemon", {}).get("name"):
                    name = v["pokemon"]["name"]; break
        except Exception:
            pass
        m[key] = name
        out.append(name)
        added += 1
    if added:
        save_extra_cache()
        log_action(f"bulk default varieties: +{added}, total={len(m)}")
    return out

def save_cache():
    """persist pokemon_cache atomically"""
    try:
        _atomic_write(CACHE_FILE, pokemon_cache)
        log_action("Cache saved to disk")
    except Exception as e:
        log_action(f"ERROR saving cache: {e}")

def save_extra_cache():
    """persist extra_cache atomically"""
    try:
        _atomic_write(EXTRA_CACHE_FILE, extra_cache)
        log_action("extra_cache.json saved")
    except Exception as e:
        log_action(f"ERROR saving extra_cache: {e}")

def refresh_cache():
    """clear pokemon cache file + memory"""
    global pokemon_cache
    pokemon_cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing cache file: {e}")
    log_action("Cache manually refreshed")

def backup_cache():
    """write a timestamped backup of pokemon_cache"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"data/pokemon_cache_backup_{timestamp}.json"
    try:
        _atomic_write(backup_path, pokemon_cache)
        log_action(f"Backup created: {backup_path}")
    except Exception as e:
        log_action(f"ERROR creating backup: {e}")

def recover_cache():
    """restore pokemon_cache.json from most recent backup (byte-for-byte)"""
    backups = sorted(glob("data/pokemon_cache_backup_*.json"), reverse=True)
    if not backups:
        log_action("Recover failed: no Pokémon cache backups found")
        return False
    src = backups[0]
    try:
        shutil.copyfile(src, CACHE_FILE)
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            recovered = json.load(f)
        global pokemon_cache
        pokemon_cache = recovered
        save_cache() # will reduce file size
        log_action(f"Recovered Pokémon cache from: {src} (size={os.path.getsize(src)} bytes)")
        return True
    except Exception as e:
        log_action(f"ERROR recovering Pokémon cache from {src}: {e}")
        return False

def backup_extra_cache():
    """write a timestamped backup of extra_cache"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"data/extra_cache_backup_{timestamp}.json"
    try:
        _atomic_write(backup_path, extra_cache)
        log_action(f"Extra cache backup created: {backup_path}")
    except Exception as e:
        log_action(f"ERROR creating extra cache backup: {e}")

def refresh_extra_cache():
    """clear extra cache (all sections)"""
    global extra_cache
    extra_cache = {k: {} for k in REQUIRED_EXTRA_KEYS}
    if os.path.exists(EXTRA_CACHE_FILE):
        try:
            os.remove(EXTRA_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing extra cache file: {e}")
    log_action("Extra cache manually refreshed")

def recover_extra_cache():
    """restore extra_cache.json from most recent backup (byte-for-byte)"""
    backups = sorted(glob("data/extra_cache_backup_*.json"), reverse=True)
    if not backups:
        log_action("Recover failed: no extra cache backups found")
        return False
    src = backups[0]
    try:
        shutil.copyfile(src, EXTRA_CACHE_FILE)
        with open(EXTRA_CACHE_FILE, "r", encoding="utf-8") as f:
            recovered = json.load(f)
        for k in REQUIRED_EXTRA_KEYS:
            recovered.setdefault(k, {})
        global extra_cache
        extra_cache = recovered
        save_extra_cache()  # keep normalized
        log_action(f"Recovered extra cache from: {src} (size={os.path.getsize(src)} bytes)")
        return True
    except Exception as e:
        log_action(f"ERROR recovering extra cache from {src}: {e}")
        return False

