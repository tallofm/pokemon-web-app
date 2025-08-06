import os
import json
from datetime import datetime
from utils.logger import log_action

CACHE_FILE = "data/pokemon_cache.json"
ENABLE_VERBOSE_LOGGING = False  # default: full logs

if not os.path.exists("data"):
    os.makedirs("data")

# load cache safely
try:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            pokemon_cache = json.load(f)
    else:
        pokemon_cache = {}
except Exception as e:
    log_action(f"ERROR loading cache: {e}")
    pokemon_cache = {}

EXTRA_CACHE_FILE = "data/extra_cache.json"
REQUIRED_EXTRA_KEYS = ["species", "evolution", "type", "generation"]

# load or initialize extra cache
try:
    if os.path.exists(EXTRA_CACHE_FILE):
        with open(EXTRA_CACHE_FILE, "r") as f:
            extra_cache = json.load(f)
    else:
        extra_cache = {}
except Exception as e:
    log_action(f"ERROR loading extra cache: {e}")
    extra_cache = {}

# ensure all required sections exist
for key in REQUIRED_EXTRA_KEYS:
    extra_cache.setdefault(key, {})

# write back if it was newly created or patched
with open(EXTRA_CACHE_FILE, "w") as f:
    json.dump(extra_cache, f)

def get_pokemon_cached(name, get_pokemon_fn):
    name = name.lower()
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

def get_species_cached(name):
    name = name.lower()
    if name in extra_cache["species"]:
        if ENABLE_VERBOSE_LOGGING:
            log_action(f"CACHE HIT: species {name}")
        return extra_cache["species"][name]

    from utils.pokeapi import get_species
    data = get_species(name)
    if data:
        extra_cache["species"][name] = data
        save_extra_cache()
    return data

def get_evolution_chain_cached(species_data):
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
    key = str(gen_id)
    if key in extra_cache.get("generation", {}):
        if ENABLE_VERBOSE_LOGGING:   
            log_action(f"CACHE HIT: generation {key}")
        return extra_cache["generation"][key]

    import requests
    url = f"https://pokeapi.co/api/v2/generation/{gen_id}/"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        extra_cache["generation"][key] = data
        save_extra_cache()
        return data
    else:
        log_action(f"ERROR fetching generation {key}")
        return None

def get_type_cached(type_name):
    type_name = type_name.lower()
    if type_name in extra_cache["type"]:
        if ENABLE_VERBOSE_LOGGING:
            log_action(f"CACHE HIT: type {type_name}")
        return extra_cache["type"][type_name]

    import requests
    url = f"https://pokeapi.co/api/v2/type/{type_name}"
    res = requests.get(url)
    if res.status_code == 200:
        data = res.json()
        extra_cache["type"][type_name] = data
        save_extra_cache()
        return data
    else:
        log_action(f"ERROR fetching type {type_name}")
        return None

def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(pokemon_cache, f)
        log_action("Cache saved to disk")
    except Exception as e:
        log_action(f"ERROR saving cache: {e}")

def save_extra_cache():
    try:
        with open(EXTRA_CACHE_FILE, "w") as f:
            json.dump(extra_cache, f)
        log_action("extra_cache.json saved")
    except Exception as e:
        log_action(f"ERROR saving extra_cache: {e}")

def refresh_cache():
    global pokemon_cache
    pokemon_cache = {}
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    log_action("Cache manually refreshed")

def backup_cache():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"data/pokemon_cache_backup_{timestamp}.json"
    try:
        with open(backup_path, "w") as f:
            json.dump(pokemon_cache, f)
        log_action(f"Backup created: {backup_path}")
    except Exception as e:
        log_action(f"ERROR creating backup: {e}")

def recover_cache():
    from glob import glob
    global pokemon_cache

    backups = sorted(glob("data/pokemon_cache_backup_*.json"), reverse=True)
    if not backups:
        log_action("Recover failed: No backups found")
        return False

    latest_backup = backups[0]
    try:
        with open(latest_backup, "r") as f:
            recovered = json.load(f)
        pokemon_cache = recovered
        save_cache()
        log_action(f"Recovered from: {latest_backup}")
        return True
    except Exception as e:
        log_action(f"ERROR recovering cache: {e}")
        return False

def backup_extra_cache():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"data/extra_cache_backup_{timestamp}.json"
    try:
        with open(backup_path, "w") as f:
            json.dump(extra_cache, f)
        log_action(f"Extra cache backup created: {backup_path}")
    except Exception as e:
        log_action(f"ERROR creating extra cache backup: {e}")

def refresh_extra_cache():
    global extra_cache
    extra_cache = {"species": {}, "evolution": {}, "type": {}, "generation": {}}
    if os.path.exists(EXTRA_CACHE_FILE):
        os.remove(EXTRA_CACHE_FILE)
    log_action("Extra cache manually refreshed")

def recover_extra_cache():
    from glob import glob
    global extra_cache

    backups = sorted(glob("data/extra_cache_backup_*.json"), reverse=True)
    if not backups:
        log_action("Recover failed: No extra cache backups found")
        return False

    latest_backup = backups[0]
    try:
        with open(latest_backup, "r") as f:
            recovered = json.load(f)
        extra_cache = recovered
        save_extra_cache()
        log_action(f"Extra cache recovered from: {latest_backup}")
        return True
    except Exception as e:
        log_action(f"ERROR recovering extra cache: {e}")
        return False
