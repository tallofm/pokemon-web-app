# utils/cache.py
"""Advanced multi-tier disk and in-memory cache with debounced writes, payload pruning, and telemetry."""

import os
import json
import tempfile
import threading
import shutil
from datetime import datetime
from glob import glob

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import log_action
from utils.default_datasets import (
    DEFAULT_INITIAL_MEGA_STONES,
    DEFAULT_INITIAL_GMAX_MOVES,
    DEFAULT_INITIAL_MOVE_OVERRIDES,
)

# --------------------------------------------------------------------------- #
# Paths & locks
# --------------------------------------------------------------------------- #

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "pokemon_cache.json")
EXTRA_CACHE_FILE = os.path.join(DATA_DIR, "extra_cache.json")
MOVES_CACHE_FILE = os.path.join(DATA_DIR, "moves_cache.json")
ABILITIES_CACHE_FILE = os.path.join(DATA_DIR, "abilities_cache.json")
ITEMS_CACHE_FILE = os.path.join(DATA_DIR, "items_cache.json")
MEGA_STONES_CACHE_FILE = os.path.join(DATA_DIR, "mega_stones_cache.json")
GMAX_MOVES_CACHE_FILE = os.path.join(DATA_DIR, "gmax_moves_cache.json")
MOVE_OVERRIDES_CACHE_FILE = os.path.join(DATA_DIR, "move_overrides_cache.json")

REQUIRED_EXTRA_KEYS = [
    "species", "evolution", "type", "generation",
    "species_default", "forms", "ability"
]

LISTS_KEY = "lists"
ENABLE_VERBOSE_LOGGING = False

_pokemon_cache_lock = threading.RLock()
_extra_cache_lock = threading.RLock()
_moves_cache_lock = threading.RLock()
_abilities_cache_lock = threading.RLock()
_items_cache_lock = threading.RLock()
_mega_stones_cache_lock = threading.RLock()
_gmax_moves_cache_lock = threading.RLock()
_move_overrides_cache_lock = threading.RLock()
_timers_lock = threading.RLock()

# Background debounced timer tracking
_save_timers = {}

# Cache Telemetry
_stats = {
    "pokemon_hits": 0,
    "pokemon_misses": 0,
    "extra_hits": 0,
    "extra_misses": 0,
    "moves_hits": 0,
    "moves_misses": 0,
    "abilities_hits": 0,
    "abilities_misses": 0,
    "items_hits": 0,
    "items_misses": 0,
}

os.makedirs(DATA_DIR, exist_ok=True)

# --------------------------------------------------------------------------- #
# Shared HTTP session (retries + timeout)
# --------------------------------------------------------------------------- #

_session = requests.Session()
_retry = Retry(total=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504))
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _json_fetch(url: str, timeout: float = 10.0):
    r = _session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _atomic_write(path: str, obj: dict):
    """Atomically write JSON to avoid corrupted or partially written files."""
    d = os.path.dirname(path) or "."
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=d, delete=False, encoding="utf-8", newline="\n") as tmp:
            json.dump(obj, tmp, separators=(",", ":"), ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _schedule_debounced_save(func, delay: float = 2.0):
    """Debounce saving to disk so rapid sequential reads/writes only write once."""
    with _timers_lock:
        func_id = func.__name__
        if func_id in _save_timers:
            _save_timers[func_id].cancel()
        t = threading.Timer(delay, func)
        t.daemon = True
        _save_timers[func_id] = t
        t.start()


def _prune_pokemon_data(p: dict) -> dict:
    """Trim memory bloat from PokéAPI responses before caching."""
    if not p or not isinstance(p, dict):
        return p

    sprites = p.get("sprites") or {}
    other = sprites.get("other") or {}
    pruned_sprites = {
        "front_default": sprites.get("front_default"),
        "front_shiny": sprites.get("front_shiny"),
        "other": {
            "official-artwork": {
                "front_default": (other.get("official-artwork") or {}).get("front_default"),
                "front_shiny": (other.get("official-artwork") or {}).get("front_shiny"),
            },
            "dream_world": {
                "front_default": (other.get("dream_world") or {}).get("front_default"),
            },
            "home": {
                "front_default": (other.get("home") or {}).get("front_default"),
            },
        },
    }

    # Only store latest version details for moves to save massive amounts of JSON size
    pruned_moves = []
    for m in p.get("moves", []):
        vg = m.get("version_group_details", [])
        latest_vg = [vg[-1]] if vg else []
        pruned_moves.append({
            "move": {"name": (m.get("move") or {}).get("name", "")},
            "version_group_details": latest_vg,
        })

    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "height": p.get("height"),
        "weight": p.get("weight"),
        "base_experience": p.get("base_experience"),
        "is_default": p.get("is_default", False),
        "species": {"name": (p.get("species") or {}).get("name", p.get("name"))},
        "types": p.get("types", []),
        "stats": p.get("stats", []),
        "sprites": pruned_sprites,
        "abilities": [
            {
                "ability": {"name": (a.get("ability") or {}).get("name", "")},
                "is_hidden": a.get("is_hidden", False),
            }
            for a in p.get("abilities", [])
        ],
        "moves": pruned_moves,
    }


def _load_cache_file(path: str, default: dict) -> dict:
    """Load JSON cache from disk with corrupt-file detection and backup."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_action(f"ERROR loading {path}: {e}")
        try:
            bad = f"{path}.corrupt.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.replace(path, bad)
            log_action(f"backed up corrupt cache to {bad}")
        except Exception:
            pass
        return default


# --------------------------------------------------------------------------- #
# Initial Cache Loading
# --------------------------------------------------------------------------- #

pokemon_cache = _load_cache_file(CACHE_FILE, {})
extra_cache = _load_cache_file(EXTRA_CACHE_FILE, {})
moves_cache = _load_cache_file(MOVES_CACHE_FILE, {})
abilities_cache = _load_cache_file(ABILITIES_CACHE_FILE, {})
items_cache = _load_cache_file(ITEMS_CACHE_FILE, {})
mega_stones_cache = _load_cache_file(MEGA_STONES_CACHE_FILE, {})
gmax_moves_cache = _load_cache_file(GMAX_MOVES_CACHE_FILE, {})
move_overrides_cache = _load_cache_file(MOVE_OVERRIDES_CACHE_FILE, {})

for key in REQUIRED_EXTRA_KEYS:
    extra_cache.setdefault(key, {})
extra_cache.setdefault(LISTS_KEY, {})

for filepath, data in [
    (CACHE_FILE, pokemon_cache),
    (EXTRA_CACHE_FILE, extra_cache),
    (MOVES_CACHE_FILE, moves_cache),
    (ABILITIES_CACHE_FILE, abilities_cache),
    (ITEMS_CACHE_FILE, items_cache),
    (MEGA_STONES_CACHE_FILE, mega_stones_cache),
    (GMAX_MOVES_CACHE_FILE, gmax_moves_cache),
    (MOVE_OVERRIDES_CACHE_FILE, move_overrides_cache),
]:
    try:
        if not os.path.exists(filepath):
            _atomic_write(filepath, data)
    except Exception as e:
        log_action(f"ERROR creating initial cache file {filepath}: {e}")

try:
    for p in glob(os.path.join(DATA_DIR, "tmp*")):
        os.remove(p)
        log_action(f"removed stale temp file: {p}")
except Exception:
    pass


# --------------------------------------------------------------------------- #
# Telemetry & Stats
# --------------------------------------------------------------------------- #

def get_cache_stats() -> dict:
    """Return live cache telemetry, counts, and hit rates for UI display."""
    with _pokemon_cache_lock:
        poke_count = len(pokemon_cache)
    with _extra_cache_lock:
        extra_count = sum(len(v) for v in extra_cache.values() if isinstance(v, dict))
    with _moves_cache_lock:
        moves_count = len(moves_cache)
    with _abilities_cache_lock:
        abilities_count = len(abilities_cache)
    with _items_cache_lock:
        items_count = len(items_cache)
    with _mega_stones_cache_lock:
        mega_stones_count = len(mega_stones_cache)
    with _gmax_moves_cache_lock:
        gmax_moves_count = len(gmax_moves_cache)

    total_hits = (
        _stats["pokemon_hits"]
        + _stats["extra_hits"]
        + _stats["moves_hits"]
        + _stats["abilities_hits"]
        + _stats["items_hits"]
    )
    total_misses = (
        _stats["pokemon_misses"]
        + _stats["extra_misses"]
        + _stats["moves_misses"]
        + _stats["abilities_misses"]
        + _stats["items_misses"]
    )
    total_reqs = total_hits + total_misses
    hit_rate = round((total_hits / total_reqs * 100), 1) if total_reqs > 0 else 100.0

    return {
        "pokemon_count": poke_count,
        "extra_count": extra_count,
        "moves_count": moves_count,
        "abilities_count": abilities_count,
        "items_count": items_count,
        "mega_stones_count": mega_stones_count,
        "gmax_moves_count": gmax_moves_count,
        "pokemon_hits": _stats["pokemon_hits"],
        "pokemon_misses": _stats["pokemon_misses"],
        "extra_hits": _stats["extra_hits"],
        "extra_misses": _stats["extra_misses"],
        "moves_hits": _stats["moves_hits"],
        "moves_misses": _stats["moves_misses"],
        "abilities_hits": _stats["abilities_hits"],
        "abilities_misses": _stats["abilities_misses"],
        "items_hits": _stats["items_hits"],
        "items_misses": _stats["items_misses"],
        "hits": total_hits,
        "misses": total_misses,
        "hit_rate": hit_rate,
        "logging_enabled": ENABLE_VERBOSE_LOGGING,
    }


# --------------------------------------------------------------------------- #
# Generic Backup & Recovery Helpers
# --------------------------------------------------------------------------- #

def _create_backup(name: str, cache_dict: dict, lock: threading.Lock) -> bool:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(DATA_DIR, f"{name}_backup_{timestamp}.json")
    try:
        with lock:
            snapshot = dict(cache_dict)
        _atomic_write(backup_path, snapshot)
        log_action(f"{name.capitalize()} backup created: {backup_path}")
        return True
    except Exception as e:
        log_action(f"ERROR creating {name} backup: {e}")
        return False


def _recover_backup(name: str, dest_file: str) -> tuple[bool, dict | None]:
    backups = sorted(glob(os.path.join(DATA_DIR, f"{name}_backup_*.json")), reverse=True)
    if not backups:
        log_action(f"Recover failed: no {name} backups found")
        return False, None
    src = backups[0]
    try:
        shutil.copyfile(src, dest_file)
        with open(dest_file, "r", encoding="utf-8") as f:
            recovered = json.load(f)
        log_action(f"Recovered {name} from: {src} (size={os.path.getsize(src)} bytes)")
        return True, recovered
    except Exception as e:
        log_action(f"ERROR recovering {name} from {src}: {e}")
        return False, None


# --------------------------------------------------------------------------- #
# Public API - Settings & Bulk Lists
# --------------------------------------------------------------------------- #

def set_verbose(on: bool) -> None:
    """Enable or disable verbose cache logging."""
    global ENABLE_VERBOSE_LOGGING
    ENABLE_VERBOSE_LOGGING = bool(on)


def get_all_pokemon_names_cached() -> list[str]:
    """Fetch and cache all Pokémon names."""
    with _extra_cache_lock:
        lists = extra_cache.setdefault(LISTS_KEY, {})
        key = "all_pokemon"
        if key in lists:
            _stats["extra_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action("CACHE HIT: all_pokemon list")
            return lists[key]

    _stats["extra_misses"] += 1
    try:
        data = _json_fetch("https://pokeapi.co/api/v2/pokemon?limit=10000&offset=0")
        names = [p.get("name") for p in (data or {}).get("results", []) if p.get("name")]
        with _extra_cache_lock:
            extra_cache.setdefault(LISTS_KEY, {})[key] = names
        save_extra_cache()
        log_action(f"Primed all_pokemon ({len(names)})")
        return names
    except Exception as e:
        log_action(f"ERROR fetching all_pokemon list: {e}")
        return []


def get_all_types_cached(exclude_special: bool = False) -> list[str]:
    """Fetch and cache all type names with a custom UX-friendly display order."""
    cache_key = "all_types_no_special" if exclude_special else "all_types"

    with _extra_cache_lock:
        lists = extra_cache.setdefault(LISTS_KEY, {})
        if cache_key in lists:
            _stats["extra_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: {cache_key}")
            return lists[cache_key]

    _stats["extra_misses"] += 1
    custom_order = [
        "grass", "fire", "water", "electric", "psychic", "dark", "fairy", "ice", "dragon",
        "normal", "flying", "fighting", "bug", "poison", "ground", "rock", "ghost", "steel",
        "stellar", "unknown",
    ]

    try:
        data = _json_fetch("https://pokeapi.co/api/v2/type")
        api_names = {t.get("name") for t in (data or {}).get("results", []) if t.get("name")}

        ordered = [t for t in custom_order if t in api_names]
        extras = sorted(api_names - set(custom_order))
        ordered.extend(extras)

        if exclude_special:
            ordered = [t for t in ordered if t not in ("stellar", "unknown")]

        with _extra_cache_lock:
            extra_cache.setdefault(LISTS_KEY, {})[cache_key] = ordered
        save_extra_cache()
        log_action(f"Primed {cache_key} ({len(ordered)})")
        return ordered
    except Exception as e:
        log_action(f"ERROR fetching type list: {e}")
        fallback = [t for t in custom_order if not (exclude_special and t in ("stellar", "unknown"))]
        return fallback


def refresh_lists(keys: list[str] | None = None) -> None:
    """Clear cached lists and persist."""
    with _extra_cache_lock:
        lists = extra_cache.setdefault(LISTS_KEY, {})
        if keys:
            for k in keys:
                lists.pop(k, None)
        else:
            lists.clear()
    save_extra_cache(sync=True)
    log_action(f"Refreshed lists: {keys or 'ALL'}")


# --------------------------------------------------------------------------- #
# Public API - Pokémon & Extra Data
# --------------------------------------------------------------------------- #

def get_ability_cached(name: str) -> dict:
    name = str(name).lower().strip()
    with _abilities_cache_lock:
        if name in abilities_cache and abilities_cache[name]:
            _stats["abilities_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: ability {name}")
            return abilities_cache[name]

    _stats["abilities_misses"] += 1
    log_action(f"CACHE MISS: ability {name} - Fetching from API")
    from utils.pokeapi import get_ability
    data = get_ability(name)
    if data and isinstance(data, dict) and data.get("name"):
        with _abilities_cache_lock:
            abilities_cache[name] = data
        save_abilities_cache()
    return data or {}


def get_form_cached(name: str) -> dict:
    name = str(name).lower().strip()
    with _extra_cache_lock:
        forms_cache = extra_cache.setdefault("forms", {})
        if name in forms_cache:
            _stats["extra_hits"] += 1
            return forms_cache[name]

    _stats["extra_misses"] += 1
    from utils.pokeapi import get_form
    data = get_form(name) or {}
    with _extra_cache_lock:
        extra_cache.setdefault("forms", {})[name] = data
    save_extra_cache()
    return data


def get_pokemon_cached(name, get_pokemon_fn):
    name = str(name).lower().strip()
    with _pokemon_cache_lock:
        if name in pokemon_cache:
            _stats["pokemon_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: {name}")
            return pokemon_cache[name]

    _stats["pokemon_misses"] += 1
    log_action(f"CACHE MISS: {name} - Fetching from API")
    data = get_pokemon_fn(name)
    if data:
        pruned = _prune_pokemon_data(data)
        with _pokemon_cache_lock:
            pokemon_cache[name] = pruned
        save_cache()  # Uses debounced background save
        return pruned
    return data


def get_species_cached(name, autosave: bool = True) -> dict:
    name = str(name).lower().strip()
    with _extra_cache_lock:
        species_dict = extra_cache.setdefault("species", {})
        if name in species_dict:
            _stats["extra_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: species {name}")
            return species_dict[name]

    _stats["extra_misses"] += 1
    from utils.pokeapi import get_species
    data = get_species(name)
    if data:
        with _extra_cache_lock:
            extra_cache.setdefault("species", {})[name] = data
        if autosave:
            save_extra_cache()
    return data


def get_evolution_chain_cached(species_data: dict) -> list[str]:
    url = (species_data or {}).get("evolution_chain", {}).get("url")
    if not url:
        return []

    with _extra_cache_lock:
        evo_dict = extra_cache.setdefault("evolution", {})
        if url in evo_dict:
            _stats["extra_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: evolution {url}")
            return evo_dict[url]

    _stats["extra_misses"] += 1
    from utils.pokeapi import get_evolution_chain
    data = get_evolution_chain(species_data)
    if data:
        with _extra_cache_lock:
            extra_cache.setdefault("evolution", {})[url] = data
        save_extra_cache()
    return data


def get_generation_cached(gen_id) -> dict | None:
    key = str(gen_id).strip()
    with _extra_cache_lock:
        gen_dict = extra_cache.setdefault("generation", {})
        if key in gen_dict:
            _stats["extra_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: generation {key}")
            return gen_dict[key]

    _stats["extra_misses"] += 1
    try:
        data = _json_fetch(f"https://pokeapi.co/api/v2/generation/{gen_id}/")
        cleaned = {
            "id": data.get("id"),
            "name": data.get("name"),
            "pokemon_species": data.get("pokemon_species", []),
        }
        with _extra_cache_lock:
            extra_cache.setdefault("generation", {})[key] = cleaned
        save_extra_cache()
        return cleaned
    except Exception as e:
        log_action(f"ERROR fetching generation {key}: {e}")
        return None


def get_type_cached(type_name: str) -> dict | None:
    type_name = str(type_name).lower().strip()
    with _extra_cache_lock:
        m = extra_cache.setdefault("type", {})
        if type_name in m:
            entry = m[type_name]
            if "pokemon" in entry:
                _stats["extra_hits"] += 1
                if ENABLE_VERBOSE_LOGGING:
                    log_action(f"CACHE HIT: type {type_name}")
                return entry

    _stats["extra_misses"] += 1
    try:
        data = _json_fetch(f"https://pokeapi.co/api/v2/type/{type_name}")
        cleaned = {
            "name": data.get("name", type_name),
            "damage_relations": data.get("damage_relations", {}),
            "pokemon": data.get("pokemon", []),
        }
        with _extra_cache_lock:
            extra_cache.setdefault("type", {})[type_name] = cleaned
        save_extra_cache()
        return cleaned
    except Exception as e:
        log_action(f"ERROR fetching type {type_name}: {e}")
        return None


def get_default_variety_cached(species_name: str) -> str:
    key = str(species_name).lower().strip()
    with _extra_cache_lock:
        m = extra_cache.setdefault("species_default", {})
        if key in m:
            return m[key]

    sp = get_species_cached(key, autosave=False) or {}
    name = key
    for v in sp.get("varieties", []):
        if v.get("is_default") and v.get("pokemon", {}).get("name"):
            name = v["pokemon"]["name"]
            break

    with _extra_cache_lock:
        extra_cache.setdefault("species_default", {})[key] = name
    return name


def bulk_prime_default_varieties(species_names: list[str]) -> list[str]:
    added = 0
    out = []
    for s in species_names:
        key = str(s).lower().strip()
        with _extra_cache_lock:
            m = extra_cache.setdefault("species_default", {})
            if key in m:
                out.append(m[key])
                continue

        sp = get_species_cached(key, autosave=False) or {}
        name = key
        for v in sp.get("varieties", []):
            if v.get("is_default") and v.get("pokemon", {}).get("name"):
                name = v["pokemon"]["name"]
                break
        with _extra_cache_lock:
            extra_cache.setdefault("species_default", {})[key] = name
        out.append(name)
        added += 1

    if added:
        save_extra_cache()
        log_action(f"bulk default varieties: +{added}, total={len(extra_cache.get('species_default', {}))}")
    return out


# --------------------------------------------------------------------------- #
# Public API - Save / Backup / Refresh
# --------------------------------------------------------------------------- #

def _perform_save_cache() -> None:
    try:
        with _pokemon_cache_lock:
            snapshot = dict(pokemon_cache)
        _atomic_write(CACHE_FILE, snapshot)
        log_action("pokemon_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving cache: {e}")


def save_cache(sync: bool = False) -> None:
    """Save Pokémon cache. If sync is False, debounces to a non-blocking background save."""
    if sync:
        _perform_save_cache()
    else:
        _schedule_debounced_save(_perform_save_cache, delay=1.5)


def _perform_save_extra_cache() -> None:
    try:
        with _extra_cache_lock:
            snapshot = {k: dict(v) if isinstance(v, dict) else list(v) for k, v in extra_cache.items()}
        _atomic_write(EXTRA_CACHE_FILE, snapshot)
        log_action("extra_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving extra_cache: {e}")


def save_extra_cache(sync: bool = False) -> None:
    """Save extra cache. If sync is False, debounces to background save."""
    if sync:
        _perform_save_extra_cache()
    else:
        _schedule_debounced_save(_perform_save_extra_cache, delay=1.5)


def refresh_cache() -> None:
    """Clear Pokémon cache file and in-memory cache."""
    global pokemon_cache
    with _pokemon_cache_lock:
        pokemon_cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing cache file: {e}")
    log_action("Cache manually refreshed")


def backup_cache() -> bool:
    save_cache(sync=True)
    return _create_backup("pokemon_cache", pokemon_cache, _pokemon_cache_lock)


def recover_cache() -> bool:
    ok, recovered = _recover_backup("pokemon_cache", CACHE_FILE)
    if ok and recovered is not None:
        global pokemon_cache
        with _pokemon_cache_lock:
            pokemon_cache = recovered
        save_cache(sync=True)
        return True
    return False


def backup_extra_cache() -> bool:
    save_extra_cache(sync=True)
    return _create_backup("extra_cache", extra_cache, _extra_cache_lock)


def refresh_extra_cache() -> None:
    """Clear extra cache, restoring required section keys."""
    global extra_cache
    with _extra_cache_lock:
        extra_cache = {k: {} for k in REQUIRED_EXTRA_KEYS}
        extra_cache[LISTS_KEY] = {}
    if os.path.exists(EXTRA_CACHE_FILE):
        try:
            os.remove(EXTRA_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing extra cache file: {e}")
    save_extra_cache(sync=True)
    log_action("Extra cache manually refreshed")


def recover_extra_cache() -> bool:
    ok, recovered = _recover_backup("extra_cache", EXTRA_CACHE_FILE)
    if ok and recovered is not None:
        for k in REQUIRED_EXTRA_KEYS:
            recovered.setdefault(k, {})
        recovered.setdefault(LISTS_KEY, {})
        global extra_cache
        with _extra_cache_lock:
            extra_cache = recovered
        save_extra_cache(sync=True)
        return True
    return False


# --------------------------------------------------------------------------- #
# Public API - Moves Cache Subsystem
# --------------------------------------------------------------------------- #

def _perform_save_moves_cache() -> None:
    try:
        with _moves_cache_lock:
            snapshot = dict(moves_cache)
        _atomic_write(MOVES_CACHE_FILE, snapshot)
        log_action("moves_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving moves_cache: {e}")


def save_moves_cache(sync: bool = False) -> None:
    if sync:
        _perform_save_moves_cache()
    else:
        _schedule_debounced_save(_perform_save_moves_cache, delay=1.5)


def get_move_cached(name: str) -> dict | None:
    name = str(name).lower().strip()
    with _moves_cache_lock:
        if name in moves_cache and moves_cache[name]:
            _stats["moves_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: move {name}")
            return moves_cache[name]

    _stats["moves_misses"] += 1
    from utils.pokeapi import get_move
    data = get_move(name)
    if not data:
        try:
            from utils.battle_engine import EXHAUSTIVE_MOVES_DATA
            from utils.naming import humanize_name
            slug = name.replace(" ", "-")
            if slug in EXHAUSTIVE_MOVES_DATA:
                m_def = EXHAUSTIVE_MOVES_DATA[slug]
                m_type = m_def.get("type", "normal")
                m_class = m_def.get("category", "physical")
                data = {
                    "id": 9000,
                    "name": slug,
                    "power": m_def.get("power"),
                    "accuracy": m_def.get("accuracy", 100),
                    "pp": m_def.get("pp", 15),
                    "priority": m_def.get("priority", 0),
                    "type": {"name": m_type},
                    "damage_class": {"name": m_class},
                    "effect_entries": [{
                        "short_effect": f"Inflicts damage using {m_type.capitalize()} power.",
                        "language": {"name": "en"}
                    }],
                    "flavor_text_entries": [{
                        "flavor_text": f"A competitive move of the {m_type.capitalize()} type.",
                        "language": {"name": "en"}
                    }],
                    "learned_by_pokemon": []
                }
        except Exception:
            pass

    with _moves_cache_lock:
        if data:
            moves_cache[name] = data
    if data:
        save_moves_cache()
    return data


def get_all_move_names_cached() -> list[str]:
    """Fetch and cache all move names under moves_cache['_all_moves']."""
    key = "_all_moves"
    with _moves_cache_lock:
        if key in moves_cache:
            _stats["moves_hits"] += 1
            return moves_cache[key]

    _stats["moves_misses"] += 1
    try:
        data = _json_fetch("https://pokeapi.co/api/v2/move?limit=2000&offset=0")
        names = [m["name"] for m in (data or {}).get("results", []) if m.get("name")]
        with _moves_cache_lock:
            moves_cache[key] = names
        save_moves_cache(sync=True)
        log_action(f"Primed all_moves ({len(names)})")
        return names
    except Exception as e:
        log_action(f"ERROR fetching all_moves: {e}")
        return []


def refresh_moves_cache() -> None:
    """Clear moves cache file and memory."""
    global moves_cache
    with _moves_cache_lock:
        moves_cache = {}
    if os.path.exists(MOVES_CACHE_FILE):
        try:
            os.remove(MOVES_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing moves cache file: {e}")
    save_moves_cache(sync=True)
    log_action("Moves cache manually refreshed")


def backup_moves_cache() -> bool:
    save_moves_cache(sync=True)
    return _create_backup("moves_cache", moves_cache, _moves_cache_lock)


def recover_moves_cache() -> bool:
    ok, recovered = _recover_backup("moves_cache", MOVES_CACHE_FILE)
    if ok and recovered is not None:
        global moves_cache
        with _moves_cache_lock:
            moves_cache = recovered
        save_moves_cache(sync=True)
        return True
    return False


# --------------------------------------------------------------------------- #
# Separate Abilities Cache Management
# --------------------------------------------------------------------------- #

def _perform_save_abilities_cache() -> None:
    try:
        with _abilities_cache_lock:
            snapshot = dict(abilities_cache)
        _atomic_write(ABILITIES_CACHE_FILE, snapshot)
        log_action("abilities_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving abilities_cache: {e}")


def save_abilities_cache(sync: bool = False) -> None:
    if sync:
        _perform_save_abilities_cache()
    else:
        _schedule_debounced_save(_perform_save_abilities_cache, delay=1.5)


def get_all_ability_names_cached() -> list[str]:
    """Fetch and cache all ability names under abilities_cache['_all_abilities']."""
    key = "_all_abilities"
    with _abilities_cache_lock:
        if key in abilities_cache:
            _stats["abilities_hits"] += 1
            return [a for a in abilities_cache[key] if not a.startswith("_")]

    _stats["abilities_misses"] += 1
    try:
        data = _json_fetch("https://pokeapi.co/api/v2/ability?limit=500&offset=0")
        names = [m["name"] for m in (data or {}).get("results", []) if m.get("name")]
        with _abilities_cache_lock:
            abilities_cache[key] = names
        save_abilities_cache(sync=True)
        log_action(f"Primed all_abilities ({len(names)})")
        return names
    except Exception as e:
        log_action(f"ERROR fetching all_abilities: {e}")
        with _abilities_cache_lock:
            return [k for k in abilities_cache.keys() if not k.startswith("_")]


def refresh_abilities_cache() -> None:
    """Clear abilities cache file and memory."""
    global abilities_cache
    with _abilities_cache_lock:
        abilities_cache = {}
    if os.path.exists(ABILITIES_CACHE_FILE):
        try:
            os.remove(ABILITIES_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing abilities cache file: {e}")
    save_abilities_cache(sync=True)
    log_action("Abilities cache manually refreshed")


def backup_abilities_cache() -> bool:
    save_abilities_cache(sync=True)
    return _create_backup("abilities_cache", abilities_cache, _abilities_cache_lock)


def recover_abilities_cache() -> bool:
    ok, recovered = _recover_backup("abilities_cache", ABILITIES_CACHE_FILE)
    if ok and recovered is not None:
        global abilities_cache
        with _abilities_cache_lock:
            abilities_cache = recovered
        save_abilities_cache(sync=True)
        return True
    return False


# --------------------------------------------------------------------------- #
# Separate Items Cache Management
# --------------------------------------------------------------------------- #

def _perform_save_items_cache() -> None:
    try:
        with _items_cache_lock:
            snapshot = dict(items_cache)
        _atomic_write(ITEMS_CACHE_FILE, snapshot)
        log_action("items_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving items_cache: {e}")


def save_items_cache(sync: bool = False) -> None:
    if sync:
        _perform_save_items_cache()
    else:
        _schedule_debounced_save(_perform_save_items_cache, delay=1.5)


def get_item_cached(name: str) -> dict | None:
    name = str(name).lower().strip()
    with _items_cache_lock:
        if name in items_cache and items_cache[name]:
            _stats["items_hits"] += 1
            if ENABLE_VERBOSE_LOGGING:
                log_action(f"CACHE HIT: item {name}")
            return items_cache[name]

    _stats["items_misses"] += 1
    log_action(f"CACHE MISS: item {name} - Fetching from API")
    from utils.pokeapi import get_item
    data = get_item(name)
    if data and isinstance(data, dict) and data.get("name"):
        with _items_cache_lock:
            items_cache[name] = data
        save_items_cache()
        # If this item is a mega stone or held item, refresh mega_stone_map and competitive_items
        cat = (data.get("category") or {}).get("name")
        if cat == "mega-stones" or name.endswith("ite") or name.endswith(("-x", "-y", "-z")):
            get_mega_stone_map(force_refresh=True)
            try:
                from utils.teambuilder_storage import get_competitive_items
                get_competitive_items()
            except Exception:
                pass
    return data


def get_all_item_names_cached() -> list[str]:
    """Fetch and cache all item names under items_cache['_all_items']."""
    key = "_all_items"
    with _items_cache_lock:
        if key in items_cache:
            _stats["items_hits"] += 1
            return [i for i in items_cache[key] if not i.startswith("_")]

    _stats["items_misses"] += 1
    try:
        data = _json_fetch("https://pokeapi.co/api/v2/item?limit=2500&offset=0")
        names = [m["name"] for m in (data or {}).get("results", []) if m.get("name")]
        with _items_cache_lock:
            items_cache[key] = names
        save_items_cache(sync=True)
        log_action(f"Primed all_items ({len(names)})")
        return names
    except Exception as e:
        log_action(f"ERROR fetching all_items: {e}")
        with _items_cache_lock:
            return [k for k in items_cache.keys() if not k.startswith("_")]


def refresh_items_cache() -> None:
    """Clear items cache file and memory."""
    global items_cache
    with _items_cache_lock:
        items_cache = {}
    if os.path.exists(ITEMS_CACHE_FILE):
        try:
            os.remove(ITEMS_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing items cache file: {e}")
    save_items_cache(sync=True)
    get_mega_stone_map(force_refresh=True)
    log_action("Items cache manually refreshed")


def backup_items_cache() -> bool:
    save_items_cache(sync=True)
    return _create_backup("items_cache", items_cache, _items_cache_lock)


def recover_items_cache() -> bool:
    ok, recovered = _recover_backup("items_cache", ITEMS_CACHE_FILE)
    if ok and recovered is not None:
        global items_cache
        with _items_cache_lock:
            items_cache = recovered
        save_items_cache(sync=True)
        get_mega_stone_map(force_refresh=True)
        return True
    return False


# --------------------------------------------------------------------------- #
# Mega Stones Dynamic Cache Manager
# --------------------------------------------------------------------------- #

def _perform_save_mega_stones_cache() -> None:
    try:
        with _mega_stones_cache_lock:
            snapshot = {k: dict(v) for k, v in mega_stones_cache.items()}
        _atomic_write(MEGA_STONES_CACHE_FILE, snapshot)
        log_action("mega_stones_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving mega_stones_cache: {e}")


def save_mega_stones_cache(sync: bool = False) -> None:
    if sync:
        _perform_save_mega_stones_cache()
    else:
        _schedule_debounced_save(_perform_save_mega_stones_cache, delay=1.5)


def get_mega_stone_map(force_refresh: bool = False) -> dict:
    """
    Returns the persistent mapping of species -> {held_stone_slug: mega_form_slug}.
    Loads from data/mega_stones_cache.json if present; falls back to DEFAULT_INITIAL_MEGA_STONES.
    Dynamically scans items_cache and pokemon_cache to discover and register all canonical
    and newly added Mega Stones from PokéAPI, saving updates atomically to disk.
    """
    global mega_stones_cache
    with _mega_stones_cache_lock:
        disk_data = None
        if not mega_stones_cache or force_refresh:
            disk_data = _load_cache_file(MEGA_STONES_CACHE_FILE, {})
            if disk_data and not force_refresh:
                mega_stones_cache = {k: dict(v) for k, v in disk_data.items()}
            else:
                mega_stones_cache = {k: dict(v) for k, v in DEFAULT_INITIAL_MEGA_STONES.items()}

        import re
        updated = False
        mega_pokemon = [k for k in pokemon_cache if "-mega" in k]

        with _items_cache_lock:
            items_snapshot = list(items_cache.items())

        for stone_name, data in items_snapshot:
            if not isinstance(data, dict):
                continue
            cat = (data.get("category") or {}).get("name")
            is_stone = (cat == "mega-stones") or (
                stone_name.endswith("ite") or stone_name.endswith("-x") or
                stone_name.endswith("-y") or stone_name.endswith("-z")
            )
            if not is_stone or stone_name.startswith("_"):
                continue

            en_texts = [f.get("text", "") for f in data.get("flavor_text_entries", []) if isinstance(f, dict) and f.get("language", {}).get("name") == "en"]
            en_effects = [e.get("effect", "") for e in data.get("effect_entries", []) if isinstance(e, dict) and e.get("language", {}).get("name") == "en"]
            all_text = " ".join(en_texts + en_effects)

            match = re.search(r"Have\s+([A-Za-z\-]+)\s+hold\s+it", all_text, re.I)
            if not match:
                match = re.search(r"Allows\s+([A-Za-z\-]+)\s+to\s+Mega\s+Evolve", all_text, re.I)
            species = match.group(1).lower().strip() if match else None

            suffix = ""
            if stone_name.endswith("-x") or stone_name.endswith("itex"):
                suffix = "-x"
            elif stone_name.endswith("-y") or stone_name.endswith("itey"):
                suffix = "-y"
            elif stone_name.endswith("-z") or stone_name.endswith("itez"):
                suffix = "-z"
            elif "mega charizard x" in all_text.lower() or "mega mewtwo x" in all_text.lower():
                suffix = "-x"
            elif "mega charizard y" in all_text.lower() or "mega mewtwo y" in all_text.lower():
                suffix = "-y"

            if not species:
                base_stone = re.sub(r"(-[xyz]|ite[xyz]?)$", "", stone_name).replace("-", "")
                for p in mega_pokemon:
                    p_base = (pokemon_cache[p].get("species", {}).get("name") or p.split("-mega")[0]).lower().replace("-", "")
                    if p_base.startswith(base_stone[:4]) or base_stone.startswith(p_base[:4]):
                        species = p_base
                        break

            if species:
                target_mega = f"{species}-mega{suffix}"
                if species not in mega_stones_cache:
                    mega_stones_cache[species] = {}
                    updated = True
                if mega_stones_cache[species].get(stone_name) != target_mega:
                    mega_stones_cache[species][stone_name] = target_mega
                    updated = True
                undashed = stone_name.replace("-", "")
                if mega_stones_cache[species].get(undashed) != target_mega:
                    mega_stones_cache[species][undashed] = target_mega
                    updated = True

        if updated or not os.path.exists(MEGA_STONES_CACHE_FILE) or os.path.getsize(MEGA_STONES_CACHE_FILE) <= 2:
            _perform_save_mega_stones_cache()

        return dict(mega_stones_cache)


def refresh_mega_stones_cache() -> None:
    """Clear mega stones cache file and memory, re-seeding from defaults & dynamic discovery."""
    global mega_stones_cache
    with _mega_stones_cache_lock:
        mega_stones_cache = {}
    if os.path.exists(MEGA_STONES_CACHE_FILE):
        try:
            os.remove(MEGA_STONES_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing mega stones cache file: {e}")
    get_mega_stone_map(force_refresh=True)
    log_action("Mega stones cache manually refreshed")


# --------------------------------------------------------------------------- #
# Gigantamax Dynamic Cache Manager
# --------------------------------------------------------------------------- #

def _perform_save_gmax_moves_cache() -> None:
    try:
        with _gmax_moves_cache_lock:
            snapshot = {k: dict(v) for k, v in gmax_moves_cache.items()}
        _atomic_write(GMAX_MOVES_CACHE_FILE, snapshot)
        log_action("gmax_moves_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving gmax_moves_cache: {e}")


def save_gmax_moves_cache(sync: bool = False) -> None:
    if sync:
        _perform_save_gmax_moves_cache()
    else:
        _schedule_debounced_save(_perform_save_gmax_moves_cache, delay=1.5)


def get_species_gmax_moves_map(force_refresh: bool = False) -> dict:
    """
    Returns the persistent mapping of species -> signature G-Max move definitions and effects.
    Loads from data/gmax_moves_cache.json if present; falls back to DEFAULT_INITIAL_GMAX_MOVES.
    Dynamically scans pokemon_cache and moves_cache to discover any new G-Max forms or moves.
    """
    global gmax_moves_cache
    with _gmax_moves_cache_lock:
        if not gmax_moves_cache or force_refresh:
            disk_data = _load_cache_file(GMAX_MOVES_CACHE_FILE, {})
            if disk_data and not force_refresh:
                gmax_moves_cache = {k: dict(v) for k, v in disk_data.items()}
            else:
                gmax_moves_cache = {k: dict(v) for k, v in DEFAULT_INITIAL_GMAX_MOVES.items()}

        updated = False
        with _pokemon_cache_lock:
            poke_items = list(pokemon_cache.items())

        for slug, data in poke_items:
            if "-gmax" in slug:
                base_species = (data.get("species", {}).get("name") or slug.replace("-gmax", "")).lower().strip()
                clean_variant = slug.replace("-gmax", "")
                if base_species not in gmax_moves_cache and clean_variant not in gmax_moves_cache:
                    g_move_name = f"G-Max {base_species.replace('-', ' ').title()}"
                    types = [t.get("type", {}).get("name", "normal") for t in data.get("types", []) if isinstance(t.get("type"), dict)]
                    b_type = types[0] if types else "normal"
                    gmax_moves_cache[base_species] = {
                        "name": g_move_name,
                        "base_type": b_type,
                        "desc": f"Gigantamax signature move for {base_species}."
                    }
                    updated = True

        if updated or not os.path.exists(GMAX_MOVES_CACHE_FILE) or os.path.getsize(GMAX_MOVES_CACHE_FILE) <= 2:
            _perform_save_gmax_moves_cache()

        return dict(gmax_moves_cache)


def refresh_gmax_moves_cache() -> None:
    """Clear G-Max moves cache file and memory, re-seeding from defaults & dynamic discovery."""
    global gmax_moves_cache
    with _gmax_moves_cache_lock:
        gmax_moves_cache = {}
    if os.path.exists(GMAX_MOVES_CACHE_FILE):
        try:
            os.remove(GMAX_MOVES_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing G-Max moves cache file: {e}")
    get_species_gmax_moves_map(force_refresh=True)
    log_action("G-Max moves cache manually refreshed")


# --------------------------------------------------------------------------- #
# Move Overrides Dynamic Cache Manager
# --------------------------------------------------------------------------- #

def _perform_save_move_overrides_cache() -> None:
    try:
        with _move_overrides_cache_lock:
            snapshot = {k: dict(v) for k, v in move_overrides_cache.items()}
        _atomic_write(MOVE_OVERRIDES_CACHE_FILE, snapshot)
        log_action("move_overrides_cache.json persisted to disk")
    except Exception as e:
        log_action(f"ERROR saving move_overrides_cache: {e}")


def save_move_overrides_cache(sync: bool = False) -> None:
    if sync:
        _perform_save_move_overrides_cache()
    else:
        _schedule_debounced_save(_perform_save_move_overrides_cache, delay=1.5)


def get_move_overrides_map(force_refresh: bool = False) -> dict:
    """
    Returns the persistent competitive move overrides dictionary (priority, custom mechanics).
    Loads from data/move_overrides_cache.json; falls back to DEFAULT_INITIAL_MOVE_OVERRIDES.
    """
    global move_overrides_cache
    with _move_overrides_cache_lock:
        if not move_overrides_cache or force_refresh:
            disk_data = _load_cache_file(MOVE_OVERRIDES_CACHE_FILE, {})
            if disk_data:
                move_overrides_cache = {k: dict(v) for k, v in disk_data.items()}
            else:
                move_overrides_cache = {k: dict(v) for k, v in DEFAULT_INITIAL_MOVE_OVERRIDES.items()}

        if not os.path.exists(MOVE_OVERRIDES_CACHE_FILE) or os.path.getsize(MOVE_OVERRIDES_CACHE_FILE) <= 2:
            _perform_save_move_overrides_cache()

        return dict(move_overrides_cache)


def refresh_move_overrides_cache() -> None:
    """Clear move overrides cache file and memory, re-seeding from defaults."""
    global move_overrides_cache
    with _move_overrides_cache_lock:
        move_overrides_cache = {}
    if os.path.exists(MOVE_OVERRIDES_CACHE_FILE):
        try:
            os.remove(MOVE_OVERRIDES_CACHE_FILE)
        except Exception as e:
            log_action(f"ERROR removing move overrides cache file: {e}")
    get_move_overrides_map(force_refresh=True)
    log_action("Move overrides cache manually refreshed")

