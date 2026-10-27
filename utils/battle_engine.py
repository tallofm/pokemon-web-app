"""
battle_engine.py - Turn-by-Turn Competitive Pokémon Battle Engine.
Implements Generation 9 competitive mechanics:
- Exact damage formula with IVs, EVs, Natures, Stat Stages (-6 to +6)
- Accurate 18-type effectiveness matrix with immunities & dual-types
- Weather (Rain, Sun, Sandstorm, Snow) and Terrains (Electric, Grassy, Psychic, Misty)
- Priority brackets (-7 to +5), Trick Room, Tailwind, Speed calculations
- Entry hazards (Stealth Rock, Spikes, Toxic Spikes, Sticky Web)
- Major competitive Abilities (Intimidate, Stamina, Good as Gold, Drizzle, Drought, Guts, Protosynthesis, Levitate, Earth Eater, etc.)
- Major competitive Items (Assault Vest, Rocky Helmet, Focus Sash, Leftovers, Choice Items, Life Orb, Sitrus Berry, etc.)
- Terastallization (Offensive STAB boost and Defensive type override)
- Full move metadata (Type, Category: Physical/Special/Status, Power, Accuracy, PP) for UI rendering
- Full serializable battle state with detailed event logs for frontend animations
"""

import math
import random
import os
import json
from typing import Dict, List, Optional, Any, Tuple, Set
from utils.naming import humanize_name

# Sound-based moves that bypass Substitute completely (Gen 6+)
SOUND_MOVES: Set[str] = {
    "boomburst", "bug-buzz", "hyper-voice", "clanging-scales", "clangorous-soulblaze",
    "snarl", "round", "disarming-voice", "sparkling-aria", "torch-song", "overdrive",
    "alluring-voice", "psychic-noise", "echoed-voice", "uproar", "relic-song",
    "roar", "perish-song", "growl", "screech", "sing", "supersonic", "metal-sound",
    "heal-bell", "grass-whistle", "chatter", "parting-shot", "howl", "confide"
}

# Protection moves that share the consecutive usage degradation counter ((1/3)^n in Gen 6+)
PROTECT_MOVES: Set[str] = {
    "protect", "detect", "spiky-shield", "baneful-bunker", "kings-shield",
    "obstruct", "silk-trap", "burning-bulwark", "max-guard", "endure"
}

# Punching moves boosted by 20% (1.2x) by Iron Fist (and affected by Punching Glove)
PUNCHING_MOVES: Set[str] = {
    "rage-fist", "drain-punch", "fire-punch", "ice-punch", "thunder-punch",
    "bullet-punch", "mach-punch", "shadow-punch", "focus-punch", "hammer-arm",
    "ice-hammer", "dizzy-punch", "mega-punch", "comet-punch", "dynamic-punch",
    "wicked-blow", "surging-strikes", "plasma-fists", "double-iron-bash"
}

# Standard 18-Type Matchup Chart
# Keys: Attacking Type -> Defender Type -> Multiplier
TYPE_CHART: Dict[str, Dict[str, float]] = {
    "normal":   {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0, "bug": 2.0, "rock": 0.5, "dragon": 0.5, "steel": 2.0},
    "water":    {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0, "rock": 2.0, "dragon": 0.5},
    "electric": {"water": 2.0, "electric": 0.5, "grass": 0.5, "ground": 0.0, "flying": 2.0, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5, "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0, "dragon": 0.5, "steel": 0.5},
    "ice":      {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5, "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0, "dark": 2.0, "steel": 2.0, "fairy": 0.5},
    "poison":   {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0, "fairy": 2.0},
    "ground":   {"fire": 2.0, "electric": 2.0, "grass": 0.5, "poison": 2.0, "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0},
    "flying":   {"electric": 0.5, "grass": 2.0, "fighting": 2.0, "bug": 2.0, "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0, "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0, "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5, "flying": 2.0, "bug": 2.0, "steel": 0.5},
    "ghost":    {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon":   {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark":     {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5, "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0, "rock": 2.0, "steel": 0.5, "fairy": 2.0},
    "fairy":    {"fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0, "dark": 2.0, "steel": 0.5}
}

NATURE_MODIFIERS: Dict[str, Dict[str, float]] = {
    "adamant": {"attack": 1.1, "special-attack": 0.9},
    "bold": {"defense": 1.1, "attack": 0.9},
    "brave": {"attack": 1.1, "speed": 0.9},
    "calm": {"special-defense": 1.1, "attack": 0.9},
    "careful": {"special-defense": 1.1, "special-attack": 0.9},
    "hasty": {"speed": 1.1, "defense": 0.9},
    "impish": {"defense": 1.1, "special-attack": 0.9},
    "jolly": {"speed": 1.1, "special-attack": 0.9},
    "modest": {"special-attack": 1.1, "attack": 0.9},
    "naive": {"speed": 1.1, "special-defense": 0.9},
    "quiet": {"special-attack": 1.1, "speed": 0.9},
    "rash": {"special-attack": 1.1, "special-defense": 0.9},
    "relaxed": {"defense": 1.1, "speed": 0.9},
    "sassy": {"special-defense": 1.1, "speed": 0.9},
    "timid": {"speed": 1.1, "attack": 0.9},
}

STAT_ABBR_MAP: Dict[str, str] = {
    "hp": "HP",
    "hit-points": "HP",
    "hit_points": "HP",
    "attack": "Atk",
    "atk": "Atk",
    "defense": "Def",
    "def": "Def",
    "special-attack": "SpA",
    "special_attack": "SpA",
    "sp_atk": "SpA",
    "spa": "SpA",
    "special-defense": "SpD",
    "special_defense": "SpD",
    "sp_def": "SpD",
    "spd": "SpD",
    "speed": "Spe",
    "spe": "Spe",
    "accuracy": "Acc",
    "evasion": "Eva",
}

def format_stat_name(stat: str) -> str:
    """Format canonical stat identifier into competitive abbreviation (e.g. 'special-attack' -> 'SpA')."""
    s = str(stat or "").lower().strip()
    return STAT_ABBR_MAP.get(s, s.capitalize())

# --------------------------------------------------------------------------- #
# Dynamic Species Typing Registry (from Pokédex cache)
# --------------------------------------------------------------------------- #

def build_dynamic_types_registry(cache: dict) -> Dict[str, List[str]]:
    """Dynamically builds a comprehensive lookup of species types from Pokédex cache (1,354+ forms)."""
    types_reg: Dict[str, List[str]] = {}
    for slug, data in (cache or {}).items():
        types = [t["type"]["name"].lower() for t in data.get("types", []) if isinstance(t.get("type"), dict)]
        if types:
            clean = slug.replace(" ", "-").lower()
            types_reg[clean] = types
            if "-mask" in clean:
                types_reg[clean.replace("-mask", "")] = types
    return types_reg


# --------------------------------------------------------------------------- #
# Dynamic Mega Evolutions Registry (Omni Ring)
# --------------------------------------------------------------------------- #

def parse_mega_entry_from_data(slug: str, data: dict, base_data: Optional[dict] = None) -> Dict[str, Any]:
    """Helper to parse a Mega / Primal form dictionary into a normalized registry entry."""
    base_species = (data.get("species", {}).get("name") or slug.split("-mega")[0].split("-primal")[0]).lower().strip()
    types = [t["type"]["name"].lower() for t in data.get("types", []) if isinstance(t.get("type"), dict)]
    abilities = [a["ability"]["name"].lower() for a in data.get("abilities", []) if isinstance(a.get("ability"), dict)]
    sprites = data.get("sprites", {})
    other = sprites.get("other", {})
    showdown = other.get("showdown", {})
    official = other.get("official-artwork", {})
    sprite = showdown.get("front_default") or sprites.get("front_default") or official.get("front_default")

    stat_boosts: Dict[str, int] = {}
    if base_data:
        m_stats = {s["stat"]["name"]: s.get("base_stat", 0) for s in data.get("stats", []) if isinstance(s.get("stat"), dict)}
        b_stats = {s["stat"]["name"]: s.get("base_stat", 0) for s in base_data.get("stats", []) if isinstance(s.get("stat"), dict)}
        for k, v in m_stats.items():
            diff = v - b_stats.get(k, 0)
            if diff != 0:
                stat_boosts[k] = diff

    display_name = humanize_name(slug)
    return {
        "mega_species": slug,
        "name": display_name,
        "types": types,
        "ability": abilities[0] if abilities else "",
        "stat_boosts": stat_boosts,
        "sprite": sprite
    }


def build_dynamic_mega_registry(cache: dict) -> Dict[str, Dict[str, Any]]:
    """
    Dynamically scans Pokédex cache for all Mega and Primal forms (97+ forms).
    Calculates stat boosts relative to base forms and extracts typings, abilities, and sprites.
    """
    registry: Dict[str, Dict[str, Any]] = {}
    for slug, data in (cache or {}).items():
        if "-mega" in slug or "-primal" in slug:
            base_species = (data.get("species", {}).get("name") or slug.split("-mega")[0].split("-primal")[0]).lower().strip()
            base_data = (cache or {}).get(base_species)
            entry = parse_mega_entry_from_data(slug, data, base_data)
            # Key by mega form slug
            registry[slug] = entry
            # Key by base species (prioritize canonical -mega, then -mega-y)
            curr = registry.get(base_species)
            should_set = False
            if not curr:
                should_set = True
            elif slug == f"{base_species}-mega":
                should_set = True
            elif curr.get("mega_species") != f"{base_species}-mega" and "-mega-y" in slug:
                should_set = True

            if should_set:
                registry[base_species] = entry
                registry[base_species.replace("-", "")] = entry

    return registry


# Dynamic registries and cached datasets initialized from Pokédex cache & dynamic loaders
try:
    from utils.cache import (
        pokemon_cache, moves_cache, get_move_cached,
        get_mega_stone_map, get_species_gmax_moves_map, get_move_overrides_map
    )
except ImportError:
    pokemon_cache, moves_cache, get_move_cached = {}, {}, None
    from utils.default_datasets import (
        DEFAULT_INITIAL_MEGA_STONES, DEFAULT_INITIAL_GMAX_MOVES, DEFAULT_INITIAL_MOVE_OVERRIDES
    )
    get_mega_stone_map = lambda force_refresh=False: dict(DEFAULT_INITIAL_MEGA_STONES)
    get_species_gmax_moves_map = lambda force_refresh=False: dict(DEFAULT_INITIAL_GMAX_MOVES)
    get_move_overrides_map = lambda force_refresh=False: dict(DEFAULT_INITIAL_MOVE_OVERRIDES)

# --------------------------------------------------------------------------- #
# Dynamic G-Max Signatures Map & Gigantamax Registry (Omni Ring)
# --------------------------------------------------------------------------- #

SPECIES_GMAX_MOVES_MAP: Dict[str, Dict[str, Any]] = get_species_gmax_moves_map()

def build_dynamic_gmax_registry(cache: dict) -> Dict[str, Dict[str, Any]]:
    """
    Dynamically scans Pokédex cache for all Gigantamax forms (34+ forms).
    Extracts official sprites, names, and links signature G-Max moves.
    """
    registry: Dict[str, Dict[str, Any]] = {}
    for slug, data in (cache or {}).items():
        if "-gmax" in slug:
            base_species = (data.get("species", {}).get("name") or slug.replace("-gmax", "")).lower().strip()
            sprites = data.get("sprites", {})
            other = sprites.get("other", {})
            showdown = other.get("showdown", {})
            official = other.get("official-artwork", {})
            sprite = showdown.get("front_default") or sprites.get("front_default") or official.get("front_default")
            
            clean_variant = slug.replace("-gmax", "")
            sig = SPECIES_GMAX_MOVES_MAP.get(clean_variant) or SPECIES_GMAX_MOVES_MAP.get(slug) or SPECIES_GMAX_MOVES_MAP.get(base_species)
            gmax_move = sig.get("name") if sig else "Max Strike"
            gmax_name = f"Gigantamax {humanize_name(base_species)}"
            
            entry = {
                "gmax_species": slug,
                "gmax_name": gmax_name,
                "gmax_move": gmax_move,
                "sprite": sprite
            }
            registry[slug] = entry
            registry[clean_variant] = entry
            registry[base_species] = entry
            registry[base_species.replace("-", "")] = entry
            
    return registry


DYNAMIC_SPECIES_TYPES: Dict[str, List[str]] = build_dynamic_types_registry(pokemon_cache)
CANONICAL_SPECIES_TYPES: Dict[str, List[str]] = DYNAMIC_SPECIES_TYPES

def get_pokemon_types(species_name: str) -> List[str]:
    """Dynamically resolves canonical Pokémon types directly from Pokédex cache."""
    clean = str(species_name or "").lower().strip().replace(" ", "-")
    if clean in DYNAMIC_SPECIES_TYPES:
        return list(DYNAMIC_SPECIES_TYPES[clean])
    for alt in (f"{clean}-mask", clean.split("-")[0]):
        if alt in DYNAMIC_SPECIES_TYPES:
            return list(DYNAMIC_SPECIES_TYPES[alt])
    return ["normal"]

# Dynamic Mega Stone mapping initialized from persistent mega_stones_cache.json
MEGA_STONE_MAP: Dict[str, Dict[str, str]] = get_mega_stone_map()

MEGA_EVOLUTIONS: Dict[str, Dict[str, Any]] = build_dynamic_mega_registry(pokemon_cache)

def ensure_mega_in_registry(mega_slug: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Ensures a specific Mega Evolution form is registered in MEGA_EVOLUTIONS.
    If missing from memory, checks pokemon_cache, or fetches on demand via PokéAPI,
    updates pokemon_cache on disk, and dynamically registers it into MEGA_EVOLUTIONS.
    """
    if not mega_slug:
        return None
    slug = str(mega_slug).lower().strip()
    if slug in MEGA_EVOLUTIONS:
        return MEGA_EVOLUTIONS[slug]

    data = None
    try:
        from utils.cache import get_pokemon_cached, pokemon_cache
        from utils.pokeapi import get_pokemon as pokeapi_get_pokemon
        if slug in pokemon_cache:
            data = pokemon_cache[slug]
        else:
            data = get_pokemon_cached(slug, pokeapi_get_pokemon)
    except Exception:
        pass

    if not data or not isinstance(data, dict):
        return None

    base_species = (data.get("species", {}).get("name") or slug.split("-mega")[0].split("-primal")[0]).lower().strip()
    base_data = None
    try:
        if base_species in pokemon_cache:
            base_data = pokemon_cache[base_species]
        else:
            base_data = get_pokemon_cached(base_species, pokeapi_get_pokemon)
    except Exception:
        pass

    entry = parse_mega_entry_from_data(slug, data, base_data)
    MEGA_EVOLUTIONS[slug] = entry
    if base_species not in MEGA_EVOLUTIONS:
        MEGA_EVOLUTIONS[base_species] = entry
        MEGA_EVOLUTIONS[base_species.replace("-", "")] = entry

    return entry
GMAX_SPECIES: Dict[str, Dict[str, Any]] = build_dynamic_gmax_registry(pokemon_cache)
SPECIES_GMAX_MOVES: Dict[str, Dict[str, Any]] = SPECIES_GMAX_MOVES_MAP

# Dynamic competitive move registry initialized from persistent move_overrides_cache.json
EXHAUSTIVE_MOVES_DATA: Dict[str, Dict[str, Any]] = get_move_overrides_map()


# Preload moves_cache.json if available
CACHED_MOVES_JSON: Dict[str, Any] = {}
MOVES_CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "moves_cache.json")
if os.path.exists(MOVES_CACHE_FILE):
    try:
        with open(MOVES_CACHE_FILE, "r", encoding="utf-8") as f:
            CACHED_MOVES_JSON = json.load(f)
    except Exception:
        pass


KEY_MOVES_DATA = EXHAUSTIVE_MOVES_DATA


def get_move_metadata(move_name: str) -> Dict[str, Any]:
    """Retrieves full move definition with true Type, Category, Power, Accuracy, Priority, and PP dynamically from cache and PokéAPI."""
    raw_str = str(move_name or "").lower().strip()
    slug = raw_str.replace(" ", "-")
    clean = raw_str.replace(" ", "").replace("-", "")
    
    # 1. Check competitive overrides dictionary first (has priority, secondary effects, and Gen 9 moves)
    for key in (slug, raw_str, clean):
        if key in EXHAUSTIVE_MOVES_DATA:
            d = dict(EXHAUSTIVE_MOVES_DATA[key])
            d["id"] = slug
            d["name"] = slug
            d["displayName"] = humanize_name(slug)
            return d

    # 2. Check moves_cache (588+ moves dynamically indexed) or CACHED_MOVES_JSON
    cached_obj = None
    for key in (slug, raw_str, clean):
        if key in moves_cache and isinstance(moves_cache[key], dict):
            cached_obj = moves_cache[key]
            break
        elif key in CACHED_MOVES_JSON and isinstance(CACHED_MOVES_JSON[key], dict):
            cached_obj = CACHED_MOVES_JSON[key]
            break

    # If still not found in local cache, dynamically fetch from PokéAPI cache
    if not cached_obj and get_move_cached:
        try:
            cached_obj = get_move_cached(slug)
        except Exception:
            pass

    if cached_obj and isinstance(cached_obj, dict):
        raw = cached_obj
        m_type = raw.get("type", {}).get("name") if isinstance(raw.get("type"), dict) else (raw.get("type") or "normal")
        m_class = raw.get("damage_class", {}).get("name") if isinstance(raw.get("damage_class"), dict) else (raw.get("damage_class") or "physical")
        meta = raw.get("meta") or {}
        ailment = (meta.get("ailment") or {}).get("name") if isinstance(meta.get("ailment"), dict) else meta.get("ailment")
        
        entry = {
            "id": slug,
            "name": slug,
            "displayName": humanize_name(slug),
            "power": raw.get("power") or 0,
            "accuracy": raw.get("accuracy") or 100,
            "type": str(m_type).lower(),
            "category": str(m_class).lower(),
            "priority": raw.get("priority", 0),
            "pp": raw.get("pp") or 15
        }
        if ailment and ailment not in ("none", "unknown"):
            entry["inflict_status"] = ailment
            entry["status_chance"] = meta.get("ailment_chance", 100) or 100
        if meta.get("drain", 0) > 0:
            entry["heal_drain"] = meta.get("drain") / 100.0
        if meta.get("healing", 0) > 0:
            entry["heal"] = meta.get("healing") / 100.0
        if meta.get("flinch_chance", 0) > 0:
            entry["flinch"] = meta.get("flinch_chance")
        if meta.get("crit_rate", 0) > 0:
            entry["high_crit"] = True

        # Dynamic stat changes parsing (e.g. Clanging Scales, Superpower, Overheat, Leaf Storm self-drops)
        meta_cat = (meta.get("category") or {}).get("name") if isinstance(meta.get("category"), dict) else meta.get("category")
        raw_stat_changes = raw.get("stat_changes") or []
        if raw_stat_changes and isinstance(raw_stat_changes, list):
            for sc in raw_stat_changes:
                if isinstance(sc, dict) and "change" in sc and "stat" in sc:
                    st_name = sc["stat"].get("name") if isinstance(sc["stat"], dict) else str(sc["stat"])
                    st_clean = st_name.lower().strip()
                    change = int(sc["change"])
                    target_name = (raw.get("target") or {}).get("name") if isinstance(raw.get("target"), dict) else raw.get("target")
                    if meta_cat == "damage-raise" or target_name in ("user", "users-field"):
                        if change < 0:
                            entry.setdefault("self_stat_drop", {})[st_clean] = change
                        elif change > 0:
                            entry.setdefault("self_boost", {})[st_clean] = change
                    elif meta_cat in ("damage-lower", "net-good-stats"):
                        entry.setdefault("stat_drops", {})[st_clean] = change

        return entry

    # 3. Fallback with sensible generic default
    return {
        "id": slug,
        "name": slug,
        "displayName": humanize_name(slug),
        "power": 75,
        "accuracy": 100,
        "type": "normal",
        "category": "physical",
        "priority": 0,
        "pp": 15
    }


# Standard Max Moves (Dynamax / G-Max for damaging & status moves)
STANDARD_MAX_MOVES: Dict[str, Dict[str, Any]] = {
    "normal": {"name": "Max Strike", "type": "normal", "target_stat_drop": {"speed": -1}, "desc": "Lowers target Speed by 1 stage."},
    "fire": {"name": "Max Flare", "type": "fire", "weather": "sun", "desc": "Sets harsh sunlight for 5 turns."},
    "water": {"name": "Max Geyser", "type": "water", "weather": "rain", "desc": "Sets rain for 5 turns."},
    "electric": {"name": "Max Lightning", "type": "electric", "terrain": "electric", "desc": "Sets Electric Terrain for 5 turns."},
    "grass": {"name": "Max Overgrowth", "type": "grass", "terrain": "grassy", "desc": "Sets Grassy Terrain for 5 turns."},
    "ice": {"name": "Max Hailstorm", "type": "ice", "weather": "snow", "desc": "Sets snow for 5 turns."},
    "fighting": {"name": "Max Knuckle", "type": "fighting", "self_stat_boost": {"attack": 1}, "desc": "Raises user Attack by 1 stage."},
    "poison": {"name": "Max Ooze", "type": "poison", "self_stat_boost": {"special-attack": 1}, "desc": "Raises user Special Attack by 1 stage."},
    "ground": {"name": "Max Quake", "type": "ground", "self_stat_boost": {"special-defense": 1}, "desc": "Raises user Special Defense by 1 stage."},
    "flying": {"name": "Max Airstream", "type": "flying", "self_stat_boost": {"speed": 1}, "desc": "Raises user Speed by 1 stage."},
    "psychic": {"name": "Max Mindstorm", "type": "psychic", "terrain": "psychic", "desc": "Sets Psychic Terrain for 5 turns."},
    "bug": {"name": "Max Flutterby", "type": "bug", "target_stat_drop": {"special-attack": -1}, "desc": "Lowers target Special Attack by 1 stage."},
    "rock": {"name": "Max Rockfall", "type": "rock", "weather": "sandstorm", "desc": "Sets a sandstorm for 5 turns."},
    "ghost": {"name": "Max Phantasm", "type": "ghost", "target_stat_drop": {"defense": -1}, "desc": "Lowers target Defense by 1 stage."},
    "dragon": {"name": "Max Wyrmwind", "type": "dragon", "target_stat_drop": {"attack": -1}, "desc": "Lowers target Attack by 1 stage."},
    "dark": {"name": "Max Darkness", "type": "dark", "target_stat_drop": {"special-defense": -1}, "desc": "Lowers target Special Defense by 1 stage."},
    "steel": {"name": "Max Steelspike", "type": "steel", "self_stat_boost": {"defense": 1}, "desc": "Raises user Defense by 1 stage."},
    "fairy": {"name": "Max Starfall", "type": "fairy", "terrain": "misty", "desc": "Sets Misty Terrain for 5 turns."}
}


def get_max_move_power(base_power: int, move_type: str) -> int:
    """Scales standard Max Move power based on base move power according to competitive Gen 8 rules."""
    if base_power <= 0:
        return 0
    if move_type in ("fighting", "poison"):
        if base_power <= 40:
            return 70
        elif base_power <= 55:
            return 75
        elif base_power <= 65:
            return 80
        elif base_power <= 75:
            return 85
        elif base_power <= 100:
            return 90
        elif base_power <= 140:
            return 95
        else:
            return 100
    else:
        if base_power <= 40:
            return 90
        elif base_power <= 50:
            return 100
        elif base_power <= 60:
            return 110
        elif base_power <= 70:
            return 120
        elif base_power <= 100:
            return 130
        elif base_power <= 130:
            return 140
        else:
            return 150


def get_max_move_details(species: str, move_name: str) -> Dict[str, Any]:
    """Computes the corresponding Max Move or exclusive G-Max Move for a given Pokémon and move."""
    meta = get_move_metadata(move_name)
    category = meta.get("category", "physical")
    base_type = meta.get("type", "normal").lower()
    base_power = meta.get("power", 0)

    # Status moves ALWAYS become Max Guard
    if category == "status":
        return {
            "id": "max-guard",
            "displayName": "Max Guard",
            "type": "normal",
            "category": "status",
            "power": 0,
            "accuracy": 100,
            "isMaxGuard": True,
            "isGmax": False,
            "description": "Protects the user from all incoming attacks, including Max Moves."
        }

    # Check for exclusive G-Max Move match
    clean_species = str(species or "").lower().strip().replace(" ", "-")
    gmax_meta = SPECIES_GMAX_MOVES.get(clean_species)
    if not gmax_meta:
        clean_variant = clean_species.replace("-gmax", "")
        gmax_meta = SPECIES_GMAX_MOVES.get(clean_variant) or SPECIES_GMAX_MOVES.get(clean_variant.split("-")[0])
    if gmax_meta and gmax_meta["base_type"] == base_type:
        calc_power = gmax_meta.get("fixed_power") or get_max_move_power(base_power, base_type)
        return {
            "id": gmax_meta["name"].lower().replace(" ", "-"),
            "displayName": gmax_meta["name"],
            "type": base_type,
            "category": category,
            "power": calc_power,
            "accuracy": 101,
            "isMaxGuard": False,
            "isGmax": True,
            "description": gmax_meta["desc"],
            "gmaxMeta": gmax_meta
        }

    # Standard Max Move
    std = STANDARD_MAX_MOVES.get(base_type, STANDARD_MAX_MOVES["normal"])
    calc_power = get_max_move_power(base_power, base_type)
    return {
        "id": std["name"].lower().replace(" ", "-"),
        "displayName": std["name"],
        "type": base_type,
        "category": category,
        "power": calc_power,
        "accuracy": 101,
        "isMaxGuard": False,
        "isGmax": False,
        "description": std["desc"],
        "stdMeta": std
    }


def get_type_multiplier(attacker_type: str, defender_types: List[str]) -> float:
    """Calculates product of effectiveness against target types (supports dual types)."""
    atk = str(attacker_type or "normal").lower()
    mult = 1.0
    for d_type in defender_types:
        df = str(d_type or "").lower()
        if atk in TYPE_CHART:
            # If defender type is specifically listed, multiply by that value
            if df in TYPE_CHART[atk]:
                mult *= TYPE_CHART[atk][df]
            # If not in table, standard neutral multiplier is 1.0
    return mult


def calculate_raw_stat(base: int, iv: int, ev: int, level: int, stat_name: str, nature: str) -> int:
    """Standard Generation 9 stat formula."""
    b = max(1, base)
    iv = max(0, min(31, iv))
    ev = max(0, min(252, ev))
    lvl = max(1, level)
    
    if stat_name.lower() in ("hp", "health"):
        if b == 1:
            return 1  # Shedinja
        return math.floor(((2 * b + iv + math.floor(ev / 4)) * lvl) / 100) + lvl + 10

    val = math.floor(((2 * b + iv + math.floor(ev / 4)) * lvl) / 100) + 5
    nat_dict = NATURE_MODIFIERS.get(nature.lower(), {})
    nat_mult = nat_dict.get(stat_name.lower(), 1.0)
    return math.floor(val * nat_mult)


class PokemonState:
    """Encapsulates active in-battle status of an individual Pokémon."""
    def __init__(self, data: Dict[str, Any], side_id: str, slot_index: int, level: int = 50):
        self.raw_data = data
        self.side_id = side_id
        self.slot_index = slot_index
        self.species = str(data.get("species") or data.get("name") or "pikachu").lower().strip().replace(" ", "-")
        self.display_name = humanize_name(data.get("displayName") or data.get("name") or self.species)
        self.level = level
        self.item = str(data.get("item") or "").lower().strip().replace(" ", "-")
        self.ability = str(data.get("ability") or "").lower().strip().replace(" ", "-")
        if not self.ability and self.species in pokemon_cache:
            p_cache = pokemon_cache[self.species]
            if isinstance(p_cache, dict) and "abilities" in p_cache:
                for ab in p_cache["abilities"]:
                    if not ab.get("is_hidden"):
                        self.ability = ab.get("ability", {}).get("name", "")
                        break
                if not self.ability and p_cache["abilities"]:
                    self.ability = p_cache["abilities"][0].get("ability", {}).get("name", "")

        self.tera_type = str(data.get("teraType") or "normal").lower().strip()
        self.nature = str(data.get("nature") or "serious").lower().strip()
        
        # Robust canonical typing resolution: dynamically fetched from Pokédex cache
        raw_types = data.get("types") or []
        if isinstance(raw_types, list) and len(raw_types) > 0 and raw_types != ["normal"]:
            self.types = [str(t).lower() for t in raw_types if t]
        else:
            self.types = get_pokemon_types(self.species)
            
        if not self.types:
            self.types = ["normal"]
            
        self.original_types = list(self.types)
        
        # Calculate stats dynamically using cache if not provided
        evs = data.get("evs") or {}
        ivs = data.get("ivs") or {}
        base = data.get("baseStats") or {}
        if not base and self.species in pokemon_cache:
            p_cache = pokemon_cache[self.species]
            if isinstance(p_cache, dict) and "stats" in p_cache:
                base = {
                    s["stat"]["name"]: s["base_stat"]
                    for s in p_cache["stats"]
                    if "stat" in s and "name" in s["stat"] and "base_stat" in s
                }
        
        self.stats: Dict[str, int] = {
            "hp": calculate_raw_stat(base.get("hp", 80), ivs.get("hp", 31), evs.get("hp", 0), level, "hp", self.nature),
            "attack": calculate_raw_stat(base.get("attack", 80), ivs.get("attack", 31), evs.get("attack", 0), level, "attack", self.nature),
            "defense": calculate_raw_stat(base.get("defense", 80), ivs.get("defense", 31), evs.get("defense", 0), level, "defense", self.nature),
            "special-attack": calculate_raw_stat(base.get("special-attack", 80), ivs.get("special-attack", 31), evs.get("special-attack", 0), level, "special-attack", self.nature),
            "special-defense": calculate_raw_stat(base.get("special-defense", 80), ivs.get("special-defense", 31), evs.get("special-defense", 0), level, "special-defense", self.nature),
            "speed": calculate_raw_stat(base.get("speed", 80), ivs.get("speed", 31), evs.get("speed", 0), level, "speed", self.nature)
        }
        self.max_hp = self.stats["hp"]
        if "currentHp" in data or "current_hp" in data:
            self.current_hp = min(self.max_hp, max(0, int(data.get("currentHp", data.get("current_hp", self.max_hp)))))
        else:
            self.current_hp = self.max_hp
        
        # Battle volatile / stage properties
        self.stages: Dict[str, int] = {
            "attack": 0, "defense": 0, "special-attack": 0, "special-defense": 0, "speed": 0, "accuracy": 0, "evasion": 0
        }
        # Non-volatile persistent status (burn, paralysis, sleep, poison, toxic, freeze) - PERSISTS TO BENCH!
        self.status: Optional[str] = None
        self.status_turns = 0

        # In-battle volatile status conditions (RESET ON SWITCH-OUT!)
        self.is_confused = False
        self.confusion_turns = 0
        self.is_infatuated = False
        self.taunt_turns = 0
        self.is_terastallized = False
        self.is_mega = False
        self.is_gmax = False
        self.gmax_turns = 0
        self.is_protected = False
        self.is_max_guarded = False
        self.is_flinched = False
        self.charging_move: Optional[str] = None
        self.semi_invulnerable: Optional[str] = None
        self.proto_boost_active: bool = False
        self.proto_boost_stat: Optional[str] = None
        self.choice_locked_move: Optional[str] = None
        self.turns_on_field = 0
        self.can_fake_out = False
        self.disguise_busted = False
        self.yawn_turns = 0
        self.protean_activated = False
        self.substitute_hp: int = 0
        self.consecutive_protect_count: int = 0
        self.times_hit_counter: int = int(data.get("times_hit_counter", data.get("timesHitCounter", 0)))
        self.revealed = False
        self.has_item = bool(self.item)
        self.item_revealed = False  # Hidden until used or knocked off
        self.moves: List[str] = [str(m).lower().strip() for m in data.get("moves") or ["tackle"] if m]
        self.pp: Dict[str, int] = {}
        for m in self.moves:
            meta = get_move_metadata(m)
            self.pp[m] = meta.get("pp", 15)

        self.sprite = data.get("sprite") or f"https://play.pokemonshowdown.com/sprites/gen5/{self.species}.png"
        self.sprite_shiny = data.get("spriteShiny") or self.sprite

    @property
    def is_fainted(self) -> bool:
        """Indicates whether this Pokémon's HP has been reduced to zero."""
        return self.current_hp <= 0

    def get_effective_stat(self, stat_name: str, field: Any = None) -> int:
        """Returns stat modified by stage multiplier, status, ability, and items."""
        base_val = self.stats.get(stat_name, 100)
        stage = max(-6, min(6, self.stages.get(stat_name, 0)))
        
        if stage >= 0:
            stage_mult = (2 + stage) / 2
        else:
            stage_mult = 2 / (2 - stage)
            
        val = float(base_val) * stage_mult

        # Guts boosts physical attack by 1.5x under ANY status condition, ignoring burn penalty
        if stat_name == "attack":
            if self.status is not None and self.ability == "guts":
                val *= 1.5
            elif self.status == "burn":
                val *= 0.5

        # Paralysis drops speed by 50%
        if stat_name == "speed" and self.status == "paralysis":
            val *= 0.5

        # Item boosts
        if self.has_item:
            if stat_name == "attack" and self.item == "choice-band":
                val *= 1.5
            elif stat_name == "special-attack" and self.item == "choice-specs":
                val *= 1.5
            elif stat_name == "speed" and self.item == "choice-scarf":
                val *= 1.5
            elif stat_name == "special-defense" and self.item == "assault-vest":
                val *= 1.5

        # Weather / Ability / Tailwind synergies
        if field:
            eff_w = field.get_effective_weather() if hasattr(field, "get_effective_weather") else getattr(field, "weather", None)

            # Dynamic Speed: Tailwind immediately doubles speed for affected side
            if stat_name == "speed":
                if self.side_id == "side1" and getattr(field, "side1", None) and getattr(field.side1, "tailwind_turns", 0) > 0:
                    val *= 2.0
                elif self.side_id == "side2" and getattr(field, "side2", None) and getattr(field.side2, "tailwind_turns", 0) > 0:
                    val *= 2.0

            if stat_name == "speed" and eff_w == "rain" and self.ability == "swift-swim":
                val *= 2.0
            elif stat_name == "speed" and eff_w == "sun" and self.ability == "chlorophyll":
                val *= 2.0
            elif stat_name == "speed" and eff_w == "sandstorm" and self.ability == "sand-rush":
                val *= 2.0
            elif stat_name == "speed" and eff_w == "snow" and self.ability == "slush-rush":
                val *= 2.0
            elif stat_name == "special-defense" and eff_w == "sandstorm" and "rock" in self.types:
                val *= 1.5
            elif stat_name == "defense" and eff_w == "snow" and "ice" in self.types:
                val *= 1.5

        # Protosynthesis / Quark Drive / Booster Energy
        if getattr(self, "proto_boost_active", False) and getattr(self, "proto_boost_stat", None) == stat_name:
            val *= 1.5 if stat_name == "speed" else 1.3
        elif field:
            eff_w = field.get_effective_weather() if hasattr(field, "get_effective_weather") else getattr(field, "weather", None)
            if self.ability == "protosynthesis" and eff_w == "sun" and getattr(self, "proto_boost_stat", None) == stat_name:
                val *= 1.5 if stat_name == "speed" else 1.3
            elif self.ability == "quark-drive" and field.terrain == "electric" and getattr(self, "proto_boost_stat", None) == stat_name:
                val *= 1.5 if stat_name == "speed" else 1.3

        return max(1, math.floor(val))

    def get_highest_stat_name(self) -> str:
        """Determines highest raw stat excluding HP for Paradox / Protosynthesis."""
        candidates = ["attack", "defense", "special-attack", "special-defense", "speed"]
        best_stat = "attack"
        best_val = -1
        for s in candidates:
            v = self.stats.get(s, 0)
            if v > best_val:
                best_val = v
                best_stat = s
        return best_stat

    def check_booster_energy_activation(self, field=None) -> Optional[Dict[str, Any]]:
        """Activates Booster Energy on Paradox Pokémon, consuming the item on entry to boost highest stat."""
        if not self.has_item or self.item != "booster-energy":
            return None
        from utils.special_pokemon import get_special_category, PARADOX
        is_paradox = (get_special_category(self.species) == "paradox") or (self.species in PARADOX) or (self.ability in ("protosynthesis", "quark-drive"))
        if not is_paradox:
            return None

        # Don't consume if Sun or Electric Terrain is already activating the ability
        if field:
            if self.ability == "protosynthesis" and getattr(field, "weather", None) == "sun":
                return None
            if self.ability == "quark-drive" and getattr(field, "terrain", None) == "electric":
                return None

        self.has_item = False
        self.item = None
        self.item_revealed = True
        self.proto_boost_active = True
        self.proto_boost_stat = self.get_highest_stat_name()
        ab_name = self.ability if self.ability in ("protosynthesis", "quark-drive") else "Protosynthesis"
        return {
            "stat": self.proto_boost_stat,
            "ability": ab_name
        }

    def modify_stage(self, stat: str, delta: int) -> int:
        """Modifies a stat stage within [-6, +6], returning the actual change."""
        current = self.stages.get(stat, 0)
        target = max(-6, min(6, current + delta))
        actual = target - current
        self.stages[stat] = target
        return actual

    def reset_volatiles(self):
        """Clears all temporary in-battle volatile states and stat boosts when switching out."""
        self.stages = {k: 0 for k in self.stages}
        self.is_protected = False
        self.is_max_guarded = False
        self.is_flinched = False
        self.is_confused = False
        self.confusion_turns = 0
        self.is_infatuated = False
        self.taunt_turns = 0
        self.charging_move = None
        self.semi_invulnerable = None
        self.choice_locked_move = None
        self.proto_boost_active = False
        self.proto_boost_stat = None
        self.turns_on_field = 0
        self.can_fake_out = False
        self.yawn_turns = 0
        self.protean_activated = False
        self.substitute_hp = 0
        self.consecutive_protect_count = 0
        if self.is_gmax:
            self.is_gmax = False
            self.gmax_turns = 0
            self.max_hp = max(1, math.floor(self.max_hp / 1.5))
            self.current_hp = min(self.max_hp, self.current_hp)
        if not self.is_terastallized and not self.is_mega:
            self.types = list(self.original_types)

    def terastallize(self) -> str:
        """Activates Terastallization, changing defensive types to tera_type."""
        if not self.is_terastallized and not self.is_mega and not self.is_gmax:
            self.is_terastallized = True
            self.types = [self.tera_type]
            return self.tera_type
        return ""

    @property
    def can_mega(self) -> bool:
        """Determines if the Pokémon is eligible to Mega Evolve (requires holding the matching Mega Stone, or Rayquaza with Dragon Ascent)."""
        if self.is_mega or self.is_gmax or self.is_terastallized:
            return False
        target_mega = self.get_mega_species_for_item()
        if not target_mega:
            return False
        mega_info = ensure_mega_in_registry(target_mega) or MEGA_EVOLUTIONS.get(target_mega) or MEGA_EVOLUTIONS.get(f"{self.species}-{target_mega}")
        return mega_info is not None

    def get_mega_species_for_item(self) -> Optional[str]:
        """Resolves the specific Mega Evolution form granted by the Pokémon's held Mega Stone (or Dragon Ascent for Rayquaza)."""
        clean_sp = self.species.lower().strip()
        clean_item = str(self.item or "").lower().strip().replace(" ", "-")

        # Rayquaza canonical exception: requires Dragon Ascent move, no Mega Stone
        if clean_sp == "rayquaza":
            if any(m.lower().strip() in ("dragon-ascent", "dragonascent") for m in self.moves):
                return "rayquaza-mega"
            return None

        if not self.has_item or not clean_item:
            return None

        # Check explicit mapping in MEGA_STONE_MAP (syncing from cache if needed)
        global MEGA_STONE_MAP
        sp_stones = MEGA_STONE_MAP.get(clean_sp)
        if not sp_stones:
            MEGA_STONE_MAP = get_mega_stone_map()
            sp_stones = MEGA_STONE_MAP.get(clean_sp)

        if sp_stones:
            if clean_item in sp_stones:
                return sp_stones[clean_item]
            clean_item_no_dash = clean_item.replace("-", "")
            if clean_item_no_dash in sp_stones:
                return sp_stones[clean_item_no_dash]

        # Dynamic fallback: check if item matches [species]ite or [species]ite-[variant]
        item_no_dash = clean_item.replace("-", "")
        for mega_slug in MEGA_EVOLUTIONS:
            if mega_slug.startswith(f"{clean_sp}-mega"):
                suffix = mega_slug.replace(f"{clean_sp}-mega", "").replace("-", "")
                expected_stone_base = clean_sp.replace("-", "") + "ite" + suffix
                if item_no_dash == expected_stone_base:
                    return mega_slug

        return None

    @property
    def can_gmax(self) -> bool:
        """Determines if the Pokémon is eligible to Gigantamax via Pokédex dynamic registry."""
        if self.is_mega or self.is_gmax or self.is_terastallized:
            return False
        return (self.species in GMAX_SPECIES) or (f"{self.species}-gmax" in GMAX_SPECIES) or (self.species in SPECIES_GMAX_MOVES_MAP)

    def mega_evolve(self, preferred_mega: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Mega Evolves the Pokémon into the specific form dictated by its held Mega Stone."""
        if not self.can_mega:
            return None
        target_mega = self.get_mega_species_for_item()
        if not target_mega:
            return None
        mega_info = ensure_mega_in_registry(target_mega) or MEGA_EVOLUTIONS.get(target_mega) or MEGA_EVOLUTIONS.get(f"{self.species}-{target_mega}")
        if not mega_info:
            return None
        self.is_mega = True
        self.species = mega_info.get("mega_species", target_mega)
        self.display_name = mega_info.get("name", f"Mega {self.display_name}")
        self.types = list(mega_info.get("types", self.types))
        self.original_types = list(self.types)
        if mega_info.get("ability"):
            self.ability = mega_info["ability"]
        if mega_info.get("sprite"):
            self.sprite = mega_info["sprite"]
        for stat, boost in mega_info.get("stat_boosts", {}).items():
            st_key = stat.lower()
            if st_key in self.stats:
                self.stats[st_key] += boost
        return mega_info

    def gigantamax(self) -> Optional[Dict[str, Any]]:
        """Activates Gigantamax / Dynamax (1.5x max HP & current HP boost, lasts 3 turns)."""
        if self.is_mega or self.is_gmax or self.is_terastallized:
            return None
        self.is_gmax = True
        self.gmax_turns = 3
        old_max = self.max_hp
        self.max_hp = math.floor(self.max_hp * 1.5)
        hp_gain = self.max_hp - old_max
        self.current_hp = min(self.max_hp, self.current_hp + hp_gain)
        gmax_info = GMAX_SPECIES.get(self.species) or GMAX_SPECIES.get(f"{self.species}-gmax")
        if gmax_info:
            self.display_name = gmax_info.get("gmax_name", f"Gigantamax {humanize_name(self.species)}")
            if gmax_info.get("sprite"):
                self.sprite = gmax_info["sprite"]
            return gmax_info
        else:
            self.display_name = f"Gigantamax {self.display_name}"
            return {"gmax_name": self.display_name, "gmax_move": "Max Strike"}

    def all_moves_depleted(self) -> bool:
        """Returns True if this Pokémon has 0 PP left across all known moves."""
        return len(self.moves) > 0 and all(self.pp.get(m, 0) <= 0 for m in self.moves)

    @property
    def is_struggling(self) -> bool:
        """Returns True if this Pokémon has no usable moves and is forced into Struggle."""
        if not self.moves or self.is_fainted:
            return False

        if self.is_gmax:
            return False

        is_taunted = getattr(self, "taunt_turns", 0) > 0
        is_vest = self.has_item and self.item == "assault-vest"

        # If choice-locked, the ONLY candidate move is the locked move
        if self.has_item and self.item in ("choice-band", "choice-specs", "choice-scarf") and self.choice_locked_move:
            locked_m = self.choice_locked_move
            if self.pp.get(locked_m, 0) <= 0:
                return True
            cat = get_move_metadata(locked_m).get("category", "physical")
            if (is_taunted or is_vest) and cat == "status":
                return True
            return False

        # Otherwise, check if ANY move is usable
        for m in self.moves:
            if self.pp.get(m, 0) <= 0:
                continue
            cat = get_move_metadata(m).get("category", "physical")
            if (is_taunted or is_vest) and cat == "status":
                continue
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serializable representation for UI with rich move details and ability/item clarity."""
        detailed_moves = []
        for m in self.moves:
            meta = get_move_metadata(m)
            max_move_details = get_max_move_details(self.species, m)
            m_pwr = meta.get("power", 0)
            if m.lower() == "rage-fist":
                m_pwr = min(350, 50 + (getattr(self, "times_hit_counter", 0) * 50))
            elif m.lower() == "last-respects":
                fainted = 0
                if hasattr(self, "side") and self.side:
                    fainted = sum(1 for ally in self.side.team if ally.is_fainted)
                m_pwr = 50 + (fainted * 20)
            detailed_moves.append({
                "id": m,
                "displayName": meta.get("displayName") or humanize_name(m),
                "type": meta.get("type", "normal"),
                "category": meta.get("category", "physical"),
                "power": m_pwr,
                "accuracy": meta.get("accuracy", 100),
                "pp": self.pp.get(m, meta.get("pp", 15)),
                "maxPp": meta.get("pp", 15),
                "maxMove": max_move_details
            })

        return {
            "species": self.species,
            "displayName": self.display_name,
            "level": self.level,
            "types": self.types,
            "originalTypes": self.original_types,
            "currentHp": self.current_hp,
            "maxHp": self.max_hp,
            "hpPercent": round((self.current_hp / self.max_hp) * 100, 1) if self.max_hp else 0,
            "status": self.status,
            "statusDisplayName": self.status.upper() if self.status else None,
            "isConfused": self.is_confused,
            "confusionTurns": self.confusion_turns,
            "isInfatuated": self.is_infatuated,
            "tauntTurns": self.taunt_turns,
            "stages": dict(self.stages),
            "isTerastallized": self.is_terastallized,
            "teraType": self.tera_type,
            "isMega": self.is_mega,
            "isGmax": self.is_gmax,
            "gmaxTurns": self.gmax_turns,
            "canMega": self.can_mega,
            "megaDetails": ensure_mega_in_registry(self.get_mega_species_for_item()) or MEGA_EVOLUTIONS.get(self.get_mega_species_for_item() or ""),
            "targetMegaSpecies": self.get_mega_species_for_item(),
            "targetMegaName": ((ensure_mega_in_registry(self.get_mega_species_for_item()) or MEGA_EVOLUTIONS.get(self.get_mega_species_for_item() or "")) or {}).get("name"),
            "availableMegas": [ensure_mega_in_registry(self.get_mega_species_for_item())] if self.get_mega_species_for_item() and (ensure_mega_in_registry(self.get_mega_species_for_item()) or self.get_mega_species_for_item() in MEGA_EVOLUTIONS) else [],
            "canGmax": self.can_gmax,
            "gmaxDetails": GMAX_SPECIES.get(self.species) or GMAX_SPECIES.get(f"{self.species}-gmax"),
            "item": self.item,
            "itemDisplayName": humanize_name(self.item) if self.item else "None",
            "hasItem": self.has_item,
            "itemRevealed": self.item_revealed,
            "ability": self.ability,
            "abilityDisplayName": humanize_name(self.ability) if self.ability else "None",
            "moves": self.moves,
            "moveDetails": detailed_moves,
            "pp": self.pp,
            "sprite": self.sprite,
            "chargingMove": self.charging_move,
            "semiInvulnerable": self.semi_invulnerable,
            "protoBoostActive": getattr(self, "proto_boost_active", False),
            "protoBoostStat": getattr(self, "proto_boost_stat", None),
            "choiceLockedMove": getattr(self, "choice_locked_move", None),
            "isStruggling": self.is_struggling,
            "disguiseBusted": getattr(self, "disguise_busted", False),
            "yawnTurns": getattr(self, "yawn_turns", 0),
            "isDrowsy": getattr(self, "yawn_turns", 0) > 0,
            "substituteHp": getattr(self, "substitute_hp", 0),
            "hasSubstitute": getattr(self, "substitute_hp", 0) > 0,
            "consecutiveProtectCount": getattr(self, "consecutive_protect_count", 0),
            "timesHitCounter": getattr(self, "times_hit_counter", 0),
            "turnsOnField": self.turns_on_field,
            "canFakeOut": self.can_fake_out,
            "isFainted": self.is_fainted,
            "revealed": getattr(self, "revealed", False),
            "slotIndex": self.slot_index
        }


class BattleSide:
    """Represents one combatant side (Player or AI)."""
    def __init__(self, side_id: str, name: str, team_raw: List[Dict[str, Any]], level: int = 50, is_ai: bool = False, difficulty: int = 50):
        self.side_id = side_id
        self.name = name
        self.is_ai = is_ai
        self.difficulty = difficulty
        self.team: List[PokemonState] = [PokemonState(p, side_id, idx, level) for idx, p in enumerate(team_raw)]
        for p in self.team:
            p.side = self
            if p.has_item:
                target = p.get_mega_species_for_item()
                if target:
                    ensure_mega_in_registry(target)
        if self.team:
            self.team[0].revealed = True
        self.active_index = 0
        self.tailwind_turns = 0
        self.reflect_turns = 0
        self.light_screen_turns = 0
        self.aurora_veil_turns = 0
        self.hazards = {"stealth_rock": False, "spikes": 0, "toxic_spikes": 0, "sticky_web": False, "steelsurge": False}
        self.gmax_wildfire_turns = 0
        self.gmax_cannonade_turns = 0
        self.gmax_vinelash_turns = 0
        self.gmax_volcalith_turns = 0
        self.omni_used = False
        self.omni_mechanic: Optional[str] = None

    @property
    def tera_used(self) -> bool:
        """Indicates whether this side has activated its once-per-battle generational gimmick."""
        return self.omni_used

    @tera_used.setter
    def tera_used(self, val: bool):
        """Sets gimmick usage and defaults to Terastallization if not specified."""
        self.omni_used = val
        if val and not self.omni_mechanic:
            self.omni_mechanic = "tera"

    @property
    def active_pokemon(self) -> Optional[PokemonState]:
        """Returns the currently active Pokémon on field for this combatant side."""
        if 0 <= self.active_index < len(self.team):
            return self.team[self.active_index]
        return None

    @property
    def has_alive_pokemon(self) -> bool:
        """True if this side has at least one conscious Pokémon remaining."""
        return any(not p.is_fainted for p in self.team)

    def get_alive_bench_indices(self) -> List[int]:
        """Returns team slot indices of conscious teammates currently on the bench."""
        return [idx for idx, p in enumerate(self.team) if not p.is_fainted and idx != self.active_index]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes battle side state, hazards, screens, and active roster for UI/telemetry."""
        return {
            "sideId": self.side_id,
            "name": self.name,
            "isAi": self.is_ai,
            "difficulty": self.difficulty,
            "active": self.active_pokemon.to_dict() if self.active_pokemon else None,
            "activeIndex": self.active_index,
            "team": [p.to_dict() for p in self.team],
            "hazards": self.hazards,
            "tailwind": self.tailwind_turns,
            "gmaxWildfire": self.gmax_wildfire_turns,
            "gmaxCannonade": self.gmax_cannonade_turns,
            "gmaxVinelash": self.gmax_vinelash_turns,
            "gmaxVolcalith": self.gmax_volcalith_turns,
            "screens": {
                "reflect": self.reflect_turns,
                "lightScreen": self.light_screen_turns,
                "auroraVeil": self.aurora_veil_turns
            },
            "teraUsed": self.omni_used,
            "omniUsed": self.omni_used,
            "omniMechanic": self.omni_mechanic
        }


class BattleSimulator:
    """Core turn-by-turn simulation engine."""
    def __init__(self, team1_data: List[Dict[str, Any]], team2_data: List[Dict[str, Any]], 
                 name1: str = "Player", name2: str = "Championship AI",
                 is_ai_side1: bool = False, difficulty1: int = 50,
                 is_ai_side2: bool = True, difficulty2: int = 80,
                 ruleset: str = "singles", level: int = 50):
        self.ruleset = ruleset
        self.level = level
        self.side1 = BattleSide("side1", name1, team1_data, level, is_ai_side1, difficulty1)
        self.side2 = BattleSide("side2", name2, team2_data, level, is_ai_side2, difficulty2)
        
        # Field conditions
        self.weather = "none"  # 'rain', 'sun', 'sandstorm', 'snow'
        self.weather_turns = 0
        self.terrain = "none"  # 'grassy', 'electric', 'psychic', 'misty'
        self.terrain_turns = 0
        self.trick_room_turns = 0
        self.gravity_turns = 0
        self.pending_switch: Dict[str, bool] = {"side1": False, "side2": False}
        self.current_turn_actions: Dict[str, Dict[str, Any]] = {}
        self.moved_this_turn: Set[str] = set()
        self.switched_in_this_turn: Set[str] = set()
        
        self.turn = 1
        self.battle_log: List[Dict[str, Any]] = []
        self.winner: Optional[str] = None
        self.is_finished = False

        # Apply initial switch-in procs
        self.trigger_entry_effects(self.side1.active_pokemon, self.side1, self.side2)
        self.trigger_entry_effects(self.side2.active_pokemon, self.side2, self.side1)

    def is_grounded(self, p: Optional[PokemonState]) -> bool:
        """Calculates whether a Pokémon is grounded on terrain and entry hazards."""
        if not p:
            return False
        if self.gravity_turns > 0:
            return True
        if p.has_item and p.item == "iron-ball":
            return True
        if "flying" in p.types:
            return False
        if p.ability == "levitate":
            return False
        if p.has_item and p.item == "air-balloon":
            return False
        return True

    def log(self, event_type: str, text: str, side_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """Appends an event to the battle log."""
        self.battle_log.append({
            "turn": self.turn,
            "type": event_type,
            "text": text,
            "sideId": side_id,
            "details": details or {}
        })

    def is_weather_suppressed(self) -> bool:
        """Returns True if any active non-fainted Pokémon on the field has Cloud Nine or Air Lock."""
        for side in (self.side1, self.side2):
            if side and side.active_pokemon and not side.active_pokemon.is_fainted:
                if side.active_pokemon.ability in ("cloud-nine", "air-lock"):
                    return True
        return False

    def get_effective_weather(self) -> str:
        """Returns active weather, or 'none' if suppressed by Cloud Nine or Air Lock."""
        if self.is_weather_suppressed():
            return "none"
        return self.weather or "none"

    def handle_crash_damage(self, user_poke: PokemonState, user_side: BattleSide, move_name: str) -> bool:
        """Applies 50% max HP crash recoil damage when crash moves miss, are protected, or hit immune targets."""
        clean_move = str(move_name or "").lower().strip().replace(" ", "-")
        if clean_move in ("high-jump-kick", "jump-kick", "supercell-slam"):
            crash_dmg = max(1, math.floor(user_poke.max_hp * 0.5))
            user_poke.current_hp = max(0, user_poke.current_hp - crash_dmg)
            self.log("damage", f"💥 {user_poke.display_name} kept going and crashed! (-{crash_dmg} HP)", user_side.side_id, {
                "damage": crash_dmg, "recoil": True
            })
            if user_poke.is_fainted:
                self.log("faint", f"☠️ {user_poke.display_name} fainted!", user_side.side_id, {
                    "species": user_poke.species, "displayName": user_poke.display_name
                })
                self.prompt_replacement(user_side)
            return True
        return False

    def is_move_targeting_opponent(self, move_name: str, m_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Determines whether a move directly targets an opposing Pokémon.
        Self-targeting moves (Bulk Up, Swords Dance, Recover, Substitute, etc.) and
        field-targeting moves (Rain Dance, Tailwind, Stealth Rock, Reflect, etc.) do NOT target
        an opposing Pokémon and therefore CANNOT be blocked by Protect, Detect, or semi-invulnerability!
        """
        if m_data is None:
            m_data = get_move_metadata(move_name)

        move_lower = move_name.lower().strip().replace(" ", "-")
        category = m_data.get("category", "physical")

        # All damaging attacks target the opposing active Pokémon
        if category in ("physical", "special"):
            return True

        # Hazards target the opposing field, NOT the opposing Pokémon; Protect does not block hazards!
        if m_data.get("hazard"):
            return False

        # Weather, terrain, room, and team field effects
        if m_data.get("weather") or m_data.get("terrain") or m_data.get("field_effect"):
            return False
        if move_lower in (
            "reflect", "light-screen", "aurora-veil", "safeguard", "mist",
            "tailwind", "trick-room", "wonder-room", "magic-room", "gravity"
        ):
            return False

        # Self-targeting status moves (Substitute, healing, resting, team heals, self-pivots, protections)
        if move_lower in (
            "substitute", "shed-tail", "rest", "wish", "heal-bell", "aromatherapy",
            "baton-pass", "teleport", "chilly-reception", "protect", "detect", "endure"
        ):
            return False
        if move_lower in PROTECT_MOVES:
            return False

        # Targeted status moves: inflict status, target stat drops, confusion, item swap, taunt, encore, yawn, etc.
        if (m_data.get("inflict_status") or 
            m_data.get("stat_drops") or 
            m_data.get("inflict_confusion") or 
            m_data.get("item_swap") or 
            m_data.get("taunt") or 
            m_data.get("encore") or
            move_lower in (
                "taunt", "encore", "yawn", "attract", "leech-seed", "trick", "switcheroo", 
                "will-o-wisp", "thunder-wave", "toxic", "spore", "sleep-powder", "hypnosis", 
                "glare", "poison-powder", "stun-spore", "confuse-ray", "sweet-kiss", 
                "supersonic", "teeter-dance", "screech", "fake-tears", "metal-sound", 
                "charm", "feather-dance", "scary-face", "parting-shot", "string-shot",
                "disable", "torment", "spite", "gastro-acid", "soak", "heal-block", "mean-look"
            )):
            return True

        # If it has self_boost, heal, or self_stat_drop, it targets the user!
        if m_data.get("self_boost") or m_data.get("heal") or m_data.get("self_stat_drop"):
            return False

        # Fallback based on PokeAPI target field if present
        target_field = str(m_data.get("target") or "").lower()
        if target_field in ("user", "user-and-allies", "all-allies", "entire-field", "users-field", "opponents-field"):
            return False

        return True

    def determine_multi_hit_count(self, user_poke: PokemonState, move_lower: str, m_data: Dict[str, Any]) -> int:
        """Determines the number of strikes for multi-hit moves, evaluating Skill Link and Loaded Dice."""
        if m_data.get("hits"):
            return int(m_data["hits"])

        # Fixed 2-hit moves
        if move_lower in (
            "dragon-darts", "dual-wingbeat", "double-hit", "bonemerang", "twin-beam",
            "double-kick", "gear-grind", "dual-chop", "twineedle"
        ):
            return 2

        # Fixed 3-hit moves
        if move_lower in ("surging-strikes", "triple-dive"):
            return 3

        # Population Bomb (hits up to 10 times)
        if move_lower == "population-bomb":
            if user_poke.ability == "skill-link":
                return 10
            if user_poke.has_item and user_poke.item == "loaded-dice":
                return random.choice([4, 5, 6, 7, 8, 9, 10, 10, 10, 10])
            hits = 0
            for _ in range(10):
                if random.random() < 0.90:
                    hits += 1
                else:
                    break
            return max(1, hits)

        # 2 to 5 multi-hit moves
        if move_lower in (
            "bullet-seed", "icicle-spear", "rock-blast", "scale-shot", "tail-slap",
            "arm-thrust", "pin-missile", "bone-rush", "spike-cannon", "fury-swipes",
            "comet-punch", "barrage", "double-slap"
        ):
            # Skill Link guarantees maximum 5 hits!
            if user_poke.ability == "skill-link":
                return 5
            # Loaded Dice guarantees 4 or 5 hits (50/50 chance in Gen 9)!
            if user_poke.has_item and user_poke.item == "loaded-dice":
                return random.choice([4, 5])

            # Standard Gen 5-9 distribution: 35% 2 hits, 35% 3 hits, 15% 4 hits, 15% 5 hits
            roll = random.random()
            if roll < 0.35:
                return 2
            elif roll < 0.70:
                return 3
            elif roll < 0.85:
                return 4
            else:
                return 5

        return 1

    def check_move_accuracy(self, user_poke: PokemonState, opp_poke: Optional[PokemonState], move_name: str, m_data: Dict[str, Any]) -> bool:
        """Determines if a move hits, accounting for weather bypasses, abilities, items, and stages."""
        move_lower = move_name.lower().strip()

        # 1. Moves that inherently bypass accuracy checks (never miss)
        never_miss_moves = {
            "aerial-ace", "aura-sphere", "swift", "magical-leaf", "shock-wave",
            "flower-trick", "kowtow-cleave", "clear-smog", "disarming-voice",
            "shadow-punch", "vital-throw", "magnet-bomb", "smart-strike", "feint-attack"
        }
        if m_data.get("never_miss") or move_lower in never_miss_moves:
            return True

        # Toxic accuracy bypass: If used by a Poison-type Pokémon, Toxic cannot miss!
        if move_lower == "toxic" and "poison" in user_poke.types:
            return True

        # Non-targeting or self-targeting status moves bypass accuracy
        if m_data.get("category") == "status":
            if not self.is_move_targeting_opponent(move_lower, m_data):
                return True

        # 2. No Guard guarantees 100% accuracy for both attacker and target
        if user_poke.ability == "no-guard" or (opp_poke and opp_poke.ability == "no-guard"):
            return True

        # 3. Weather-specific bypasses & adjustments
        eff_weather = self.get_effective_weather()
        if eff_weather == "rain":
            # In rain, Hurricane and Thunder cannot miss!
            if move_lower in ("hurricane", "thunder"):
                return True
        elif eff_weather in ("snow", "hail"):
            # In snow/hail, Blizzard cannot miss!
            if move_lower == "blizzard":
                return True

        # 4. Base accuracy retrieval
        raw_acc = m_data.get("accuracy", 100)
        if raw_acc is True or raw_acc is None or raw_acc <= 0 or raw_acc >= 1000:
            return True

        base_acc = float(raw_acc)

        # In harsh sunlight, Hurricane and Thunder accuracy drops to 50%
        if eff_weather == "sun" and move_lower in ("hurricane", "thunder"):
            base_acc = 50.0

        # 5. Attacker ability modifiers
        if user_poke.ability == "compound-eyes":
            base_acc *= 1.3
        elif user_poke.ability == "victory-star":
            base_acc *= 1.1

        # 6. Attacker item modifiers
        if user_poke.has_item and user_poke.item == "wide-lens":
            base_acc *= 1.1

        # 7. Defender ability evasion modifiers
        if opp_poke:
            if opp_poke.ability == "sand-veil" and eff_weather == "sandstorm":
                base_acc *= 0.8
            elif opp_poke.ability == "snow-cloak" and eff_weather in ("snow", "hail"):
                base_acc *= 0.8

        # 8. Stat stage modifiers (Accuracy & Evasion)
        acc_stage = user_poke.stages.get("accuracy", 0)
        eva_stage = opp_poke.stages.get("evasion", 0) if opp_poke else 0

        # Abilities that ignore evasion: Keen Eye, Mind's Eye, Unaware
        if user_poke.ability in ("keen-eye", "minds-eye", "unaware") and eva_stage > 0:
            eva_stage = 0

        net_stage = max(-6, min(6, acc_stage - eva_stage))
        if net_stage >= 0:
            stage_mult = (3.0 + net_stage) / 3.0
        else:
            stage_mult = 3.0 / (3.0 - net_stage)

        final_acc = base_acc * stage_mult

        if final_acc >= 100.0:
            return True

        return random.uniform(0.0, 100.0) <= final_acc

    def check_status_berry(self, poke: Optional[PokemonState], side: BattleSide) -> bool:
        """Checks and consumes Lum Berry or status-specific berries (Chesto, Rawst, Pecha, Cheri, Aspear, Persim)."""
        if not poke or poke.is_fainted or not poke.has_item:
            return False

        item_name = str(poke.item or "").lower().strip()
        cured = False
        cured_msg = ""

        # Lum Berry cures any non-volatile status OR confusion
        if item_name == "lum-berry":
            if poke.status:
                old_st = poke.status
                poke.status = None
                poke.status_turns = 0
                cured = True
                cured_msg = f"cured its {humanize_name(old_st)}"
            if poke.is_confused:
                poke.is_confused = False
                poke.confusion_turns = 0
                cured = True
                cured_msg = f"{cured_msg} and confusion" if cured_msg else "snapped out of confusion"

            if cured:
                poke.has_item = False
                poke.item = None
                poke.item_revealed = True
                self.log("item", f"🌿 [{poke.display_name}'s Lum Berry] Consumed Lum Berry and {cured_msg}!", side.side_id, {"item": "Lum Berry"})
                return True

        # Chesto Berry cures sleep
        elif item_name == "chesto-berry" and poke.status == "sleep":
            poke.status = None
            poke.status_turns = 0
            poke.has_item = False
            poke.item = None
            poke.item_revealed = True
            self.log("item", f"🍒 [{poke.display_name}'s Chesto Berry] Consumed Chesto Berry and woke up from sleep!", side.side_id, {"item": "Chesto Berry"})
            return True

        # Rawst Berry cures burn
        elif item_name == "rawst-berry" and poke.status == "burn":
            poke.status = None
            poke.status_turns = 0
            poke.has_item = False
            poke.item = None
            poke.item_revealed = True
            self.log("item", f"🍓 [{poke.display_name}'s Rawst Berry] Consumed Rawst Berry and healed its burn!", side.side_id, {"item": "Rawst Berry"})
            return True

        # Pecha Berry cures poison
        elif item_name == "pecha-berry" and poke.status in ("poison", "toxic"):
            poke.status = None
            poke.status_turns = 0
            poke.has_item = False
            poke.item = None
            poke.item_revealed = True
            self.log("item", f"🍑 [{poke.display_name}'s Pecha Berry] Consumed Pecha Berry and was cured of poison!", side.side_id, {"item": "Pecha Berry"})
            return True

        # Cheri Berry cures paralysis
        elif item_name == "cheri-berry" and poke.status == "paralysis":
            poke.status = None
            poke.status_turns = 0
            poke.has_item = False
            poke.item = None
            poke.item_revealed = True
            self.log("item", f"🍒 [{poke.display_name}'s Cheri Berry] Consumed Cheri Berry and was cured of paralysis!", side.side_id, {"item": "Cheri Berry"})
            return True

        # Aspear Berry cures freeze
        elif item_name == "aspear-berry" and poke.status == "freeze":
            poke.status = None
            poke.status_turns = 0
            poke.has_item = False
            poke.item = None
            poke.item_revealed = True
            self.log("item", f"🍐 [{poke.display_name}'s Aspear Berry] Consumed Aspear Berry and defrosted!", side.side_id, {"item": "Aspear Berry"})
            return True

        # Persim Berry cures confusion
        elif item_name == "persim-berry" and poke.is_confused:
            poke.is_confused = False
            poke.confusion_turns = 0
            poke.has_item = False
            poke.item = None
            poke.item_revealed = True
            self.log("item", f"🫐 [{poke.display_name}'s Persim Berry] Consumed Persim Berry and snapped out of confusion!", side.side_id, {"item": "Persim Berry"})
            return True

        return False

    def check_white_herb(self, poke: Optional[PokemonState], side: BattleSide) -> bool:
        """Checks and consumes White Herb if any stat stage is below 0, restoring all negative stat stages to 0."""
        if not poke or poke.is_fainted or not poke.has_item:
            return False

        item_name = str(poke.item or "").lower().strip()
        if item_name != "white-herb":
            return False

        has_neg = False
        restored_stats = []
        for stat, val in poke.stages.items():
            if val < 0:
                poke.stages[stat] = 0
                has_neg = True
                restored_stats.append(format_stat_name(stat))

        if has_neg:
            poke.has_item = False
            poke.item = None
            poke.item_revealed = True
            stats_str = ", ".join(restored_stats)
            self.log("item", f"🌿 [{poke.display_name}'s White Herb] Consumed White Herb to restore its lowered stats ({stats_str}) back to normal!", side.side_id, {
                "item": "white-herb",
                "restoredStats": restored_stats
            })
            return True
        return False

    def trigger_entry_effects(self, p: Optional[PokemonState], my_side: BattleSide, opp_side: BattleSide):
        """Processes switch-in abilities (Intimidate, Drizzle, etc.) and hazards."""
        if not p or p.is_fainted:
            return

        p.revealed = True
        p.turns_on_field = 0
        p.can_fake_out = True
        opp_active = opp_side.active_pokemon

        # 1. Entry Hazards (if not holding Heavy-Duty Boots and not Flying/Levitating for Ground hazards)
        is_grounded = self.is_grounded(p) and p.item != "heavy-duty-boots"
        if p.item != "heavy-duty-boots":
            # Stealth Rock
            if my_side.hazards.get("stealth_rock"):
                sr_mult = get_type_multiplier("rock", p.types)
                sr_dmg = math.floor(p.max_hp * (0.125 * sr_mult))
                if sr_dmg > 0:
                    p.current_hp = max(0, p.current_hp - sr_dmg)
                    self.log("hazard", f"Pointed stones dug into {p.display_name}! (-{sr_dmg} HP)", my_side.side_id)
            
            # Spikes
            spikes_count = my_side.hazards.get("spikes", 0)
            if spikes_count > 0 and is_grounded:
                sp_pct = 0.125 if spikes_count == 1 else (0.166 if spikes_count == 2 else 0.25)
                sp_dmg = math.floor(p.max_hp * sp_pct)
                p.current_hp = max(0, p.current_hp - sp_dmg)
                self.log("hazard", f"{p.display_name} was hurt by spikes! (-{sp_dmg} HP)", my_side.side_id)

            # Sticky Web
            if my_side.hazards.get("sticky_web") and is_grounded:
                p.modify_stage("speed", -1)
                self.log("hazard", f"{p.display_name} was caught in a sticky web! Spe fell!", my_side.side_id)
                self.check_white_herb(p, my_side)

            # Toxic Spikes
            tspikes = my_side.hazards.get("toxic_spikes", 0)
            if is_grounded:
                if "poison" in p.types:
                    if tspikes > 0:
                        my_side.hazards["toxic_spikes"] = 0
                        self.log("hazard", f"✨ {p.display_name} absorbed the toxic spikes!", my_side.side_id)
                elif "steel" not in p.types and p.status is None:
                    if tspikes >= 2:
                        p.status = "toxic"
                        p.status_turns = 1
                        self.log("hazard", f"⚠️ {p.display_name} was badly poisoned by toxic spikes!", my_side.side_id, {"status": "toxic"})
                    elif tspikes == 1:
                        p.status = "poison"
                        p.status_turns = 1
                        self.log("hazard", f"⚠️ {p.display_name} was poisoned by toxic spikes!", my_side.side_id, {"status": "poison"})
                    self.check_status_berry(p, my_side)

            # G-Max Steelsurge (Steel-type hazard)
            if my_side.hazards.get("steelsurge"):
                ss_mult = get_type_multiplier("steel", p.types)
                ss_dmg = math.floor(p.max_hp * (0.125 * ss_mult))
                if ss_dmg > 0:
                    p.current_hp = max(0, p.current_hp - ss_dmg)
                    self.log("hazard", f"⚙️ Sharp steel spikes dug into {p.display_name}! (-{ss_dmg} HP)", my_side.side_id)

        # Check if Pokémon fainted from entry hazard damage before any ability or item activation!
        # Canonical rule: If a Pokémon faints upon switching in due to hazard damage,
        # its switch-in ability (Intimidate, Drizzle, etc.) DOES NOT PROC and a replacement is prompted!
        if p.is_fainted:
            self.log("faint", f"☠️ {p.display_name} fainted from hazard damage upon switching in!", my_side.side_id, {
                "species": p.species,
                "displayName": p.display_name,
                "hazardFaint": True
            })
            self.prompt_replacement(my_side)
            return

        # 2. Abilities on Entry
        ab = p.ability
        if ab == "intimidate" and opp_active and not opp_active.is_fainted:
            if opp_active.has_item and opp_active.item == "clear-amulet":
                self.log("item", f"🛡️ [{opp_active.display_name}'s Clear Amulet] Protected its stats from being lowered!", opp_side.side_id)
            elif opp_active.ability in ("clear-body", "white-smoke", "hyper-cutter", "full-metal-body"):
                self.log("ability", f"{p.display_name}'s Intimidate was blocked by {opp_active.display_name}'s {humanize_name(opp_active.ability)}!", my_side.side_id)
            elif opp_active.ability == "defiant":
                opp_active.modify_stage("attack", 2)
                self.log("ability", f"✨ [{opp_active.display_name}'s Defiant] Atk rose sharply (+2) from Intimidate!", opp_side.side_id)
            elif opp_active.ability == "competitive":
                opp_active.modify_stage("special-attack", 2)
                self.log("ability", f"✨ [{opp_active.display_name}'s Competitive] SpA rose sharply (+2) from Intimidate!", opp_side.side_id)
            elif opp_active.ability in ("guard-dog", "oblivious", "scrappy"):
                self.log("ability", f"✨ [{opp_active.display_name}'s {humanize_name(opp_active.ability)}] Immune to Intimidate!", opp_side.side_id)
            else:
                opp_active.modify_stage("attack", -1)
                self.log("ability", f"✨ [{p.display_name}'s Intimidate] {opp_active.display_name}'s Atk fell!", my_side.side_id, {"ability": "Intimidate", "stat": "attack", "delta": -1})
                self.check_white_herb(opp_active, opp_side)

        elif ab == "drizzle":
            self.weather = "rain"
            self.weather_turns = 5
            self.log("weather", f"🌧️ [{p.display_name}'s Drizzle] Downpour commenced! It started to rain!", my_side.side_id, {"weather": "rain"})

        elif ab == "drought":
            self.weather = "sun"
            self.weather_turns = 5
            self.log("weather", f"☀️ [{p.display_name}'s Drought] The sunlight turned harsh!", my_side.side_id, {"weather": "sun"})

        elif ab == "snow-warning":
            self.weather = "snow"
            self.weather_turns = 5
            self.log("weather", f"❄️ [{p.display_name}'s Snow Warning] It started to snow!", my_side.side_id, {"weather": "snow"})

        elif ab == "sand-stream":
            self.weather = "sandstorm"
            self.weather_turns = 5
            self.log("weather", f"🌪️ [{p.display_name}'s Sand Stream] A sandstorm brewed!", my_side.side_id, {"weather": "sandstorm"})

        elif ab == "grassy-surge":
            self.terrain = "grassy"
            self.terrain_turns = 5
            self.log("terrain", f"🌱 [{p.display_name}'s Grassy Surge] An emerald lawn carpeted the battlefield!", my_side.side_id, {"terrain": "grassy"})

        elif ab == "electric-surge":
            self.terrain = "electric"
            self.terrain_turns = 5
            self.log("terrain", f"⚡ [{p.display_name}'s Electric Surge] An electric field electrified the battlefield!", my_side.side_id, {"terrain": "electric"})

        elif ab == "psychic-surge":
            self.terrain = "psychic"
            self.terrain_turns = 5
            self.log("terrain", f"🔮 [{p.display_name}'s Psychic Surge] The battlefield got weird with psychic terrain!", my_side.side_id, {"terrain": "psychic"})

        elif ab == "pressure":
            self.log("ability", f"✨ [{p.display_name}'s Pressure] {p.display_name} is exerting its pressure!", my_side.side_id)

        elif ab == "supreme-overlord":
            fainted_count = sum(1 for ally in my_side.team if ally.is_fainted)
            if fainted_count > 0:
                boost_pct = min(5, fainted_count) * 10
                self.log("ability", f"✨ [{p.display_name}'s Supreme Overlord] {p.display_name} gained strength from the fallen! (+{boost_pct}% power)", my_side.side_id, {
                    "ability": "Supreme Overlord", "fainted_allies": fainted_count, "boost": boost_pct
                })

        # Booster Energy and Protosynthesis / Quark Drive on Entry
        booster_proc = p.check_booster_energy_activation(self)
        if booster_proc:
            self.log("item", f"🔋 [{p.display_name}'s Booster Energy] Consumed its Booster Energy to activate {humanize_name(booster_proc['ability'])}! Its {format_stat_name(booster_proc['stat'])} was heightened!", my_side.side_id, {
                "item": "Booster Energy", "stat": booster_proc["stat"], "species": p.species
            })
        elif p.ability == "protosynthesis" and self.get_effective_weather() == "sun":
            p.proto_boost_stat = p.get_highest_stat_name()
            self.log("ability", f"☀️ [{p.display_name}'s Protosynthesis] The harsh sunlight activated Protosynthesis! Its {format_stat_name(p.proto_boost_stat)} was heightened!", my_side.side_id)
        elif p.ability == "quark-drive" and self.terrain == "electric":
            p.proto_boost_stat = p.get_highest_stat_name()
            self.log("ability", f"⚡ [{p.display_name}'s Quark Drive] The electric terrain activated Quark Drive! Its {format_stat_name(p.proto_boost_stat)} was heightened!", my_side.side_id)

        # Check status berry on entry (e.g. Lum Berry, Chesto Berry)
        self.check_status_berry(p, my_side)

    def calculate_move_damage(self, attacker: PokemonState, defender: PokemonState, move_name: str) -> Tuple[int, Dict[str, Any]]:
        """Detailed Gen 9 damage calculation with Body Press Defense scaling and complete type/ability interactions."""
        # G-Max / Dynamax Move transformation
        if attacker.is_gmax:
            max_move = get_max_move_details(attacker.species, move_name)
            if max_move.get("isMaxGuard"):
                return 0, {"typeMult": 1.0, "isCrit": False, "effectiveness": "status", "category": "status", "moveType": "normal"}
            power = max_move.get("power", 130)
            move_type = max_move.get("type", "normal").lower()
            category = max_move.get("category", "physical")
            m_data = {"power": power, "type": move_type, "category": category}
        else:
            m_data = get_move_metadata(move_name)
            category = m_data.get("category", "physical")
            if category == "status":
                return 0, {"typeMult": 1.0, "isCrit": False, "effectiveness": "status", "category": "status", "moveType": m_data.get("type", "normal")}

            power = m_data.get("power", 75)
            move_type = m_data.get("type", "normal").lower()

        # Dynamic move: Weather Ball (in active weather: doubles power to 100 and changes type!)
        if move_name.lower() == "weather-ball":
            if self.weather == "rain":
                move_type = "water"
                power = 100
            elif self.weather == "sun":
                move_type = "fire"
                power = 100
            elif self.weather == "sandstorm":
                move_type = "rock"
                power = 100
            elif self.weather == "snow":
                move_type = "ice"
                power = 100
            else:
                move_type = "normal"
                power = 50

        # Dynamic move: Terrain Pulse (in terrain with grounded attacker: doubles power to 100 and changes type!)
        is_grounded_attacker = self.is_grounded(attacker)
        if move_name.lower() == "terrain-pulse" and is_grounded_attacker:
            if self.terrain == "electric":
                move_type = "electric"
                power = 100
            elif self.terrain == "grassy":
                move_type = "grass"
                power = 100
            elif self.terrain == "psychic":
                move_type = "psychic"
                power = 100
            elif self.terrain == "misty":
                move_type = "fairy"
                power = 100

        # Expanding Force (in Psychic Terrain with grounded user: 1.5x power from 80 to 120!)
        if move_name.lower() == "expanding-force" and self.terrain == "psychic" and self.is_grounded(attacker):
            power = 120

        # Semi-invulnerable target interactions: Earthquake/Magnitude doubles vs Dig, Surf/Whirlpool vs Dive, Gust/Twister vs Fly/Bounce
        clean_mv = move_name.lower().strip()
        if getattr(defender, "semi_invulnerable", None) == "dig" and clean_mv in ("earthquake", "magnitude"):
            power *= 2
        elif getattr(defender, "semi_invulnerable", None) == "dive" and clean_mv in ("surf", "whirlpool"):
            power *= 2
        elif getattr(defender, "semi_invulnerable", None) in ("fly", "bounce") and clean_mv in ("gust", "twister"):
            power *= 2

        # Dynamic move: Tera Blast (matches user's Tera type when Terastallized and becomes physical if Attack > SpA)
        if move_name.lower() == "tera-blast" and attacker.is_terastallized:
            move_type = attacker.tera_type
            if attacker.get_effective_stat("attack", self) > attacker.get_effective_stat("special-attack", self):
                category = "physical"

        # Dynamic move: Ivy Cudgel (type changes according to Ogerpon's mask)
        if move_name.lower() in ("ivy-cudgel", "ivycudgel"):
            if attacker.item == "hearthflame-mask" or "hearthflame" in attacker.species.lower():
                move_type = "fire"
            elif attacker.item == "wellspring-mask" or "wellspring" in attacker.species.lower():
                move_type = "water"
            elif attacker.item == "cornerstone-mask" or "cornerstone" in attacker.species.lower():
                move_type = "rock"
            else:
                move_type = "grass"

        # Dynamic move: Rage Fist (50 Base Power, increases by +50 BP each time the user has been hit by an attack, up to 350 BP max)
        if clean_mv == "rage-fist":
            hits = getattr(attacker, "times_hit_counter", 0)
            power = min(350, 50 + (hits * 50))

        # Dynamic move: Last Respects (50 Base Power, increases by +20 BP for each fainted ally on user's team)
        if clean_mv == "last-respects":
            atk_side = self.side1 if attacker.side_id == "side1" else self.side2
            fainted_allies = sum(1 for p in atk_side.team if p.is_fainted)
            power = 50 + (fainted_allies * 20)

        # Iron Fist ability: boosts punching moves by 20% (1.2x)
        if attacker.ability == "iron-fist" and clean_mv in PUNCHING_MOVES:
            power = math.floor(power * 1.2)

        # Check Body Press: calculates using Defense stat instead of Attack!
        if m_data.get("uses_defense") or move_name.lower() == "body-press":
            atk = attacker.get_effective_stat("defense", self)
            defn = defender.get_effective_stat("defense", self)
        elif category == "physical":
            atk = attacker.get_effective_stat("attack", self)
            defn = defender.get_effective_stat("defense", self)
        else:
            atk = attacker.get_effective_stat("special-attack", self)
            defn = defender.get_effective_stat("special-defense", self)

        # Check Knock Off item bonus
        if move_name == "knock-off" and defender.has_item:
            power = math.floor(power * 1.5)

        # Check Facade / Guts boost
        if move_name == "facade" and attacker.status in ("burn", "paralysis", "poison", "toxic"):
            power *= 2

        # 1. Base Damage Formula
        lvl = attacker.level
        base_dmg = math.floor(math.floor(math.floor(2 * lvl / 5 + 2) * power * atk / defn) / 50) + 2

        # 2. Weather Modifier
        weather_mult = 1.0
        eff_weather = self.get_effective_weather()
        if eff_weather == "rain":
            if move_type == "water":
                weather_mult = 1.5
            elif move_type == "fire":
                weather_mult = 0.5
        elif eff_weather == "sun":
            if move_type == "fire":
                weather_mult = 1.5
            elif move_type == "water":
                weather_mult = 1.5 if move_name.lower() == "hydro-steam" else 0.5

        # 3. Terrain Modifier
        terrain_mult = 1.0
        is_grounded_attacker = self.is_grounded(attacker)
        is_grounded_defender = self.is_grounded(defender)

        if is_grounded_attacker:
            if self.terrain == "grassy" and move_type == "grass":
                terrain_mult = 1.3
            elif self.terrain == "electric" and move_type == "electric":
                terrain_mult = 1.3
            elif self.terrain == "psychic" and move_type == "psychic":
                terrain_mult = 1.3

        if is_grounded_defender:
            if self.terrain == "grassy" and move_name.lower() in ("earthquake", "bulldoze", "magnitude"):
                terrain_mult *= 0.5
            elif self.terrain == "misty" and move_type == "dragon":
                terrain_mult *= 0.5

        # 4. Critical Hit
        crit_rate = 0.0416  # 1/24
        if m_data.get("always_crit") or (move_name.lower() in ("wicked-blow", "surging-strikes", "flower-trick")):
            is_crit = True
        else:
            is_crit = random.random() < crit_rate

        crit_mult = 1.5 if is_crit else 1.0

        # 5. Random Factor (0.85 to 1.00)
        random_mult = random.uniform(0.85, 1.00)

        # 6. STAB (Same Type Attack Bonus)
        is_stab = move_type in attacker.types
        if is_stab:
            stab_mult = 2.0 if attacker.ability == "adaptability" else 1.5
        else:
            stab_mult = 1.0

        # 7. Type Effectiveness (Exact match against dual-types)
        if move_name.lower() == "struggle":
            # Struggle deals typeless damage, hitting all Pokémon (including Ghost) for neutral 1.0x
            type_mult = 1.0
        elif move_name.lower() == "freeze-dry":
            # Freeze-Dry is 2.0x super-effective against Water types
            type_mult = 1.0
            for d_type in defender.types:
                df = str(d_type or "").lower()
                if df == "water":
                    type_mult *= 2.0
                elif df in TYPE_CHART.get("ice", {}):
                    type_mult *= TYPE_CHART["ice"][df]
        else:
            type_mult = get_type_multiplier(move_type, defender.types)

        # Check ability and item immunities
        if move_type == "ground" and not self.is_grounded(defender):
            type_mult = 0.0
        elif move_type == "fire" and defender.ability in ("flash-fire", "well-baked-body"):
            type_mult = 0.0
        elif move_type == "water" and defender.ability in ("water-absorb", "storm-drain", "dry-skin"):
            type_mult = 0.0
        elif move_type == "electric" and defender.ability in ("volt-absorb", "lightning-rod", "motor-drive"):
            type_mult = 0.0
        elif move_type == "grass" and defender.ability == "sap-sipper":
            type_mult = 0.0
        elif move_type == "ground" and defender.ability == "earth-eater":
            type_mult = 0.0

        # If completely immune, damage is zero
        if type_mult == 0.0:
            return 0, {
                "typeMult": 0.0,
                "isCrit": False,
                "category": category,
                "moveType": move_type
            }

        # 8. Item Modifier
        item_mult = 1.0
        if attacker.has_item and attacker.item == "life-orb":
            item_mult = 1.3

        # 9. Spread Move Modifier in Doubles (0.75x if >1 alive defenders on opposing side, 1.0x if 1)
        spread_mult = 1.0
        is_spread = m_data.get("spread", False) or m_data.get("spread_all", False)
        if move_name.lower() == "expanding-force" and self.terrain == "psychic" and self.is_grounded(attacker):
            is_spread = True

        def_side = self.side2 if defender.side_id == "side2" else self.side1
        if self.ruleset == "doubles" and is_spread:
            alive_defenders = sum(1 for p in def_side.team if not p.is_fainted)
            if alive_defenders > 1:
                spread_mult = 0.75
            else:
                spread_mult = 1.0

        # 10. Supreme Overlord (+10% damage per fainted ally on attacker's team)
        supreme_mult = 1.0
        if attacker.ability == "supreme-overlord":
            atk_side = self.side1 if attacker.side_id == "side1" else self.side2
            fainted_count = sum(1 for p in atk_side.team if p.is_fainted)
            supreme_mult = 1.0 + (0.1 * min(5, fainted_count))

        # Fixed damage attacks (ignore defense, critical hits, weather, random variance, and type effectiveness)
        clean_mv = move_name.lower().strip()
        is_fixed = False
        if clean_mv == "final-gambit":
            total_damage = attacker.current_hp
            is_crit = False
            is_fixed = True
        elif clean_mv in ("seismic-toss", "night-shade"):
            total_damage = attacker.level
            is_crit = False
            is_fixed = True
        elif clean_mv in ("super-fang", "ruination", "natures-madness"):
            total_damage = max(1, math.floor(defender.current_hp / 2))
            is_crit = False
            is_fixed = True
        elif clean_mv == "endeavor":
            total_damage = max(0, defender.current_hp - attacker.current_hp)
            is_crit = False
            is_fixed = True
        else:
            total_damage = math.floor(base_dmg * weather_mult * terrain_mult * crit_mult * random_mult * stab_mult * type_mult * item_mult * spread_mult * supreme_mult)

        # Multiscale / Shadow Shield (halves damage taken when at full HP - does not apply to fixed damage)
        had_multiscale = False
        if not is_fixed and defender.ability in ("multiscale", "shadow-shield") and defender.current_hp == defender.max_hp:
            if attacker.ability not in ("mold-breaker", "teravolt", "turboblaze"):
                total_damage = math.floor(total_damage * 0.5)
                had_multiscale = True

        # Screens & Aurora Veil (halves damage; Infiltrator and Crits bypass screens - does not apply to fixed damage)
        had_screen = False
        if not is_fixed and attacker.ability != "infiltrator" and not is_crit:
            screen_mult = 0.5 if self.ruleset == "singles" else 0.66
            if category == "physical" and (def_side.reflect_turns > 0 or def_side.aurora_veil_turns > 0):
                total_damage = math.floor(total_damage * screen_mult)
                had_screen = True
            elif category == "special" and (def_side.light_screen_turns > 0 or def_side.aurora_veil_turns > 0):
                total_damage = math.floor(total_damage * screen_mult)
                had_screen = True
        
        # Focus Sash / Sturdy check
        focus_sash_used = False
        if defender.current_hp == defender.max_hp and total_damage >= defender.current_hp:
            if defender.has_item and defender.item == "focus-sash":
                total_damage = defender.current_hp - 1
                focus_sash_used = True
            elif defender.ability == "sturdy":
                total_damage = defender.current_hp - 1
                focus_sash_used = True

        info = {
            "basePower": power,
            "typeMult": type_mult,
            "isCrit": is_crit,
            "category": category,
            "moveType": move_type,
            "fixedDamage": is_fixed,
            "hadMultiscale": had_multiscale,
            "hadScreen": had_screen,
            "hadSpreadReduction": (spread_mult < 1.0),
            "hadSupremeOverlord": (supreme_mult > 1.0),
            "focusSashUsed": focus_sash_used
        }
        return max(1 if type_mult > 0 else 0, total_damage), info

    def execute_turn(self, action1: Dict[str, Any], action2: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Executes one full turn given actions for both sides.
        """
        if self.is_finished:
            return self.battle_log

        # Clear volatile turn states (Protect, Max Guard, Flinch)
        for s in (self.side1, self.side2):
            if s.active_pokemon:
                s.active_pokemon.is_protected = False
                s.active_pokemon.is_max_guarded = False
                s.active_pokemon.is_flinched = False

        # 1. Handle Omni Ring declarations (Terastallization, Mega Evolution, Gigantamax) before move execution
        for side, action in ((self.side1, action1), (self.side2, action2)):
            if action.get("type") == "move" and not side.omni_used and side.active_pokemon:
                omni_choice = action.get("omni") or ("tera" if action.get("tera") else None)
                if omni_choice == "mega":
                    pref_mega = action.get("mega") or action.get("preferredMega")
                    mega_res = side.active_pokemon.mega_evolve(preferred_mega=pref_mega)
                    if mega_res:
                        side.omni_used = True
                        side.omni_mechanic = "mega"
                        self.log("omni", f"🧬 [{side.name}] {side.active_pokemon.display_name} activated Omni Ring and Mega Evolved!", side.side_id, {"omni": "mega", "species": side.active_pokemon.species})
                elif omni_choice == "gmax":
                    gmax_res = side.active_pokemon.gigantamax()
                    if gmax_res:
                        side.omni_used = True
                        side.omni_mechanic = "gmax"
                        self.log("omni", f"⚡ [{side.name}] {side.active_pokemon.display_name} activated Omni Ring and Gigantamaxed into a towering titan!", side.side_id, {"omni": "gmax", "species": side.active_pokemon.species})
                elif omni_choice == "tera":
                    t = side.active_pokemon.terastallize()
                    if t:
                        side.omni_used = True
                        side.omni_mechanic = "tera"
                        self.log("tera", f"💎 [{side.name}] {side.active_pokemon.display_name} Terastallized into pure {humanize_name(t)}!", side.side_id, {"teraType": t, "omni": "tera"})

        # 2. Determine execution order and bind each action strictly to the current active Pokémon
        actor1 = self.side1.active_pokemon
        actor2 = self.side2.active_pokemon

        # If a combatant is currently charging a 2-turn move (e.g. Electro Shot, Solar Beam, Phantom Force), lock into it
        if actor1 and actor1.charging_move:
            action1 = {"type": "move", "move": actor1.charging_move}
        if actor2 and actor2.charging_move:
            action2 = {"type": "move", "move": actor2.charging_move}

        def get_combatant_speed_prio(s: BattleSide, act: Dict[str, Any], actor: Optional[PokemonState]) -> Tuple[int, int]:
            """Calculates action priority bracket (e.g. +7 switch, +1 Sucker Punch) and effective Speed."""
            if not actor or actor.is_fainted:
                return -999, 0
            prio = 7 if act.get("type") == "switch" else self.get_move_priority(actor, act.get("move") or act.get("move_id") or act.get("moveId") or act.get("moveName"))
            spe = actor.get_effective_stat("speed", self)
            return prio, spe

        prio1, spe1 = get_combatant_speed_prio(self.side1, action1, actor1)
        prio2, spe2 = get_combatant_speed_prio(self.side2, action2, actor2)

        if self.trick_room_turns > 0:
            speed_faster = (spe1 < spe2)
        else:
            speed_faster = (spe1 > spe2)

        if prio1 > prio2:
            order = [(self.side1, self.side2, action1, actor1), (self.side2, self.side1, action2, actor2)]
        elif prio2 > prio1:
            order = [(self.side2, self.side1, action2, actor2), (self.side1, self.side2, action1, actor1)]
        else:
            if speed_faster:
                order = [(self.side1, self.side2, action1, actor1), (self.side2, self.side1, action2, actor2)]
            elif spe2 > spe1:
                order = [(self.side2, self.side1, action2, actor2), (self.side1, self.side2, action1, actor1)]
            else:
                coin = random.random() < 0.5
                order = [(self.side1, self.side2, action1, actor1), (self.side2, self.side1, action2, actor2)] if coin else [(self.side2, self.side1, action2, actor2), (self.side1, self.side2, action1, actor1)]

        # Store actions and initialize turn tracking for Sucker Punch & Fake Out
        self.current_turn_actions = {
            self.side1.side_id: dict(action1 or {}),
            self.side2.side_id: dict(action2 or {})
        }
        self.moved_this_turn = set()
        self.switched_in_this_turn = set()

        # 3. Execute actions in calculated order
        for user_side, opp_side, act, actor in order:
            if self.is_finished:
                break
            
            # An action can ONLY be executed by the Pokémon that queued it!
            # If that Pokémon fainted earlier in this turn (e.g. Diancie fainted to Earthquake),
            # its action is completely voided and any replacement sent out CANNOT attack on this turn!
            if not actor or actor.is_fainted or user_side.active_pokemon != actor:
                continue

            user_poke = user_side.active_pokemon
            opp_poke = opp_side.active_pokemon

            if not user_poke or user_poke.is_fainted:
                continue

            if act.get("type") == "switch":
                target_idx = (
                    act.get("targetIndex") if act.get("targetIndex") is not None
                    else (act.get("target_slot") if act.get("target_slot") is not None
                    else (act.get("targetSlot") if act.get("targetSlot") is not None
                    else act.get("slot", 0)))
                )
                self.perform_switch(user_side, opp_side, target_idx, is_replacement=False)
            elif act.get("type") == "move":
                move_name = act.get("move") or act.get("move_id") or act.get("moveId") or act.get("moveName") or "tackle"
                pivot_idx = act.get("pivotTargetIndex") or act.get("pivot_target_index")
                self.perform_move(user_side, opp_side, move_name, pivot_target_index=pivot_idx)

            self.moved_this_turn.add(user_side.side_id)

        # 4. End-of-turn residual effects
        self.resolve_end_of_turn()

        # 5. Check victory
        self.check_faint_and_win()

        self.turn += 1
        return self.battle_log

    def get_move_priority(self, p: Optional[PokemonState], move_name: Optional[str]) -> int:
        """Determines the net priority of a move considering base priority, Prankster, Gale Wings, Grassy Glide, and Triage."""
        if not move_name or not p:
            return 0
        m_data = get_move_metadata(move_name)
        if p.is_gmax:
            if m_data.get("category") == "status":
                return 4  # Max Guard priority +4
            return 0

        base_prio = m_data.get("priority", 0)
        
        # Prankster ability gives +1 to status moves
        if p.ability == "prankster" and m_data.get("category") == "status":
            base_prio += 1

        # Gale Wings gives +1 to flying moves at full HP
        if p.ability == "gale-wings" and m_data.get("type") == "flying" and p.current_hp == p.max_hp:
            base_prio += 1

        # Grassy Glide in Grassy Terrain
        if move_name.lower() == "grassy-glide" and self.terrain == "grassy":
            base_prio += 1

        # Triage gives +3 priority to healing moves
        if p.ability == "triage" and (m_data.get("heal") or m_data.get("heal_drain") or move_name.lower() in ("recover", "roost", "synthesis", "soft-boiled", "slack-off", "milk-drink", "moonlight", "morning-sun", "shore-up", "strengthsap", "draining-kiss", "giga-drain", "drain-punch", "horn-leech")):
            base_prio += 3

        return base_prio

    def perform_switch(self, user_side: BattleSide, opp_side: BattleSide, new_index: int, is_replacement: bool = False, is_pivot: bool = False, is_baton_pass: bool = False, passed_substitute: int = 0):
        """Swaps active Pokémon, resets temporary volatiles, applies Natural Cure/Regenerator, and triggers switch-in procs."""
        if new_index < 0 or new_index >= len(user_side.team):
            return
        old_p = user_side.active_pokemon
        new_p = user_side.team[new_index]
        if new_p.is_fainted:
            return

        passed_sub = passed_substitute
        passed_stages = None

        # 1. Handle outgoing Pokémon
        if old_p:
            # Natural Cure cures non-volatile status upon switch-out
            if old_p.ability == "natural-cure" and old_p.status is not None:
                cured_st = old_p.status
                old_p.status = None
                old_p.status_turns = 0
                self.log("ability", f"✨ [{old_p.display_name}'s Natural Cure] Cured its {cured_st} upon switching out!", user_side.side_id)

            # Regenerator restores 1/3 max HP upon switch-out
            if old_p.ability == "regenerator" and not old_p.is_fainted:
                regen = math.floor(old_p.max_hp / 3)
                old_p.current_hp = min(old_p.max_hp, old_p.current_hp + regen)
                self.log("ability", f"✨ [{old_p.display_name}'s Regenerator] Restored HP upon switching out! (+{regen} HP)", user_side.side_id)

            if is_baton_pass:
                passed_stages = dict(old_p.stages)
                if getattr(old_p, "substitute_hp", 0) > 0:
                    passed_sub = old_p.substitute_hp

            # Volatiles (Confusion, Infatuation, Taunt, Boosts/Drops, Protect, Flinch, Substitute) reset to 0
            old_p.reset_volatiles()

        user_side.active_index = new_index
        self.pending_switch[user_side.side_id] = False
        self.switched_in_this_turn.add(user_side.side_id)
        new_p.revealed = True
        new_p.can_fake_out = True
        new_p.turns_on_field = 0
        old_name = old_p.display_name if old_p else "Pokémon"

        if is_baton_pass and passed_stages:
            new_p.stages = dict(passed_stages)
            self.log("stat", f"✨ [{new_p.display_name}] Received Baton Pass stat boosts!", user_side.side_id)

        if passed_sub > 0:
            new_p.substitute_hp = passed_sub
            self.log("stat", f"🧸 [{new_p.display_name}] Inherited the substitute decoy! (Sub HP: {new_p.substitute_hp})", user_side.side_id)
        else:
            new_p.substitute_hp = 0

        if is_replacement or (old_p and old_p.is_fainted):
            self.log("switch", f"➡️ [{user_side.name}] Sent out {new_p.display_name}!", user_side.side_id, {
                "sentOut": new_p.display_name,
                "sentOutSpecies": new_p.species,
                "newIndex": new_index,
                "isReplacement": True
            })
        elif is_pivot:
            self.log("switch", f"🔄 [{user_side.name}] {old_name} pivoted out! Go, {new_p.display_name}!", user_side.side_id, {
                "withdrew": old_name,
                "sentOut": new_p.display_name,
                "sentOutSpecies": new_p.species,
                "newIndex": new_index,
                "isPivot": True
            })
        else:
            self.log("switch", f"🔄 [{user_side.name}] Withdrew {old_name}! Go, {new_p.display_name}!", user_side.side_id, {
                "withdrew": old_name,
                "sentOut": new_p.display_name,
                "sentOutSpecies": new_p.species,
                "newIndex": new_index,
                "isReplacement": False
            })

        self.trigger_entry_effects(new_p, user_side, opp_side)

    def perform_move(self, user_side: BattleSide, opp_side: BattleSide, move_name: str, pivot_target_index: Optional[int] = None):
        """Resolves move accuracy, damage, on-hit abilities (e.g. Stamina), and faints."""
        user_poke = user_side.active_pokemon
        opp_poke = opp_side.active_pokemon
        if not user_poke or user_poke.is_fainted:
            return

        # Check status berry on user before move execution (e.g. Lum/Chesto wake up)
        self.check_status_berry(user_poke, user_side)

        m_data = get_move_metadata(move_name)
        max_info = get_max_move_details(user_poke.species, move_name) if user_poke.is_gmax else None
        if user_poke.is_gmax and max_info:
            m_human = max_info["displayName"]
        else:
            m_human = m_data.get("displayName") or humanize_name(move_name)

        move_lower = move_name.lower().strip()

        # Check if Pokémon is forced into Struggle (0 PP across all moves, or choice-locked into a 0 PP move, or no usable moves)
        is_choice_locked_0pp = (
            not user_poke.is_gmax and user_poke.has_item and
            user_poke.item in ("choice-band", "choice-specs", "choice-scarf") and
            user_poke.choice_locked_move and
            user_poke.pp.get(user_poke.choice_locked_move, 0) <= 0
        )
        if move_lower == "struggle" or user_poke.is_struggling or is_choice_locked_0pp:
            move_name = "struggle"
            move_lower = "struggle"
            m_data = {
                "id": "struggle",
                "name": "struggle",
                "displayName": "Struggle",
                "power": 50,
                "accuracy": 100,
                "type": "normal",
                "category": "physical",
                "priority": 0,
                "recoil": 0.25,
                "pp": 1
            }
            m_human = "Struggle"
        elif not user_poke.is_gmax and user_poke.pp.get(move_lower, 1) <= 0:
            self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} tried to use {m_human}!", user_side.side_id)
            self.log("fail", f"❌ There's no PP left for this move!", user_side.side_id, {"failed": True})
            return

        # Status check (Sleep, Freeze, Paralysis)
        if user_poke.status == "sleep":
            user_poke.status_turns -= 1
            if user_poke.status_turns <= 0:
                user_poke.status = None
                self.log("status", f"💤 {user_poke.display_name} woke up!", user_side.side_id)
            else:
                self.log("status", f"💤 {user_poke.display_name} is fast asleep!", user_side.side_id)
                return

        if user_poke.status == "freeze":
            thawing_moves = {"flare-blitz", "flame-wheel", "sacred-fire", "scald", "steam-eruption", "pyro-ball", "burn-up"}
            if move_lower in thawing_moves:
                user_poke.status = None
                self.log("status", f"🔥 [{user_poke.display_name}] {m_human}'s heat thawed it out!", user_side.side_id)
            elif random.random() < 0.2:
                user_poke.status = None
                self.log("status", f"❄️ {user_poke.display_name} thawed out!", user_side.side_id)
            else:
                self.log("status", f"❄️ {user_poke.display_name} is frozen solid!", user_side.side_id)
                return

        if user_poke.status == "paralysis" and random.random() < 0.25:
            self.log("status", f"⚡ {user_poke.display_name} is fully paralyzed and cannot move!", user_side.side_id)
            return

        if user_poke.is_flinched:
            user_poke.is_flinched = False
            self.log("status", f"💫 {user_poke.display_name} flinched and couldn't move!", user_side.side_id)
            return

        # Confusion check (33% chance to hurt itself for 40 BP physical hit)
        if user_poke.is_confused:
            self.log("status", f"💫 {user_poke.display_name} is confused!", user_side.side_id)
            user_poke.confusion_turns -= 1
            if user_poke.confusion_turns <= 0:
                user_poke.is_confused = False
                self.log("status", f"✨ {user_poke.display_name} snapped out of confusion!", user_side.side_id)
            elif random.random() < 0.33:
                lvl = user_poke.level
                atk = user_poke.get_effective_stat("attack", self)
                defn = user_poke.get_effective_stat("defense", self)
                conf_dmg = math.floor(math.floor(math.floor(2 * lvl / 5 + 2) * 40 * atk / defn) / 50) + 2
                user_poke.current_hp = max(0, user_poke.current_hp - conf_dmg)
                self.log("damage", f"💥 It hurt itself in its confusion! (-{conf_dmg} HP)", user_side.side_id, {"confusion": True})
                if user_poke.is_fainted:
                    self.log("faint", f"☠️ {user_poke.display_name} fainted!", user_side.side_id, {"species": user_poke.species})
                    self.prompt_replacement(user_side)
                return

        # Infatuation check (50% chance to be immobilized by love)
        if user_poke.is_infatuated and opp_poke and not opp_poke.is_fainted:
            self.log("status", f"❤️ {user_poke.display_name} is in love with {opp_poke.display_name}!", user_side.side_id)
            if random.random() < 0.5:
                self.log("status", f"💔 {user_poke.display_name} is immobilized by love!", user_side.side_id)
                return

        # Taunt check (prevents status category moves)
        if not user_poke.is_gmax and user_poke.taunt_turns > 0 and m_data.get("category") == "status":
            self.log("status", f"🤬 {user_poke.display_name} can't use {m_human} after the taunt!", user_side.side_id)
            return

        # Assault Vest check (prevents status category moves)
        if not user_poke.is_gmax and user_poke.has_item and user_poke.item == "assault-vest" and m_data.get("category") == "status":
            self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} tried to use {m_human}!", user_side.side_id)
            self.log("fail", f"🦺 The effects of the Assault Vest prevent using status moves!", user_side.side_id)
            return

        # Choice Lock check (Choice Band, Choice Specs, Choice Scarf - suspended while Dynamaxed!)
        move_lower = move_name.lower().strip()
        if not user_poke.is_gmax and user_poke.has_item and user_poke.item in ("choice-band", "choice-specs", "choice-scarf") and move_lower != "struggle":
            if user_poke.choice_locked_move and user_poke.choice_locked_move != move_lower:
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} tried to use {m_human}!", user_side.side_id)
                self.log("fail", f"🔒 {user_poke.display_name} is locked into {humanize_name(user_poke.choice_locked_move)} by its {humanize_name(user_poke.item)}!", user_side.side_id)
                return
            else:
                user_poke.choice_locked_move = move_lower

        # Priority move checks (Psychic Terrain, Armor Tail, Dazzling, Queenly Majesty, Prankster vs Dark)
        move_priority = self.get_move_priority(user_poke, move_name)
        if move_priority > 0 and opp_poke and not opp_poke.is_fainted and user_side.side_id != opp_side.side_id:
            # 1. Psychic Terrain protects grounded opposing targets from priority moves
            if self.terrain == "psychic" and self.is_grounded(opp_poke):
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {
                    "move": m_human,
                    "category": m_data.get("category", "physical"),
                    "moveType": m_data.get("type", "normal")
                })
                self.log("fail", f"🔮 {opp_poke.display_name} is protected by the psychic terrain!", opp_side.side_id)
                return

            # 2. Armor Tail / Dazzling / Queenly Majesty prevents opposing priority moves
            if opp_poke.ability in ("armor-tail", "dazzling", "queenly-majesty"):
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {
                    "move": m_human,
                    "category": m_data.get("category", "physical"),
                    "moveType": m_data.get("type", "normal")
                })
                self.log("fail", f"🛡️ [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Cannot use priority moves against {opp_poke.display_name}!", opp_side.side_id)
                return

            # 3. Prankster status moves fail against Dark-type Pokémon (Gen 7+)
            if user_poke.ability == "prankster" and m_data.get("category") == "status" and "dark" in opp_poke.types:
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {
                    "move": m_human,
                    "category": m_data.get("category", "status"),
                    "moveType": m_data.get("type", "normal")
                })
                self.log("damage", f"🚫 It doesn't affect {opp_poke.display_name}...", opp_side.side_id, {"isImmune": True})
                return

        # Fake Out first turn only check
        is_first_turn_only = m_data.get("first_turn_only", False) or move_lower == "fake-out"
        if is_first_turn_only:
            if not getattr(user_poke, "can_fake_out", False):
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {
                    "move": m_human,
                    "category": m_data.get("category", "physical"),
                    "moveType": m_data.get("type", "normal")
                })
                self.log("damage", f"❌ But it failed!", user_side.side_id, {"failed": True})
                return
            user_poke.can_fake_out = False

        # Sucker Punch / Thunderclap check (fails if target not attacking, already moved, or fainted)
        is_sucker = m_data.get("sucker", False) or move_lower in ("sucker-punch", "thunderclap")
        if is_sucker:
            opp_act = getattr(self, "current_turn_actions", {}).get(opp_side.side_id, {})
            opp_is_attacking = False
            if opp_act.get("type") == "move":
                opp_move = opp_act.get("move", "")
                opp_m_data = get_move_metadata(opp_move)
                if opp_m_data.get("category") in ("physical", "special"):
                    opp_is_attacking = True

            opp_already_moved = (opp_side.side_id in getattr(self, "moved_this_turn", set()))

            if not opp_poke or opp_poke.is_fainted or not opp_is_attacking or opp_already_moved:
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {
                    "move": m_human,
                    "category": m_data.get("category", "physical"),
                    "moveType": m_data.get("type", "dark")
                })
                self.log("damage", f"❌ But it failed!", user_side.side_id, {"failed": True})
                return

        # Deduct PP (Pressure consumes 2 PP on moves targeting the opponent!)
        base_m = move_lower
        if base_m not in user_poke.pp:
            for om in user_poke.moves:
                if om == move_lower:
                    base_m = om
                    break
            else:
                if user_poke.moves:
                    base_m = user_poke.moves[0]

        if base_m in user_poke.pp and base_m != "struggle":
            targets_opp = (
                m_data.get("category") in ("physical", "special") or
                m_data.get("inflict_status") or
                m_data.get("stat_drops") or
                m_data.get("taunt") or
                m_data.get("yawn") or
                m_data.get("attract") or
                move_lower in ("trick", "switcheroo", "leech-seed", "encore", "torment", "disable")
            )
            has_pressure = bool(opp_poke and not opp_poke.is_fainted and opp_poke.ability == "pressure")
            pp_cost = 2 if (has_pressure and targets_opp) else 1
            user_poke.pp[base_m] = max(0, user_poke.pp[base_m] - pp_cost)
            if has_pressure and targets_opp:
                self.log("ability", f"✨ [{opp_poke.display_name}'s Pressure] Exerted pressure on {user_poke.display_name}'s {m_human}! (-2 PP)", opp_side.side_id)

        # Protect, Max Guard, & defensive protection moves handling with official Gen 6-9 consecutive decay: (1/3)^count
        is_protect_move = bool(move_lower in PROTECT_MOVES or m_data.get("protect") or (user_poke.is_gmax and max_info and max_info.get("isMaxGuard")))
        if is_protect_move:
            count = getattr(user_poke, "consecutive_protect_count", 0)
            success_rate = (1.0 / 3.0) ** count

            if random.random() < success_rate:
                user_poke.consecutive_protect_count = count + 1
                user_poke.is_protected = True
                if user_poke.is_gmax and max_info and max_info.get("isMaxGuard"):
                    user_poke.is_max_guarded = True
                    self.log("move", f"🛡️ [{user_side.name}] {user_poke.display_name} used Max Guard!", user_side.side_id, {
                        "move": "Max Guard",
                        "category": "status",
                        "moveType": "normal",
                        "userSpecies": user_poke.species,
                        "userDisplayName": user_poke.display_name,
                        "isProtect": True
                    })
                    self.log("field", f"🛡️ {user_poke.display_name} protected itself completely with Max Guard!", user_side.side_id)
                else:
                    self.log("move", f"🛡️ [{user_side.name}] {user_poke.display_name} protected itself!", user_side.side_id, {
                        "move": m_human,
                        "isProtect": True
                    })
            else:
                user_poke.consecutive_protect_count = 0
                user_poke.is_protected = False
                user_poke.is_max_guarded = False
                prot_name = "Max Guard" if (user_poke.is_gmax and max_info and max_info.get("isMaxGuard")) else m_human
                self.log("move", f"🛡️ [{user_side.name}] {user_poke.display_name} used {prot_name}!", user_side.side_id, {
                    "move": prot_name,
                    "isProtect": True,
                    "failed": True
                })
                self.log("fail", f"❌ But it failed!", user_side.side_id, {"failed": True})
            return
        else:
            # Any non-protection move resets the consecutive protection streak to 0
            user_poke.consecutive_protect_count = 0

        # Two-turn charging moves (Electro Shot, Solar Beam, Solar Blade)
        if move_lower == "electro-shot":
            is_rain = (self.weather == "rain")
            has_herb = (user_poke.has_item and user_poke.item == "power-herb")
            is_charged = (user_poke.charging_move == "electro-shot")

            if is_rain:
                user_poke.charging_move = None
                user_poke.modify_stage("special-attack", 1)
                self.log("stat", f"📈 [{user_poke.display_name}] Absorbed electric downpour! SpA rose!", user_side.side_id, {"stat": "special-attack", "delta": 1})
            elif has_herb and not is_charged:
                user_poke.has_item = False
                user_poke.item = None
                user_poke.item_revealed = True
                user_poke.charging_move = None
                user_poke.modify_stage("special-attack", 1)
                self.log("item", f"🌿 [{user_poke.display_name}'s Power Herb] Power Herb allowed it to unleash Electro Shot instantly! SpA rose!", user_side.side_id)
            elif is_charged:
                user_poke.charging_move = None
            else:
                # Turn 1: Charge turn (absorb electricity & raise SpA; no damage dealt yet)
                user_poke.charging_move = "electro-shot"
                user_poke.modify_stage("special-attack", 1)
                self.log("move", f"⚡ [{user_side.name}] {user_poke.display_name} absorbed electricity! SpA rose!", user_side.side_id, {
                    "move": m_human, "charging": True, "stat": "special-attack", "delta": 1
                })
                return

        elif move_lower in ("solar-beam", "solar-blade"):
            eff_w = self.get_effective_weather()
            is_sun = (eff_w == "sun")
            has_herb = (user_poke.has_item and user_poke.item == "power-herb")
            is_charged = (user_poke.charging_move == move_lower)

            if is_sun:
                user_poke.charging_move = None
            elif has_herb and not is_charged:
                user_poke.has_item = False
                user_poke.item = None
                user_poke.item_revealed = True
                user_poke.charging_move = None
                self.log("item", f"🌿 [{user_poke.display_name}'s Power Herb] Power Herb allowed it to attack instantly!", user_side.side_id)
            elif is_charged:
                user_poke.charging_move = None
            else:
                user_poke.charging_move = move_lower
                self.log("move", f"☀️ [{user_side.name}] {user_poke.display_name} absorbed sunlight!", user_side.side_id, {
                    "move": m_human, "charging": True
                })
                return

        elif move_lower == "meteor-beam":
            has_herb = (user_poke.has_item and user_poke.item == "power-herb")
            is_charged = (user_poke.charging_move == "meteor-beam")

            if has_herb and not is_charged:
                user_poke.has_item = False
                user_poke.item = None
                user_poke.item_revealed = True
                user_poke.charging_move = None
                user_poke.modify_stage("special-attack", 1)
                self.log("item", f"🌿 [{user_poke.display_name}'s Power Herb] Power Herb allowed it to unleash Meteor Beam instantly! SpA rose!", user_side.side_id)
            elif is_charged:
                user_poke.charging_move = None
            else:
                user_poke.charging_move = "meteor-beam"
                user_poke.modify_stage("special-attack", 1)
                self.log("move", f"☄️ [{user_side.name}] {user_poke.display_name} is overflowing with space power! SpA rose!", user_side.side_id, {
                    "move": m_human, "charging": True, "stat": "special-attack", "delta": 1
                })
                return

        elif move_lower == "skull-bash":
            has_herb = (user_poke.has_item and user_poke.item == "power-herb")
            is_charged = (user_poke.charging_move == "skull-bash")

            if has_herb and not is_charged:
                user_poke.has_item = False
                user_poke.item = None
                user_poke.item_revealed = True
                user_poke.charging_move = None
                user_poke.modify_stage("defense", 1)
                self.log("item", f"🌿 [{user_poke.display_name}'s Power Herb] Power Herb allowed it to unleash Skull Bash instantly! Def rose!", user_side.side_id)
            elif is_charged:
                user_poke.charging_move = None
            else:
                user_poke.charging_move = "skull-bash"
                user_poke.modify_stage("defense", 1)
                self.log("move", f"🛡️ [{user_side.name}] {user_poke.display_name} tucked in its head! Def rose!", user_side.side_id, {
                    "move": m_human, "charging": True, "stat": "defense", "delta": 1
                })
                return

        elif move_lower in ("sky-attack", "freeze-shock", "ice-burn"):
            has_herb = (user_poke.has_item and user_poke.item == "power-herb")
            is_charged = (user_poke.charging_move == move_lower)

            if has_herb and not is_charged:
                user_poke.has_item = False
                user_poke.item = None
                user_poke.item_revealed = True
                user_poke.charging_move = None
                self.log("item", f"🌿 [{user_poke.display_name}'s Power Herb] Power Herb allowed it to attack instantly!", user_side.side_id)
            elif is_charged:
                user_poke.charging_move = None
            else:
                user_poke.charging_move = move_lower
                self.log("move", f"⚡ [{user_side.name}] {user_poke.display_name} became cloaked in energy!", user_side.side_id, {
                    "move": m_human, "charging": True
                })
                return

        # Two-turn semi-invulnerable moves (Phantom Force, Shadow Force, Fly, Dig, Dive, Bounce)
        SEMI_INVULNERABLE_MOVES = {
            "phantom-force": {"icon": "👻", "text": "vanished into the shadows!"},
            "shadow-force": {"icon": "👻", "text": "vanished into the shadows!"},
            "fly": {"icon": "🦅", "text": "flew up high!"},
            "dig": {"icon": "⛏️", "text": "burrowed underground!"},
            "dive": {"icon": "🌊", "text": "hid underwater!"},
            "bounce": {"icon": "🦘", "text": "bounced up high!"},
        }

        if not user_poke.is_gmax and move_lower in SEMI_INVULNERABLE_MOVES:
            semi_meta = SEMI_INVULNERABLE_MOVES[move_lower]
            has_herb = (user_poke.has_item and user_poke.item == "power-herb")
            is_charged = (user_poke.charging_move == move_lower)

            if has_herb and not is_charged:
                user_poke.has_item = False
                user_poke.item = None
                user_poke.item_revealed = True
                user_poke.charging_move = None
                user_poke.semi_invulnerable = None
                self.log("item", f"🌿 [{user_poke.display_name}'s Power Herb] Power Herb allowed it to attack instantly!", user_side.side_id)
            elif is_charged:
                user_poke.charging_move = None
                user_poke.semi_invulnerable = None
            else:
                # Turn 1: Enter semi-invulnerable charging state
                user_poke.charging_move = move_lower
                user_poke.semi_invulnerable = move_lower
                self.log("move", f"{semi_meta['icon']} [{user_side.name}] {user_poke.display_name} {semi_meta['text']}", user_side.side_id, {
                    "move": m_human, "charging": True, "semiInvulnerable": move_lower
                })
                return

        # Phantom Force, Shadow Force, Feint, Hyperspace Fury/Hole break through Protect, Detect, and Max Guard
        if move_lower in ("phantom-force", "shadow-force", "feint", "hyperspace-fury", "hyperspace-hole"):
            if opp_poke and (opp_poke.is_protected or getattr(opp_poke, "is_max_guarded", False)):
                opp_poke.is_protected = False
                opp_poke.is_max_guarded = False
                self.log("field", f"👻 [{user_side.name}] {user_poke.display_name} broke through {opp_poke.display_name}'s protection!", user_side.side_id)

        # Target protected? (Self-targeting and field moves NEVER get blocked by Protect!)
        is_protect_pierce = False
        targets_opp = self.is_move_targeting_opponent(move_lower, m_data)
        if targets_opp and opp_poke and opp_poke.is_protected:
            # Unseen Fist allows contact/damaging moves to punch straight through standard Protect/Detect
            if user_poke.ability == "unseen-fist" and not getattr(opp_poke, "is_max_guarded", False):
                self.log("ability", f"👊 [{user_poke.display_name}'s Unseen Fist] Punched through {opp_poke.display_name}'s protection!", user_side.side_id)
            elif user_poke.is_gmax and max_info:
                is_bypassing = max_info.get("gmaxMeta", {}).get("bypass_protect", False)
                is_max_guarded = getattr(opp_poke, "is_max_guarded", False)
                if is_max_guarded and not is_bypassing:
                    self.log("move", f"⚡ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {
                        "move": m_human,
                        "category": max_info.get("category", "physical"),
                        "moveType": max_info.get("type", "normal"),
                        "userSpecies": user_poke.species
                    })
                    self.log("protect", f"🛡️ {opp_poke.display_name} protected itself completely with Max Guard!", opp_side.side_id)
                    return
                elif not is_bypassing:
                    is_protect_pierce = True
            else:
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {"move": m_human})
                self.log("protect", f"🛡️ {opp_poke.display_name} protected itself from {m_human}!", opp_side.side_id)
                self.handle_crash_damage(user_poke, user_side, move_name)
                return

        # Target semi-invulnerable check (Fly, Dig, Dive, Bounce, Phantom Force, Shadow Force)
        if targets_opp and opp_poke and getattr(opp_poke, "semi_invulnerable", None):
            can_hit = False
            if user_poke.ability == "no-guard":
                can_hit = True
            elif move_lower == "toxic" and "poison" in user_poke.types:
                can_hit = True
            elif opp_poke.semi_invulnerable in ("fly", "bounce") and move_lower in ("gust", "twister", "thunder", "hurricane", "smack-down"):
                can_hit = True
            elif opp_poke.semi_invulnerable == "dig" and move_lower in ("earthquake", "magnitude"):
                can_hit = True
            elif opp_poke.semi_invulnerable == "dive" and move_lower in ("surf", "whirlpool"):
                can_hit = True

            if not can_hit:
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {"move": m_human})
                self.log("miss", f"❌ {opp_poke.display_name} avoided the attack!", user_side.side_id)
                self.handle_crash_damage(user_poke, user_side, move_name)
                return

        # Accuracy Check (Max Moves never miss!)
        if not user_poke.is_gmax:
            if not self.check_move_accuracy(user_poke, opp_poke, move_name, m_data):
                self.log("move", f"⚔️ [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {"move": m_human})
                self.log("miss", f"❌ {user_poke.display_name}'s attack missed!", user_side.side_id)
                self.handle_crash_damage(user_poke, user_side, move_name)
                return

        # Dynamic move typing resolution (Weather Ball, Terrain Pulse, Tera Blast)
        if user_poke.is_gmax and max_info:
            effective_category = max_info.get("category", "physical")
            effective_type = max_info.get("type", "normal").lower()
        else:
            effective_category = m_data.get("category", "physical")
            effective_type = m_data.get("type", "normal").lower()

            if move_name.lower() == "weather-ball":
                eff_w = self.get_effective_weather()
                if eff_w == "rain":
                    effective_type = "water"
                elif eff_w == "sun":
                    effective_type = "fire"
                elif eff_w == "sandstorm":
                    effective_type = "rock"
                elif eff_w == "snow":
                    effective_type = "ice"
            elif move_name.lower() == "terrain-pulse" and ("flying" not in user_poke.types and user_poke.ability != "levitate"):
                if self.terrain == "electric":
                    effective_type = "electric"
                elif self.terrain == "grassy":
                    effective_type = "grass"
                elif self.terrain == "psychic":
                    effective_type = "psychic"
                elif self.terrain == "misty":
                    effective_type = "fairy"
            elif move_name.lower() == "tera-blast" and user_poke.is_terastallized:
                effective_type = user_poke.tera_type
                if user_poke.get_effective_stat("attack", self) > user_poke.get_effective_stat("special-attack", self):
                    effective_category = "physical"
            elif move_name.lower() in ("ivy-cudgel", "ivycudgel"):
                if user_poke.item == "hearthflame-mask" or "hearthflame" in user_poke.species.lower():
                    effective_type = "fire"
                elif user_poke.item == "wellspring-mask" or "wellspring" in user_poke.species.lower():
                    effective_type = "water"
                elif user_poke.item == "cornerstone-mask" or "cornerstone" in user_poke.species.lower():
                    effective_type = "rock"
                else:
                    effective_type = "grass"

        # Protean / Libero ability handling (Gen 9: transforms user into move type on first attack)
        if user_poke.ability in ("protean", "libero") and not user_poke.is_terastallized:
            if not getattr(user_poke, "protean_activated", False):
                user_poke.types = [effective_type]
                user_poke.protean_activated = True
                self.log("ability", f"✨ [{user_poke.display_name}'s {humanize_name(user_poke.ability)}] Transformed into pure {effective_type.capitalize()}!", user_side.side_id)

        # Execute Move
        move_icon = "⚡" if user_poke.is_gmax else "⚔️"
        self.log("move", f"{move_icon} [{user_side.name}] {user_poke.display_name} used {m_human}!", user_side.side_id, {
            "move": m_human,
            "category": effective_category,
            "moveType": effective_type,
            "userSpecies": user_poke.species,
            "userDisplayName": user_poke.display_name,
            "isMaxMove": user_poke.is_gmax
        })

        # Status / Field moves
        if m_data.get("category") == "status":
            self.handle_status_move(user_side, opp_side, user_poke, opp_poke, m_data, m_human, pivot_target_index=pivot_target_index)
            return

        # Damaging attack
        # Brick Break / Psychic Fangs: Shatter screens before damage calculation!
        if move_lower in ("brick-break", "psychic-fangs"):
            if opp_side.reflect_turns > 0 or opp_side.light_screen_turns > 0 or opp_side.aurora_veil_turns > 0:
                opp_side.reflect_turns = 0
                opp_side.light_screen_turns = 0
                opp_side.aurora_veil_turns = 0
                self.log("field", f"🔨 [{user_side.name}] {user_poke.display_name}'s {m_human} shattered {opp_side.name}'s screens!", user_side.side_id)

        dmg, info = self.calculate_move_damage(user_poke, opp_poke, move_name)

        # Complete Immunity Check (e.g. Draco Meteor vs Fairy, Normal/Fighting vs Ghost, Ground vs Flying)
        # In competitive Pokémon, type immunities take precedence: the move fails to affect the target and CANNOT break Disguise!
        if info["typeMult"] == 0.0:
            # Check defensive absorption abilities before generic immunity message
            if opp_poke.ability == "well-baked-body" and effective_type == "fire":
                opp_poke.modify_stage("defense", 2)
                self.log("ability", f"🍞 [{opp_poke.display_name}'s Well-Baked Body] Immune to Fire! Defense rose sharply (+2)!", opp_side.side_id, {
                    "ability": "Well-Baked Body", "stat": "defense", "delta": 2
                })
                return
            elif opp_poke.ability == "flash-fire" and effective_type == "fire":
                self.log("ability", f"🔥 [{opp_poke.display_name}'s Flash Fire] Immune to Fire! Its Fire-type moves were powered up!", opp_side.side_id)
                return
            elif opp_poke.ability == "earth-eater" and effective_type == "ground":
                heal_amt = math.floor(opp_poke.max_hp * 0.25)
                opp_poke.current_hp = min(opp_poke.max_hp, opp_poke.current_hp + heal_amt)
                self.log("ability", f"🌍 [{opp_poke.display_name}'s Earth Eater] Absorbed Ground attack and restored HP! (+{heal_amt} HP)", opp_side.side_id)
                return
            elif opp_poke.ability in ("water-absorb", "dry-skin") and effective_type == "water":
                heal_amt = math.floor(opp_poke.max_hp * 0.25)
                opp_poke.current_hp = min(opp_poke.max_hp, opp_poke.current_hp + heal_amt)
                self.log("ability", f"💧 [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Absorbed Water attack and restored HP! (+{heal_amt} HP)", opp_side.side_id)
                return
            elif opp_poke.ability == "volt-absorb" and effective_type == "electric":
                heal_amt = math.floor(opp_poke.max_hp * 0.25)
                opp_poke.current_hp = min(opp_poke.max_hp, opp_poke.current_hp + heal_amt)
                self.log("ability", f"⚡ [{opp_poke.display_name}'s Volt Absorb] Absorbed Electric attack and restored HP! (+{heal_amt} HP)", opp_side.side_id)
                return
            elif opp_poke.ability in ("lightning-rod", "storm-drain") and ((opp_poke.ability == "lightning-rod" and effective_type == "electric") or (opp_poke.ability == "storm-drain" and effective_type == "water")):
                opp_poke.modify_stage("special-attack", 1)
                self.log("ability", f"✨ [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Immune! SpA rose!", opp_side.side_id, {
                    "stat": "special-attack", "delta": 1
                })
                return
            elif opp_poke.ability == "motor-drive" and effective_type == "electric":
                opp_poke.modify_stage("speed", 1)
                self.log("ability", f"⚡ [{opp_poke.display_name}'s Motor Drive] Immune! Spe rose!", opp_side.side_id, {
                    "stat": "speed", "delta": 1
                })
                return
            elif opp_poke.ability == "sap-sipper" and effective_type == "grass":
                opp_poke.modify_stage("attack", 1)
                self.log("ability", f"🌱 [{opp_poke.display_name}'s Sap Sipper] Immune! Atk rose!", opp_side.side_id, {
                    "stat": "attack", "delta": 1
                })
                return

            self.log("damage", f"🚫 It doesn't affect {opp_poke.display_name}...", opp_side.side_id, {"isImmune": True})
            self.handle_crash_damage(user_poke, user_side, move_name)
            return

        # Substitute & sound/infiltrator bypass check
        bypasses_sub = (user_poke.ability == "infiltrator" or move_lower in SOUND_MOVES)
        target_sub_active = (getattr(opp_poke, "substitute_hp", 0) > 0 and not bypasses_sub)
        hits_count = self.determine_multi_hit_count(user_poke, move_lower, m_data)
        single_hit_dmg = dmg

        if getattr(opp_poke, "substitute_hp", 0) > 0 and bypasses_sub:
            if user_poke.ability == "infiltrator":
                self.log("ability", f"✨ [{user_poke.display_name}'s Infiltrator] Slipped through {opp_poke.display_name}'s substitute!", user_side.side_id)
            elif move_lower in SOUND_MOVES:
                self.log("move", f"🔊 [{user_side.name}] {m_human}'s sound waves bypassed the substitute!", user_side.side_id)

        # Check Mimikyu's Disguise ability (absorbs the attack, breaks disguise, takes 1/8 max HP recoil)
        # Note: If target is behind a substitute, the substitute absorbs the hit instead; Disguise is untouched!
        if not target_sub_active and opp_poke.ability == "disguise" and not getattr(opp_poke, "disguise_busted", False):
            if user_poke.ability not in ("mold-breaker", "teravolt", "turboblaze"):
                opp_poke.disguise_busted = True
                opp_poke.times_hit_counter += 1
                busted_dmg = max(1, math.floor(opp_poke.max_hp / 8))
                opp_poke.current_hp = max(0, opp_poke.current_hp - busted_dmg)
                busted_pct = round((busted_dmg / opp_poke.max_hp) * 100, 1)
                self.log("ability", f"🎭 [{opp_poke.display_name}'s Disguise] Its disguise served as a decoy and was busted! (-{busted_dmg} HP, {busted_pct}%)", opp_side.side_id, {
                    "species": opp_poke.species, "disguiseBusted": True, "damage": busted_dmg
                })
                # Multi-hit moves: subsequent hits strike Mimikyu directly!
                if hits_count > 1 and not opp_poke.is_fainted:
                    remaining_hits = hits_count - 1
                    subsequent_dmg = single_hit_dmg * remaining_hits
                    opp_poke.current_hp = max(0, opp_poke.current_hp - subsequent_dmg)
                    opp_poke.times_hit_counter += remaining_hits
                    sub_pct = round((subsequent_dmg / opp_poke.max_hp) * 100, 1)
                    self.log("damage", f"{opp_poke.display_name} took 💥 -{subsequent_dmg} HP ({sub_pct}%) from the remaining strikes! | Hit {hits_count} times!", opp_side.side_id)
                if opp_poke.is_fainted:
                    self.log("faint", f"☠️ {opp_poke.display_name} fainted!", opp_side.side_id, {
                        "species": opp_poke.species,
                        "displayName": opp_poke.display_name,
                        "killerSpecies": user_poke.species,
                        "killerDisplayName": user_poke.display_name,
                        "killerMove": m_human
                    })
                    self.prompt_replacement(opp_side)
                return

        # Substitute absorption handler: absorbs attack
        if target_sub_active:
            sub_callout = f"💥 -{single_hit_dmg} HP"
            if not info.get("fixedDamage"):
                if info["isCrit"]:
                    sub_callout += " | Critical hit!"
                if info["typeMult"] >= 2.0:
                    sub_callout += " | Super effective!"
                elif info["typeMult"] <= 0.5:
                    sub_callout += " | Not very effective..."

            sub_broke = False
            hits_on_sub = 0
            hits_on_target = 0
            actual_sub_dmg = 0
            for h in range(hits_count):
                if opp_poke.substitute_hp > 0:
                    hits_on_sub += 1
                    strike_sub_dmg = min(opp_poke.substitute_hp, single_hit_dmg)
                    actual_sub_dmg += strike_sub_dmg
                    opp_poke.substitute_hp = max(0, opp_poke.substitute_hp - single_hit_dmg)
                    if opp_poke.substitute_hp == 0:
                        sub_broke = True
                else:
                    hits_on_target += 1

            if sub_broke:
                self.log("damage", f"💥 [{opp_side.name}] The substitute took the hit ({sub_callout})! {opp_poke.display_name}'s substitute broke!", opp_side.side_id, {
                    "damage": actual_sub_dmg,
                    "substituteBroke": True,
                    "substituteHp": 0,
                    "isCrit": info["isCrit"],
                    "typeMult": info["typeMult"],
                    "defenderHp": opp_poke.current_hp,
                    "defenderMaxHp": opp_poke.max_hp
                })
            else:
                self.log("damage", f"🛡️ [{opp_side.name}] The substitute took the hit ({sub_callout})! (Sub HP remaining: {opp_poke.substitute_hp})", opp_side.side_id, {
                    "damage": actual_sub_dmg,
                    "substituteDamage": actual_sub_dmg,
                    "substituteHp": opp_poke.substitute_hp,
                    "isCrit": info["isCrit"],
                    "typeMult": info["typeMult"],
                    "defenderHp": opp_poke.current_hp,
                    "defenderMaxHp": opp_poke.max_hp
                })

            target_actual_dmg = 0
            if hits_on_target > 0 and not opp_poke.is_fainted:
                target_raw_dmg = single_hit_dmg * hits_on_target
                target_actual_dmg = min(opp_poke.current_hp, target_raw_dmg)
                opp_poke.current_hp = max(0, opp_poke.current_hp - target_raw_dmg)
                opp_poke.times_hit_counter += hits_on_target
                t_pct = round((target_actual_dmg / opp_poke.max_hp) * 100, 1)
                self.log("damage", f"{opp_poke.display_name} took 💥 -{target_actual_dmg} HP ({t_pct}%) from the remaining strikes! | Hit {hits_count} times!", opp_side.side_id)
                if opp_poke.is_fainted:
                    self.log("faint", f"☠️ {opp_poke.display_name} fainted!", opp_side.side_id, {
                        "species": opp_poke.species,
                        "displayName": opp_poke.display_name,
                        "killerSpecies": user_poke.species,
                        "killerDisplayName": user_poke.display_name,
                        "killerMove": m_human
                    })
                    self.prompt_replacement(opp_side)

            total_actual_sub_dmg = actual_sub_dmg + target_actual_dmg

            # Recoil damage on user (e.g. Brave Bird, Flare Blitz, Head Smash, Struggle)
            if m_data.get("recoil") and (total_actual_sub_dmg > 0 or move_lower == "struggle"):
                if user_poke.ability in ("rock-head", "magic-guard") and move_lower != "struggle":
                    self.log("ability", f"✨ [{user_poke.display_name}'s {humanize_name(user_poke.ability)}] Protected it from recoil damage!", user_side.side_id)
                else:
                    if move_lower == "struggle":
                        recoil_dmg = max(1, math.floor(user_poke.max_hp * 0.25))
                    else:
                        recoil_dmg = max(1, math.floor(total_actual_sub_dmg * m_data["recoil"]))
                    user_poke.current_hp = max(0, user_poke.current_hp - recoil_dmg)
                    self.log("damage", f"{user_poke.display_name} was hit with recoil! (-{recoil_dmg} HP)", user_side.side_id)
                    if user_poke.is_fainted:
                        self.log("faint", f"☠️ {user_poke.display_name} fainted!", user_side.side_id, {"species": user_poke.species})
                        self.prompt_replacement(user_side)
                        return

            # Drain Healing (e.g. Giga Drain, Drain Punch)
            if m_data.get("heal_drain") and total_actual_sub_dmg > 0 and not user_poke.is_fainted:
                heal_drain = max(1, math.floor(total_actual_sub_dmg * m_data["heal_drain"]))
                user_poke.current_hp = min(user_poke.max_hp, user_poke.current_hp + heal_drain)
                self.log("heal", f"💚 {user_poke.display_name} sucked energy from the substitute! (+{heal_drain} HP)", user_side.side_id)

            # Self stat drop (e.g. Close Combat, Make It Rain, Draco Meteor)
            if m_data.get("self_stat_drop") and not user_poke.is_fainted:
                for stat, drop in m_data["self_stat_drop"].items():
                    user_poke.modify_stage(stat, drop)
                    self.log("stat", f"📉 {user_poke.display_name}'s {format_stat_name(stat)} fell!", user_side.side_id, {"stat": stat, "delta": drop})
                self.check_white_herb(user_poke, user_side)

            # Self stat boost (e.g. Torch Song, Flame Charge, Power-Up Punch)
            if m_data.get("self_boost") and not user_poke.is_fainted:
                for stat, boost in m_data["self_boost"].items():
                    user_poke.modify_stage(stat, boost)
                    self.log("stat", f"📈 [{user_poke.display_name}] {format_stat_name(stat)} rose!", user_side.side_id, {"stat": stat, "delta": boost})

            # Life Orb recoil on user
            if user_poke.has_item and user_poke.item == "life-orb" and dmg > 0 and not user_poke.is_fainted:
                lo_recoil = math.floor(user_poke.max_hp * 0.1)
                user_poke.current_hp = max(0, user_poke.current_hp - lo_recoil)
                user_poke.item_revealed = True
                self.log("item", f"⚡ {user_poke.display_name} lost some HP from Life Orb! (-{lo_recoil} HP)", user_side.side_id)
                if user_poke.is_fainted:
                    self.log("faint", f"☠️ {user_poke.display_name} fainted!", user_side.side_id, {"species": user_poke.species})
                    self.prompt_replacement(user_side)
                    return

            # Check pivot on damaging attack (U-turn, Volt Switch, Flip Turn)
            if m_data.get("pivot") and not user_poke.is_fainted:
                alive_bench = user_side.get_alive_bench_indices()
                if alive_bench:
                    target_switch_idx = pivot_target_index if (pivot_target_index is not None and pivot_target_index in alive_bench) else alive_bench[0]
                    self.perform_switch(user_side, opp_side, target_switch_idx, is_replacement=False, is_pivot=True)

            # Check self-destruct / suicide moves (Final Gambit, Explosion, Self-Destruct, Misty Explosion)
            if move_lower == "final-gambit" or m_data.get("self_destruct"):
                self.suicide_side = user_side.side_id
                user_poke.current_hp = 0
                self.log("faint", f"☠️ {user_poke.display_name} fainted from using {m_human}!", user_side.side_id, {
                    "species": user_poke.species, "displayName": user_poke.display_name, "selfFaint": True
                })
                self.prompt_replacement(user_side)

            return

        if info.get("hadMultiscale"):
            self.log("ability", f"🛡️ [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Weakened the attack!", opp_side.side_id)

        total_dmg = single_hit_dmg * hits_count
        if is_protect_pierce:
            total_dmg = max(1, math.floor(total_dmg * 0.25))
            self.log("protect", f"🛡️ {opp_poke.display_name} couldn't fully protect itself and took chip damage from {m_human}!", opp_side.side_id)

        # Multi-hit moves break Focus Sash / Sturdy because subsequent strikes finish them off
        if hits_count > 1 and info.get("focusSashUsed"):
            if total_dmg >= opp_poke.current_hp:
                info["focusSashUsed"] = False

        # Actual damage inflicted is capped by defender's current HP
        actual_dmg = min(opp_poke.current_hp, total_dmg)
        opp_poke.current_hp = max(0, opp_poke.current_hp - total_dmg)
        dmg_pct = round((actual_dmg / opp_poke.max_hp) * 100, 1)
        opp_poke.times_hit_counter += hits_count
        dmg = actual_dmg

        # Build dynamic callout
        callout = f"💥 -{actual_dmg} HP ({dmg_pct}%)"
        if hits_count > 1:
            callout += f" | Hit {hits_count} times!"
            if user_poke.ability == "skill-link" and hits_count == 5:
                callout += " (Skill Link)"
            elif user_poke.has_item and user_poke.item == "loaded-dice" and hits_count >= 4:
                callout += " (Loaded Dice)"
        if not info.get("fixedDamage"):
            if info["isCrit"]:
                callout += " | Critical hit!"
            if info.get("hadSpreadReduction"):
                callout += " | Spread (-25%)"
            if info.get("hadSupremeOverlord"):
                callout += " | Supreme Overlord"
            if move_lower == "rage-fist":
                callout += f" | Rage Fist ({info.get('basePower', 50)} BP)"
            elif move_lower == "last-respects":
                callout += f" | Last Respects ({info.get('basePower', 50)} BP)"
            if info["typeMult"] >= 2.0:
                callout += " | Super effective!"
            elif info["typeMult"] <= 0.5:
                callout += " | Not very effective..."

        self.log("damage", f"{opp_poke.display_name} took {callout}!", opp_side.side_id, {
            "damage": actual_dmg,
            "rawDamage": total_dmg,
            "hitsCount": hits_count,
            "isCrit": info["isCrit"],
            "typeMult": info["typeMult"],
            "defenderHp": opp_poke.current_hp,
            "defenderMaxHp": opp_poke.max_hp
        })

        # Focus Sash consumption (only if survived with HP > 0)
        if info.get("focusSashUsed") and opp_poke.current_hp > 0:
            opp_poke.has_item = False
            opp_poke.item = None
            opp_poke.item_revealed = True
            self.log("item", f"🥋 [{opp_poke.display_name}'s Focus Sash] Hung on using its Focus Sash!", opp_side.side_id)

        # Air Balloon popped by damaging attack
        if opp_poke.has_item and opp_poke.item == "air-balloon" and total_dmg > 0 and not opp_poke.is_fainted:
            opp_poke.has_item = False
            opp_poke.item = None
            opp_poke.item_revealed = True
            self.log("item", f"🎈 [{opp_poke.display_name}'s Air Balloon] Its Air Balloon popped!", opp_side.side_id)

        # =========================================================
        # ON-HIT DEFENSIVE ABILITY PROCS (Stamina, Rough Skin, etc.)
        # =========================================================
        if not opp_poke.is_fainted and total_dmg > 0:
            # 1. Archaludon's Stamina (+1 Defense per hit taken)
            if opp_poke.ability == "stamina":
                stamina_boost = hits_count
                opp_poke.modify_stage("defense", stamina_boost)
                stamina_msg = f"Defense rose by {stamina_boost} stages!" if stamina_boost > 1 else "Defense rose!"
                self.log("ability", f"✨ [{opp_poke.display_name}'s Stamina] {stamina_msg}", opp_side.side_id, {
                    "ability": "Stamina", "stat": "defense", "delta": stamina_boost
                })

            # 2. Rocky Helmet item on contact
            if opp_poke.has_item and opp_poke.item == "rocky-helmet" and m_data.get("category") == "physical":
                helmet_dmg = math.floor(user_poke.max_hp / 6) * hits_count
                user_poke.current_hp = max(0, user_poke.current_hp - helmet_dmg)
                opp_poke.item_revealed = True
                self.log("item", f"🪖 {user_poke.display_name} was hurt by {opp_poke.display_name}'s Rocky Helmet! (-{helmet_dmg} HP)", user_side.side_id)

            # 3. Rough Skin / Iron Barbs
            if opp_poke.ability in ("rough-skin", "iron-barbs") and m_data.get("category") == "physical":
                barb_dmg = math.floor(user_poke.max_hp / 8) * hits_count
                user_poke.current_hp = max(0, user_poke.current_hp - barb_dmg)
                self.log("ability", f"⚡ {user_poke.display_name} was hurt by {opp_poke.display_name}'s {humanize_name(opp_poke.ability)}! (-{barb_dmg} HP)", user_side.side_id)

            # 4. Weak Armor
            if opp_poke.ability == "weak-armor" and m_data.get("category") == "physical":
                opp_poke.modify_stage("defense", -1)
                opp_poke.modify_stage("speed", 2)
                self.log("ability", f"✨ [{opp_poke.display_name}'s Weak Armor] Def fell and Spe rose sharply!", opp_side.side_id)

            # 5. Justified
            if opp_poke.ability == "justified" and m_data.get("type") == "dark":
                opp_poke.modify_stage("attack", 1)
                self.log("ability", f"✨ [{opp_poke.display_name}'s Justified] Atk rose!", opp_side.side_id)

            # 6. Rattled
            if opp_poke.ability == "rattled" and m_data.get("type") in ("bug", "ghost", "dark"):
                opp_poke.modify_stage("speed", 1)
                self.log("ability", f"✨ [{opp_poke.display_name}'s Rattled] Spe rose!", opp_side.side_id)

            # 7. Baxcalibur's Thermal Exchange (+1 Atk on taking Fire attack)
            if opp_poke.ability == "thermal-exchange" and effective_type == "fire":
                opp_poke.modify_stage("attack", 1)
                self.log("ability", f"❄️ [{opp_poke.display_name}'s Thermal Exchange] Fire attack raised its Attack!", opp_side.side_id, {
                    "ability": "Thermal Exchange", "stat": "attack", "delta": 1
                })

        # Recoil damage (Struggle deals 25% max HP recoil; standard recoil moves deal % of damage actually dealt)
        if m_data.get("recoil") and (actual_dmg > 0 or move_lower == "struggle"):
            if user_poke.ability in ("rock-head", "magic-guard") and move_lower != "struggle":
                self.log("ability", f"✨ [{user_poke.display_name}'s {humanize_name(user_poke.ability)}] Protected it from recoil damage!", user_side.side_id)
            else:
                if move_lower == "struggle":
                    recoil_dmg = max(1, math.floor(user_poke.max_hp * 0.25))
                else:
                    recoil_dmg = max(1, math.floor(actual_dmg * m_data["recoil"]))
                user_poke.current_hp = max(0, user_poke.current_hp - recoil_dmg)
                self.log("damage", f"{user_poke.display_name} was hit with recoil! (-{recoil_dmg} HP)", user_side.side_id)

        # Drain Healing (based on actual damage dealt to target)
        if m_data.get("heal_drain") and actual_dmg > 0 and not user_poke.is_fainted:
            heal_drain = max(1, math.floor(actual_dmg * m_data["heal_drain"]))
            user_poke.current_hp = min(user_poke.max_hp, user_poke.current_hp + heal_drain)
            self.log("heal", f"💚 {user_poke.display_name} sucked energy from {opp_poke.display_name}! (+{heal_drain} HP)", user_side.side_id)

        # Secondary effects (blocked by Covert Cloak!)
        has_covert_cloak = (opp_poke.has_item and opp_poke.item == "covert-cloak")
        if not has_covert_cloak:
            # Flinch secondary effect (e.g. Fake Out, Iron Head, Rock Slide)
            if m_data.get("flinch") and not opp_poke.is_fainted:
                fl_rate = m_data.get("flinch", 0)
                if fl_rate >= 100 or random.randint(1, 100) <= fl_rate:
                    opp_poke.is_flinched = True

            # Stat drops on target
            if m_data.get("stat_drops") and not opp_poke.is_fainted:
                if opp_poke.has_item and opp_poke.item == "clear-amulet":
                    self.log("item", f"🛡️ [{opp_poke.display_name}'s Clear Amulet] Protected its stats from being lowered!", opp_side.side_id)
                elif opp_poke.ability in ("clear-body", "white-smoke", "hyper-cutter", "full-metal-body"):
                    self.log("ability", f"✨ [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Protected its stats from being lowered!", opp_side.side_id)
                else:
                    for stat, drop in m_data["stat_drops"].items():
                        opp_poke.modify_stage(stat, drop)
                        self.log("stat", f"📉 {opp_poke.display_name}'s {format_stat_name(stat)} fell!", opp_side.side_id, {"stat": stat, "delta": drop})
                        if opp_poke.ability == "defiant":
                            opp_poke.modify_stage("attack", 2)
                            self.log("ability", f"✨ [{opp_poke.display_name}'s Defiant] Atk rose sharply (+2)!", opp_side.side_id)
                        elif opp_poke.ability == "competitive":
                            opp_poke.modify_stage("special-attack", 2)
                            self.log("ability", f"✨ [{opp_poke.display_name}'s Competitive] SpA rose sharply (+2)!", opp_side.side_id)
                    self.check_white_herb(opp_poke, opp_side)

        # Self stat drop (e.g. Close Combat, Make It Rain, Draco Meteor)
        if m_data.get("self_stat_drop"):
            for stat, drop in m_data["self_stat_drop"].items():
                user_poke.modify_stage(stat, drop)
                self.log("stat", f"📉 {user_poke.display_name}'s {format_stat_name(stat)} fell!", user_side.side_id, {"stat": stat, "delta": drop})
            self.check_white_herb(user_poke, user_side)

        # Self stat boost (e.g. Torch Song)
        if m_data.get("self_boost"):
            for stat, boost in m_data["self_boost"].items():
                user_poke.modify_stage(stat, boost)
                self.log("stat", f"📈 [{user_poke.display_name}] {format_stat_name(stat)} rose!", user_side.side_id, {"stat": stat, "delta": boost})

        # Knock Off item removal (Canonical rule: Mega Stones cannot be removed from corresponding Pokémon)
        if m_data.get("removes_item") and opp_poke.has_item:
            if opp_poke.get_mega_species_for_item() is None:
                item_lost = opp_poke.item
                opp_poke.has_item = False
                opp_poke.item = None
                opp_poke.choice_locked_move = None
                opp_poke.item_revealed = True
                self.log("item", f"🎒 {opp_poke.display_name}'s {humanize_name(item_lost)} was knocked off!", opp_side.side_id)
            else:
                self.log("item", f"🎒 {opp_poke.display_name}'s {humanize_name(opp_poke.item)} cannot be knocked off!", opp_side.side_id)

        # Life Orb recoil
        if user_poke.has_item and user_poke.item == "life-orb" and actual_dmg > 0 and not user_poke.is_fainted:
            if user_poke.ability == "magic-guard":
                # Magic Guard negates Life Orb recoil
                pass
            else:
                lo_recoil = max(1, math.floor(user_poke.max_hp * 0.1))
                user_poke.current_hp = max(0, user_poke.current_hp - lo_recoil)
                user_poke.item_revealed = True
                self.log("item", f"⚡ {user_poke.display_name} lost some HP from Life Orb! (-{lo_recoil} HP)", user_side.side_id)

        # Sitrus Berry trigger
        if opp_poke.has_item and opp_poke.item == "sitrus-berry" and 0 < opp_poke.current_hp <= math.floor(opp_poke.max_hp / 2):
            heal_amt = math.floor(opp_poke.max_hp * 0.25)
            opp_poke.current_hp = min(opp_poke.max_hp, opp_poke.current_hp + heal_amt)
            opp_poke.has_item = False
            opp_poke.item_revealed = True
            self.log("item", f"🍒 {opp_poke.display_name} ate its Sitrus Berry and restored HP! (+{heal_amt} HP)", opp_side.side_id)

        # Weakness Policy trigger (activates when surviving a damaging super-effective attack)
        if opp_poke.has_item and opp_poke.item == "weakness-policy" and not opp_poke.is_fainted and dmg > 0 and info.get("typeMult", 1.0) >= 2.0:
            opp_poke.has_item = False
            opp_poke.item = None
            opp_poke.item_revealed = True
            opp_poke.modify_stage("attack", 2)
            opp_poke.modify_stage("special-attack", 2)
            self.log("item", f"✨ [{opp_poke.display_name}'s Weakness Policy] Weakness Policy sharply raised Attack (+2) and Sp. Atk (+2)!", opp_side.side_id, {
                "item": "weakness-policy",
                "attack": opp_poke.stages.get("attack", 0),
                "specialAttack": opp_poke.stages.get("special-attack", 0)
            })

        # Secondary status ailments on damaging attack
        if not opp_poke.is_fainted and opp_poke.status is None:
            # Burn chance (e.g. Scald 30%, Flamethrower 10%, Flare Blitz 10%)
            b_chance = m_data.get("burn_chance", 0)
            if b_chance > 0 and random.randint(1, 100) <= b_chance and "fire" not in opp_poke.types and opp_poke.ability != "thermal-exchange":
                opp_poke.status = "burn"
                opp_poke.status_turns = 1
                self.log("status", f"🔥 {opp_poke.display_name} was burned by {m_human}!", opp_side.side_id, {"status": "burn"})
                self.check_status_berry(opp_poke, opp_side)

            # Paralyze chance (e.g. Thunderbolt 10%)
            p_chance = m_data.get("paralyze_chance", 0)
            if p_chance > 0 and random.randint(1, 100) <= p_chance and "electric" not in opp_poke.types:
                opp_poke.status = "paralysis"
                opp_poke.status_turns = 1
                self.log("status", f"⚡ {opp_poke.display_name} was paralyzed by {m_human}!", opp_side.side_id, {"status": "paralysis"})
                self.check_status_berry(opp_poke, opp_side)

            # Freeze chance (e.g. Ice Beam 10%, Blizzard 10%)
            fr_chance = m_data.get("freeze_chance", 0)
            if fr_chance > 0 and random.randint(1, 100) <= fr_chance and "ice" not in opp_poke.types and self.weather != "sun":
                opp_poke.status = "freeze"
                opp_poke.status_turns = 1
                self.log("status", f"❄️ {opp_poke.display_name} was frozen solid by {m_human}!", opp_side.side_id, {"status": "freeze"})
                self.check_status_berry(opp_poke, opp_side)

            # Poison chance (e.g. Sludge Bomb 30%)
            ps_chance = m_data.get("poison_chance", 0)
            if ps_chance > 0 and random.randint(1, 100) <= ps_chance and "poison" not in opp_poke.types and "steel" not in opp_poke.types:
                opp_poke.status = "poison"
                opp_poke.status_turns = 1
                self.log("status", f"☠️ {opp_poke.display_name} was poisoned by {m_human}!", opp_side.side_id, {"status": "poison"})
                self.check_status_berry(opp_poke, opp_side)

        # Secondary confusion chance on damaging attack
        conf_chance = 1.0 if move_name == "dynamic-punch" else (0.3 if move_name == "hurricane" else (0.2 if move_name in ("water-pulse", "confusion", "psybeam") else 0.0))
        if conf_chance > 0 and not opp_poke.is_fainted and not opp_poke.is_confused and random.random() < conf_chance:
            if opp_poke.ability != "own-tempo":
                opp_poke.is_confused = True
                opp_poke.confusion_turns = random.randint(2, 5)
                self.log("status", f"💫 {opp_poke.display_name} became confused from the attack!", opp_side.side_id, {"status": "confusion"})
                self.check_status_berry(opp_poke, opp_side)

        # Max Move & G-Max Move Secondary Effects
        if user_poke.is_gmax and max_info:
            std = max_info.get("stdMeta")
            gmeta = max_info.get("gmaxMeta")

            # 1. Weather
            w_to_set = (gmeta and gmeta.get("weather")) or (std and std.get("weather"))
            if w_to_set and self.weather != w_to_set:
                self.weather = w_to_set
                self.weather_turns = 5
                w_msgs = {
                    "sun": "☀️ The sunlight turned harsh!",
                    "rain": "🌧️ Rain began to fall!",
                    "snow": "❄️ Snow began to fall!",
                    "sandstorm": "🏜️ A sandstorm kicked up!"
                }
                self.log("weather", w_msgs.get(w_to_set, f"The weather became {w_to_set}!"), user_side.side_id, {"weather": w_to_set})

            # 2. Terrain
            t_to_set = (gmeta and gmeta.get("terrain")) or (std and std.get("terrain"))
            if t_to_set and self.terrain != t_to_set:
                self.terrain = t_to_set
                self.terrain_turns = 5
                t_msgs = {
                    "electric": "⚡ An electric current ran across the battlefield!",
                    "grassy": "🌿 Grass grew all over the battlefield!",
                    "psychic": "🔮 The battlefield got weird!",
                    "misty": "🌸 Mist swirled around the battlefield!"
                }
                self.log("terrain", t_msgs.get(t_to_set, f"The terrain became {t_to_set}!"), user_side.side_id, {"terrain": t_to_set})

            # 3. User Stat Boosts (Max Knuckle, Max Ooze, Max Quake, Max Steelspike, Max Airstream)
            user_boosts = std and std.get("self_stat_boost")
            if user_boosts and not user_poke.is_fainted:
                for stat, amt in user_boosts.items():
                    user_poke.modify_stage(stat, amt)
                    self.log("stat", f"📈 [{user_poke.display_name}] {format_stat_name(stat)} rose!", user_side.side_id, {"stat": stat, "delta": amt})

            # 4. Target Stat Drops (Max Strike, Max Wyrmwind, Max Phantasm, Max Flutterby, Max Darkness, G-Max Replenish)
            target_drops = (gmeta and gmeta.get("target_stat_drop")) or (std and std.get("target_stat_drop"))
            if target_drops and opp_poke and not opp_poke.is_fainted:
                if opp_poke.has_item and opp_poke.item == "clear-amulet":
                    self.log("item", f"🛡️ [{opp_poke.display_name}'s Clear Amulet] Protected its stats from being lowered!", opp_side.side_id)
                elif opp_poke.ability in ("clear-body", "white-smoke", "hyper-cutter", "full-metal-body"):
                    self.log("ability", f"✨ [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Protected its stats from being lowered!", opp_side.side_id)
                else:
                    for stat, amt in target_drops.items():
                        opp_poke.modify_stage(stat, amt)
                        self.log("stat", f"📉 [{opp_poke.display_name}] {format_stat_name(stat)} fell!", opp_side.side_id, {"stat": stat, "delta": amt})
                        if opp_poke.ability == "defiant":
                            opp_poke.modify_stage("attack", 2)
                            self.log("ability", f"✨ [{opp_poke.display_name}'s Defiant] Atk rose sharply (+2)!", opp_side.side_id)
                        elif opp_poke.ability == "competitive":
                            opp_poke.modify_stage("special-attack", 2)
                            self.log("ability", f"✨ [{opp_poke.display_name}'s Competitive] SpA rose sharply (+2)!", opp_side.side_id)

            # 5. Exclusive G-Max Effects
            if gmeta:
                if gmeta.get("wildfire"):
                    opp_side.gmax_wildfire_turns = 4
                    self.log("field", f"🔥 [{user_side.name}] G-Max Wildfire engulfed {opp_side.name}'s field in a sea of fire!", user_side.side_id)
                if gmeta.get("cannonade"):
                    opp_side.gmax_cannonade_turns = 4
                    self.log("field", f"🌊 [{user_side.name}] G-Max Cannonade surrounded {opp_side.name}'s field in raging water!", user_side.side_id)
                if gmeta.get("vinelash"):
                    opp_side.gmax_vinelash_turns = 4
                    self.log("field", f"🌿 [{user_side.name}] G-Max Vine Lash trapped {opp_side.name}'s field in thorny vines!", user_side.side_id)
                if gmeta.get("volcalith"):
                    opp_side.gmax_volcalith_turns = 4
                    self.log("field", f"🪨 [{user_side.name}] G-Max Volcalith surrounded {opp_side.name}'s field in molten rocks!", user_side.side_id)
                if gmeta.get("steelsurge"):
                    opp_side.hazards["steelsurge"] = True
                    self.log("field", f"⚙️ [{user_side.name}] G-Max Steelsurge scattered sharp steel spikes across {opp_side.name}'s field!", user_side.side_id)
                if gmeta.get("stealth_rock"):
                    opp_side.hazards["stealth_rock"] = True
                    self.log("field", f"🪨 [{user_side.name}] G-Max Stonesurge scattered sharp rocks across {opp_side.name}'s field!", user_side.side_id)
                if gmeta.get("heal_team"):
                    heal_amt = max(1, math.floor(user_poke.max_hp * gmeta["heal_team"]))
                    for ally in user_side.team:
                        if not ally.is_fainted:
                            ally.current_hp = min(ally.max_hp, ally.current_hp + heal_amt)
                    self.log("heal", f"✨ [{user_side.name}] G-Max Finale restored HP to the entire team!", user_side.side_id)
                if gmeta.get("cure_status"):
                    for ally in user_side.team:
                        ally.status = None
                        ally.status_turns = 0
                    self.log("status", f"✨ [{user_side.name}] G-Max Sweetness cured the entire team of all status conditions!", user_side.side_id)
                if gmeta.get("crit_boost"):
                    user_poke.crit_stage = getattr(user_poke, "crit_stage", 0) + gmeta["crit_boost"]
                    self.log("stat", f"🎯 [{user_poke.display_name}] G-Max Chi Strike heightened critical-hit ratio!", user_side.side_id)
                if gmeta.get("sets_veil"):
                    user_side.aurora_veil_turns = 5
                    self.log("field", f"❄️ [{user_side.name}] G-Max Resonance set up Aurora Veil for your team!", user_side.side_id)
                if gmeta.get("clear_field"):
                    opp_side.reflect_turns = 0
                    opp_side.light_screen_turns = 0
                    opp_side.aurora_veil_turns = 0
                    user_side.stealth_rock = False
                    opp_side.stealth_rock = False
                    user_side.hazards = {"stealth_rock": False, "spikes": 0, "toxic_spikes": 0, "sticky_web": False, "steelsurge": False}
                    opp_side.hazards = {"stealth_rock": False, "spikes": 0, "toxic_spikes": 0, "sticky_web": False, "steelsurge": False}
                    self.terrain = None
                    self.terrain_turns = 0
                    self.log("field", f"🌪️ [{user_side.name}] G-Max Wind Rage blew away all screens, hazards, and terrain!", user_side.side_id)
                if gmeta.get("inflict_confusion") and opp_poke and not opp_poke.is_fainted:
                    if not opp_poke.is_confused and opp_poke.ability != "own-tempo":
                        opp_poke.is_confused = True
                        opp_poke.confusion_turns = random.randint(2, 5)
                        self.log("status", f"💫 [{opp_poke.display_name}] became confused from G-Max Smite!", opp_side.side_id)
                if gmeta.get("inflict_yawn") and opp_poke and not opp_poke.is_fainted:
                    if opp_poke.status is None and getattr(opp_poke, "yawn_turns", 0) == 0:
                        opp_poke.yawn_turns = 2
                        self.log("status", f"💤 [{opp_poke.display_name}] grew drowsy from G-Max Snooze!", opp_side.side_id)
                if gmeta.get("inflict_paralysis") and opp_poke and not opp_poke.is_fainted:
                    if opp_poke.status is None and "electric" not in opp_poke.types:
                        opp_poke.status = "paralysis"
                        opp_poke.status_turns = 1
                        self.log("status", f"⚡ [{opp_poke.display_name}] was paralyzed by G-Max Volt Crash!", opp_side.side_id, {"status": "paralysis"})
                        self.check_status_berry(opp_poke, opp_side)
                if gmeta.get("inflict_paralyze_or_poison") and opp_poke and not opp_poke.is_fainted:
                    if opp_poke.status is None:
                        ailment = "paralysis" if "poison" in opp_poke.types or "steel" in opp_poke.types else ("poison" if "electric" in opp_poke.types else random.choice(["paralysis", "poison"]))
                        opp_poke.status = ailment
                        opp_poke.status_turns = 1
                        self.log("status", f"⚡ [{opp_poke.display_name}] was afflicted with {ailment} by G-Max Stun Shock!", opp_side.side_id, {"status": ailment})
                        self.check_status_berry(opp_poke, opp_side)

        # Check defender faint
        if opp_poke.is_fainted:
            self.log("faint", f"☠️ {opp_poke.display_name} fainted!", opp_side.side_id, {
                "species": opp_poke.species,
                "displayName": opp_poke.display_name,
                "killerSpecies": user_poke.species,
                "killerDisplayName": user_poke.display_name,
                "killerMove": m_human
            })
            if user_poke.ability == "moxie":
                user_poke.modify_stage("attack", 1)
                self.log("ability", f"✨ [{user_poke.display_name}'s Moxie] Atk rose!", user_side.side_id)
            self.prompt_replacement(opp_side)

        # Check self-destruct / suicide moves (Final Gambit, Explosion, Self-Destruct, Misty Explosion)
        if move_lower == "final-gambit" or m_data.get("self_destruct"):
            self.suicide_side = user_side.side_id
            user_poke.current_hp = 0
            self.log("faint", f"☠️ {user_poke.display_name} fainted from using {m_human}!", user_side.side_id, {
                "species": user_poke.species, "displayName": user_poke.display_name, "selfFaint": True
            })
            self.prompt_replacement(user_side)
        # Check attacker faint (from recoil, Rocky Helmet, Life Orb, Rough Skin)
        elif user_poke.is_fainted:
            self.log("faint", f"☠️ {user_poke.display_name} fainted!", user_side.side_id, {"species": user_poke.species})
            self.prompt_replacement(user_side)

        # Check pivot move switch (U-Turn, Volt Switch, Flip Turn)
        if m_data.get("pivot") and not user_poke.is_fainted:
            alive_bench = user_side.get_alive_bench_indices()
            if alive_bench:
                target_switch_idx = pivot_target_index if (pivot_target_index is not None and pivot_target_index in alive_bench) else alive_bench[0]
                self.perform_switch(user_side, opp_side, target_switch_idx, is_replacement=False, is_pivot=True)

    def handle_status_move(self, user_side: BattleSide, opp_side: BattleSide, user_poke: PokemonState, opp_poke: PokemonState, m_data: Dict[str, Any], m_human: str, pivot_target_index: Optional[int] = None):
        """Processes heals, boosts, field conditions, item swaps, substitute, and status ailments with Good as Gold immunity."""
        move_lower = (m_data.get("id") or m_data.get("name") or "").lower().strip()

        # Substitute: sacrifices 25% max HP to create a protective decoy doll
        if move_lower == "substitute":
            if getattr(user_poke, "substitute_hp", 0) > 0:
                self.log("move", f"❌ But it failed! {user_poke.display_name} already has a substitute active!", user_side.side_id, {"failed": True})
                return
            sub_cost = math.floor(user_poke.max_hp * 0.25)
            if user_poke.current_hp <= sub_cost:
                self.log("move", f"❌ But it failed! Not enough HP to create a substitute!", user_side.side_id, {"failed": True})
                return
            user_poke.current_hp -= sub_cost
            user_poke.substitute_hp = sub_cost
            cost_pct = round((sub_cost / user_poke.max_hp) * 100, 1)
            self.log("move", f"🧸 [{user_side.name}] {user_poke.display_name} put in a substitute! (-{sub_cost} HP, {cost_pct}%)", user_side.side_id, {
                "substitute": True,
                "substituteHp": user_poke.substitute_hp,
                "cost": sub_cost
            })
            return

        # Reflect, Light Screen, Aurora Veil
        if move_lower == "reflect":
            user_side.reflect_turns = 8 if (user_poke.has_item and user_poke.item == "light-clay") else 5
            self.log("field", f"🛡️ [{user_side.name}] Reflect raised physical Defense!", user_side.side_id)
            return
        elif move_lower == "light-screen":
            user_side.light_screen_turns = 8 if (user_poke.has_item and user_poke.item == "light-clay") else 5
            self.log("field", f"✨ [{user_side.name}] Light Screen raised special Defense!", user_side.side_id)
            return
        elif move_lower == "aurora-veil":
            eff_w = self.get_effective_weather()
            if eff_w == "snow":
                user_side.aurora_veil_turns = 8 if (user_poke.has_item and user_poke.item == "light-clay") else 5
                self.log("field", f"❄️ [{user_side.name}] Aurora Veil strengthened team against physical & special moves!", user_side.side_id)
            else:
                self.log("move", f"But it failed! Aurora Veil only works in Snow.", user_side.side_id)
            return

        # Target behind Substitute check: Infiltrator and sound moves bypass
        bypasses_sub = (user_poke.ability == "infiltrator" or move_lower in SOUND_MOVES)
        target_sub_active = (opp_poke and getattr(opp_poke, "substitute_hp", 0) > 0 and not bypasses_sub)

        # Good as Gold check: Target is immune to all status moves!
        if opp_poke and opp_poke.ability == "good-as-gold":
            if m_data.get("inflict_status") or m_data.get("stat_drops") or m_data.get("taunt") or m_data.get("encore") or m_data.get("item_swap") or move_lower in ("trick", "switcheroo", "taunt", "yawn", "encore"):
                self.log("ability", f"✨ [{opp_poke.display_name}'s Good as Gold] Immune to status moves!", opp_side.side_id)
                return

        # Trick / Switcheroo (Held item exchange)
        if move_lower in ("trick", "switcheroo") or m_data.get("item_swap"):
            if not opp_poke or opp_poke.is_fainted:
                self.log("damage", f"❌ But it failed!", user_side.side_id, {"failed": True})
                return
            if target_sub_active:
                self.log("damage", f"❌ But it failed! {opp_poke.display_name} is behind a substitute!", user_side.side_id, {"failed": True})
                return

            if opp_poke.ability == "sticky-hold":
                self.log("ability", f"✨ [{opp_poke.display_name}'s Sticky Hold] Its item cannot be taken!", opp_side.side_id)
                return
            if user_poke.ability == "sticky-hold":
                self.log("ability", f"✨ [{user_poke.display_name}'s Sticky Hold] Its item cannot be taken!", user_side.side_id)
                return

            if not user_poke.has_item and not opp_poke.has_item:
                self.log("damage", f"❌ But it failed! Neither Pokémon holds an item.", user_side.side_id, {"failed": True})
                return

            untrickable = ("booster-energy", "rusted-sword", "rusted-shield", "griseous-core", "griseous-orb")
            has_untrickable_mega = (user_poke.get_mega_species_for_item() is not None) or (opp_poke.get_mega_species_for_item() is not None)
            if (user_poke.item in untrickable) or (opp_poke.item in untrickable) or has_untrickable_mega:
                self.log("damage", f"❌ But it failed! That item cannot be swapped.", user_side.side_id, {"failed": True})
                return

            user_item = user_poke.item
            opp_item = opp_poke.item

            user_poke.item = opp_item
            user_poke.has_item = bool(opp_item)
            user_poke.item_revealed = True

            opp_poke.item = user_item
            opp_poke.has_item = bool(user_item)
            opp_poke.item_revealed = True

            # If user no longer holds a choice item, release Choice Lock!
            if user_poke.item not in ("choice-band", "choice-specs", "choice-scarf"):
                user_poke.choice_locked_move = None
            else:
                user_poke.choice_locked_move = None

            # Reset recipient choice lock so it engages on their next selected move
            if opp_poke.item not in ("choice-band", "choice-specs", "choice-scarf"):
                opp_poke.choice_locked_move = None
            else:
                opp_poke.choice_locked_move = None

            u_name = humanize_name(user_item) if user_item else "no item"
            o_name = humanize_name(opp_item) if opp_item else "no item"
            self.log("item", f"🔄 [{user_poke.display_name}] Tricked its {u_name} onto {opp_poke.display_name} in exchange for its {o_name}!", user_side.side_id, {
                "userItem": opp_item,
                "oppItem": user_item
            })
            return

        # Self Healing (Recover, Soft-Boiled, Roost)
        if m_data.get("heal"):
            heal_amt = math.floor(user_poke.max_hp * m_data["heal"])
            user_poke.current_hp = min(user_poke.max_hp, user_poke.current_hp + heal_amt)
            self.log("heal", f"💚 {user_poke.display_name} recovered HP! (+{heal_amt} HP)", user_side.side_id)

        # Self Stat Boosts (Nasty Plot, Swords Dance, Dragon Dance, Quiver Dance)
        if m_data.get("self_boost"):
            for stat, boost in m_data["self_boost"].items():
                user_poke.modify_stage(stat, boost)
                word = "rose sharply!" if boost >= 2 else "rose!"
                self.log("stat", f"📈 [{user_poke.display_name}] {format_stat_name(stat)} {word}", user_side.side_id, {"stat": stat, "delta": boost})

        # Geomancy (Xerneas signature 2-turn move: charges, then raises SpA, SpD, Spe by +2)
        if move_lower == "geomancy":
            has_herb = (user_poke.has_item and user_poke.item == "power-herb")
            is_charged = (user_poke.charging_move == "geomancy")
            if has_herb and not is_charged:
                user_poke.has_item = False
                user_poke.item = None
                user_poke.item_revealed = True
                user_poke.charging_move = None
                for st in ("special-attack", "special-defense", "speed"):
                    user_poke.modify_stage(st, 2)
                self.log("item", f"🌿 [{user_poke.display_name}'s Power Herb] Power Herb allowed it to unleash Geomancy instantly! SpA, SpD, and Spe rose sharply (+2)!", user_side.side_id)
                return
            elif is_charged:
                user_poke.charging_move = None
                for st in ("special-attack", "special-defense", "speed"):
                    user_poke.modify_stage(st, 2)
                self.log("stat", f"✨ [{user_poke.display_name}] SpA, SpD, and Spe rose sharply (+2) from Geomancy!", user_side.side_id)
                return
            else:
                user_poke.charging_move = "geomancy"
                self.log("move", f"✨ [{user_side.name}] {user_poke.display_name} is absorbing power!", user_side.side_id, {
                    "move": m_human, "charging": True
                })
                return

        # Self Stat Drops on status moves (e.g. Shell Smash, Curse)
        if m_data.get("self_stat_drop") and not user_poke.is_fainted:
            for stat, drop in m_data["self_stat_drop"].items():
                user_poke.modify_stage(stat, drop)
                self.log("stat", f"📉 [{user_poke.display_name}] {format_stat_name(stat)} fell ({drop})!", user_side.side_id, {"stat": stat, "delta": drop})
            self.check_white_herb(user_poke, user_side)

        # Target Stat Drops on status moves (e.g. Screech, Fake Tears, Charm, Scary Face, Metal Sound)
        if m_data.get("stat_drops") and opp_poke and not opp_poke.is_fainted:
            if target_sub_active:
                self.log("status", f"❌ But it failed! {opp_poke.display_name} is behind a substitute!", user_side.side_id, {"failed": True})
            elif opp_poke.has_item and opp_poke.item == "clear-amulet":
                self.log("item", f"🛡️ [{opp_poke.display_name}'s Clear Amulet] Protected its stats from being lowered!", opp_side.side_id)
            elif opp_poke.ability in ("clear-body", "white-smoke", "hyper-cutter", "full-metal-body"):
                self.log("ability", f"✨ [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Protected its stats from being lowered!", opp_side.side_id)
            else:
                for stat, drop in m_data["stat_drops"].items():
                    opp_poke.modify_stage(stat, drop)
                    self.log("stat", f"📉 {opp_poke.display_name}'s {format_stat_name(stat)} fell ({drop})!", opp_side.side_id, {"stat": stat, "delta": drop})
                    if opp_poke.ability == "defiant":
                        opp_poke.modify_stage("attack", 2)
                        self.log("ability", f"✨ [{opp_poke.display_name}'s Defiant] Atk rose sharply (+2)!", opp_side.side_id)
                    elif opp_poke.ability == "competitive":
                        opp_poke.modify_stage("special-attack", 2)
                        self.log("ability", f"✨ [{opp_poke.display_name}'s Competitive] SpA rose sharply (+2)!", opp_side.side_id)
                self.check_white_herb(opp_poke, opp_side)

        # Field Effects (Tailwind, Trick Room)
        if m_data.get("field_effect") == "tailwind":
            user_side.tailwind_turns = 4
            self.log("field", f"🌪️ The tailwind blew from behind {user_side.name}'s team!", user_side.side_id)
        elif m_data.get("field_effect") == "trick_room":
            self.trick_room_turns = 5
            self.log("field", f"⏳ {user_poke.display_name} twisted the dimensions with Trick Room!", user_side.side_id)

        # Weather moves
        if m_data.get("weather"):
            self.weather = m_data["weather"]
            self.weather_turns = 5
            self.log("weather", f"🌧️ Weather changed to {self.weather}!", user_side.side_id)

        # Hazards (Stealth Rock, Spikes)
        if m_data.get("hazard") == "stealth_rock":
            if not opp_side.hazards.get("stealth_rock"):
                opp_side.hazards["stealth_rock"] = True
                self.log("hazard", f"🪨 Pointed stones float in the air around {opp_side.name}'s team!", opp_side.side_id)
        elif m_data.get("hazard") == "spikes":
            opp_side.hazards["spikes"] = min(3, opp_side.hazards.get("spikes", 0) + 1)
            self.log("hazard", f"📌 Spikes were scattered around {opp_side.name}'s feet!", opp_side.side_id)

        # Status Ailments (Will-O-Wisp, Thunder Wave, Spore, Toxic)
        if m_data.get("inflict_status") and opp_poke and not opp_poke.is_fainted:
            if target_sub_active:
                self.log("status", f"❌ But it failed! {opp_poke.display_name} is protected by its substitute!", user_side.side_id, {"failed": True})
                return
            st = m_data["inflict_status"]
            if opp_poke.status is not None:
                self.log("status", f"It had no effect! {opp_poke.display_name} is already afflicted.", opp_side.side_id)
            elif st == "burn" and ("fire" in opp_poke.types or opp_poke.ability == "thermal-exchange"):
                if opp_poke.ability == "thermal-exchange":
                    self.log("ability", f"✨ [{opp_poke.display_name}'s Thermal Exchange] Immune to burns!", opp_side.side_id)
                else:
                    self.log("status", f"It had no effect on Fire-type {opp_poke.display_name}!", opp_side.side_id)
            elif st == "paralysis" and "electric" in opp_poke.types:
                self.log("status", f"It had no effect on Electric-type {opp_poke.display_name}!", opp_side.side_id)
            elif st in ("poison", "toxic") and ("poison" in opp_poke.types or "steel" in opp_poke.types):
                self.log("status", f"It had no effect on {opp_poke.display_name}!", opp_side.side_id)
            elif self.terrain == "electric" and st == "sleep" and self.is_grounded(opp_poke):
                self.log("status", f"Electric Terrain prevents {opp_poke.display_name} from falling asleep!", opp_side.side_id)
            elif self.terrain == "misty" and self.is_grounded(opp_poke):
                self.log("status", f"Misty Terrain protects {opp_poke.display_name} from status conditions!", opp_side.side_id)
            else:
                opp_poke.status = st
                opp_poke.status_turns = random.randint(1, 3) if st == "sleep" else 1
                self.log("status", f"⚠️ {opp_poke.display_name} was inflicted with {humanize_name(st)}!", opp_side.side_id, {"status": st})
                self.check_status_berry(opp_poke, opp_side)

        # Team Status Healing (Heal Bell, Aromatherapy)
        if move_lower in ("heal-bell", "aromatherapy"):
            for p in user_side.team:
                p.status = None
                p.status_turns = 0
            self.log("status", f"🔔 A soothing chime echoed! {user_side.name}'s party status ailments were cured!", user_side.side_id)

        # Rest (full heal + 2 turn sleep)
        if move_lower == "rest":
            user_poke.current_hp = user_poke.max_hp
            user_poke.status = "sleep"
            user_poke.status_turns = 2
            self.log("status", f"💤 {user_poke.display_name} slept and fully restored its HP!", user_side.side_id)
            self.check_status_berry(user_poke, user_side)

        # Confusion Moves (Confuse Ray, Sweet Kiss, Supersonic, Teeter Dance)
        if move_lower in ("confuse-ray", "sweet-kiss", "supersonic", "teeter-dance") or m_data.get("inflict_confusion"):
            if opp_poke and not opp_poke.is_fainted:
                if target_sub_active and move_lower not in SOUND_MOVES:
                    self.log("status", f"❌ But it failed! {opp_poke.display_name} is protected by its substitute!", user_side.side_id, {"failed": True})
                    return
                if opp_poke.ability == "own-tempo":
                    self.log("ability", f"✨ [{opp_poke.display_name}'s Own Tempo] Prevents confusion!", opp_side.side_id)
                elif opp_poke.is_confused:
                    self.log("status", f"{opp_poke.display_name} is already confused!", opp_side.side_id)
                else:
                    opp_poke.is_confused = True
                    opp_poke.confusion_turns = random.randint(2, 5)
                    self.log("status", f"💫 {opp_poke.display_name} became confused!", opp_side.side_id, {"status": "confusion"})
                    self.check_status_berry(opp_poke, opp_side)

        # Yawn (Causes drowsiness, then sleep next turn)
        if move_lower == "yawn":
            if not opp_poke or opp_poke.is_fainted:
                self.log("damage", f"❌ But it failed!", user_side.side_id, {"failed": True})
                return
            if target_sub_active:
                self.log("damage", f"❌ But it failed! {opp_poke.display_name} is behind a substitute!", user_side.side_id, {"failed": True})
                return
            if opp_poke.status is not None or getattr(opp_poke, "yawn_turns", 0) > 0:
                self.log("damage", f"❌ But it failed! {opp_poke.display_name} already has a status condition.", user_side.side_id, {"failed": True})
                return
            is_grounded = self.is_grounded(opp_poke)
            if self.terrain == "electric" and is_grounded:
                self.log("terrain", f"⚡ Electric Terrain prevents {opp_poke.display_name} from growing drowsy!", opp_side.side_id)
                return
            if self.terrain == "misty" and is_grounded:
                self.log("terrain", f"🌸 Misty Terrain prevents {opp_poke.display_name} from growing drowsy!", opp_side.side_id)
                return
            if opp_poke.ability in ("insomnia", "vital-spirit"):
                self.log("ability", f"✨ [{opp_poke.display_name}'s {humanize_name(opp_poke.ability)}] Immune to drowsiness!", opp_side.side_id)
                return

            opp_poke.yawn_turns = 2
            self.log("status", f"😴 {opp_poke.display_name} grew drowsy!", opp_side.side_id, {"yawn": True})

        # Taunt
        if move_lower == "taunt":
            if opp_poke and not opp_poke.is_fainted:
                if target_sub_active:
                    self.log("status", f"❌ But it failed! {opp_poke.display_name} is behind a substitute!", user_side.side_id, {"failed": True})
                    return
                if opp_poke.ability == "oblivious":
                    self.log("ability", f"✨ [{opp_poke.display_name}'s Oblivious] Immune to taunt!", opp_side.side_id)
                else:
                    opp_poke.taunt_turns = 3
                    self.log("status", f"🤬 {opp_poke.display_name} fell for the taunt!", opp_side.side_id, {"status": "taunt"})

        # Attract
        if move_lower == "attract":
            if opp_poke and not opp_poke.is_fainted:
                if target_sub_active:
                    self.log("status", f"❌ But it failed! {opp_poke.display_name} is behind a substitute!", user_side.side_id, {"failed": True})
                    return
                if opp_poke.ability == "oblivious":
                    self.log("ability", f"✨ [{opp_poke.display_name}'s Oblivious] Immune to infatuation!", opp_side.side_id)
                else:
                    opp_poke.is_infatuated = True
                    self.log("status", f"❤️ {opp_poke.display_name} fell in love!", opp_side.side_id, {"status": "infatuation"})

        # Shed Tail: cuts 50% max HP, creates a 25% max HP substitute, and pivots out passing it!
        if move_lower == "shed-tail":
            alive_bench = user_side.get_alive_bench_indices()
            hp_cost = math.floor(user_poke.max_hp * 0.5)
            if not alive_bench:
                self.log("move", f"❌ But it failed! No Pokémon available to switch in!", user_side.side_id, {"failed": True})
                return
            if user_poke.current_hp <= hp_cost:
                self.log("move", f"❌ But it failed! {user_poke.display_name} did not have enough HP to shed its tail!", user_side.side_id, {"failed": True})
                return
            user_poke.current_hp -= hp_cost
            sub_created = math.floor(user_poke.max_hp * 0.25)
            cost_pct = round((hp_cost / user_poke.max_hp) * 100, 1)
            self.log("move", f"🦎 [{user_side.name}] {user_poke.display_name} shed its tail! (-{hp_cost} HP, {cost_pct}%)", user_side.side_id, {
                "shedTail": True,
                "substituteHp": sub_created,
                "cost": hp_cost
            })
            target_switch_idx = pivot_target_index if (pivot_target_index is not None and pivot_target_index in alive_bench) else alive_bench[0]
            self.perform_switch(user_side, opp_side, target_switch_idx, is_replacement=False, is_pivot=True, is_baton_pass=False, passed_substitute=sub_created)
            return

        # Check pivot on status moves (Parting Shot, Chilly Reception, Shed Tail, Baton Pass, Teleport)
        if m_data.get("pivot") and not user_poke.is_fainted:
            alive_bench = user_side.get_alive_bench_indices()
            if alive_bench:
                target_switch_idx = pivot_target_index if (pivot_target_index is not None and pivot_target_index in alive_bench) else alive_bench[0]
                is_bp = (move_lower == "baton-pass")
                self.perform_switch(user_side, opp_side, target_switch_idx, is_replacement=False, is_pivot=True, is_baton_pass=is_bp)

    def resolve_end_of_turn(self):
        """End-of-turn countdowns, Leftovers healing, Sandstorm, Burn chip, etc."""
        # 1. Weather damage / Leftovers / Grassy Terrain
        for s in (self.side1, self.side2):
            p = s.active_pokemon
            if not p or p.is_fainted:
                continue

            # Leftovers recovery
            if p.has_item and p.item == "leftovers" and p.current_hp < p.max_hp:
                heal = math.floor(p.max_hp / 16)
                p.current_hp = min(p.max_hp, p.current_hp + heal)
                p.item_revealed = True
                self.log("item", f"🍎 {p.display_name} restored a little HP using Leftovers! (+{heal} HP)", s.side_id)

            # Grassy terrain healing
            if self.terrain == "grassy" and "flying" not in p.types and p.ability != "levitate":
                if p.current_hp < p.max_hp:
                    heal = math.floor(p.max_hp / 16)
                    p.current_hp = min(p.max_hp, p.current_hp + heal)
                    self.log("terrain", f"🌱 Grassy terrain restored {p.display_name}'s HP! (+{heal} HP)", s.side_id)

            # Weather chip (Sandstorm)
            if self.weather == "sandstorm" and not any(t in p.types for t in ("rock", "ground", "steel")):
                chip = math.floor(p.max_hp / 16)
                p.current_hp = max(0, p.current_hp - chip)
                self.log("weather", f"🌪️ {p.display_name} was buffeted by the sandstorm! (-{chip} HP)", s.side_id)

            # Status Healing Abilities at End of Turn (Shed Skin, Hydration)
            if p.ability == "shed-skin" and p.status is not None and random.random() < 0.33:
                cured_st = p.status
                p.status = None
                p.status_turns = 0
                self.log("ability", f"✨ [{p.display_name}'s Shed Skin] Shed its skin and cured its {cured_st}!", s.side_id)
            elif p.ability == "hydration" and p.status is not None and self.weather == "rain":
                cured_st = p.status
                p.status = None
                p.status_turns = 0
                self.log("ability", f"✨ [{p.display_name}'s Hydration] The rain cured its {cured_st}!", s.side_id)

            # Volatile Taunt countdown
            if p.taunt_turns > 0:
                p.taunt_turns -= 1
                if p.taunt_turns == 0:
                    self.log("status", f"{p.display_name}'s taunt wore off!", s.side_id)

            # Yawn Drowsiness & Sleep Countdown (Causes sleep on the turn after Yawn)
            if getattr(p, "yawn_turns", 0) > 0:
                p.yawn_turns -= 1
                if p.yawn_turns == 0:
                    if p.status is None:
                        is_grounded = self.is_grounded(p)
                        if self.terrain == "electric" and is_grounded:
                            self.log("terrain", f"⚡ Electric Terrain prevents {p.display_name} from falling asleep!", s.side_id)
                        elif self.terrain == "misty" and is_grounded:
                            self.log("terrain", f"🌸 Misty Terrain prevents {p.display_name} from falling asleep!", s.side_id)
                        elif p.ability in ("insomnia", "vital-spirit"):
                            self.log("ability", f"✨ [{p.display_name}'s {humanize_name(p.ability)}] Stayed awake!", s.side_id)
                        else:
                            p.status = "sleep"
                            p.status_turns = random.randint(1, 3)
                            self.log("status", f"💤 {p.display_name} fell asleep from drowsiness!", s.side_id, {"status": "sleep"})
                            self.check_status_berry(p, s)

            # Status Orb Activation (Flame Orb, Toxic Orb)
            if p.has_item and p.status is None:
                if p.item == "flame-orb" and "fire" not in p.types:
                    p.status = "burn"
                    p.status_turns = 1
                    p.item_revealed = True
                    self.log("item", f"🔥 [{p.display_name}'s Flame Orb] {p.display_name} was burned by its Flame Orb!", s.side_id, {"status": "burn"})
                elif p.item == "toxic-orb" and "poison" not in p.types and "steel" not in p.types:
                    p.status = "toxic"
                    p.status_turns = 1
                    p.item_revealed = True
                    self.log("item", f"☣️ [{p.display_name}'s Toxic Orb] {p.display_name} was badly poisoned by its Toxic Orb!", s.side_id, {"status": "toxic"})

            # Status damage (Burn, Poison, Toxic)
            if p.status == "burn":
                chip = max(1, math.floor(p.max_hp / 16))
                p.current_hp = max(0, p.current_hp - chip)
                self.log("status", f"🔥 {p.display_name} is hurt by its burn! (-{chip} HP)", s.side_id)
            elif p.status == "poison":
                chip = max(1, math.floor(p.max_hp / 8))
                p.current_hp = max(0, p.current_hp - chip)
                self.log("status", f"🧪 {p.display_name} is hurt by poison! (-{chip} HP)", s.side_id)
            elif p.status == "toxic":
                p.status_turns += 1
                chip = max(1, math.floor(p.max_hp * (p.status_turns / 16)))
                p.current_hp = max(0, p.current_hp - chip)
                self.log("status", f"☣️ {p.display_name} is hurt by toxic poison! (-{chip} HP)", s.side_id)

            # G-Max Lingering Field Damage (Wildfire, Cannonade, Vine Lash, Volcalith: 1/6 max HP chip to non-matching types)
            if s.gmax_wildfire_turns > 0 and p and not p.is_fainted:
                s.gmax_wildfire_turns -= 1
                if "fire" not in p.types:
                    wf_chip = max(1, math.floor(p.max_hp / 6))
                    p.current_hp = max(0, p.current_hp - wf_chip)
                    self.log("field", f"🔥 [{p.display_name}] was burned by the sea of fire from G-Max Wildfire! (-{wf_chip} HP)", s.side_id)

            if s.gmax_cannonade_turns > 0 and p and not p.is_fainted:
                s.gmax_cannonade_turns -= 1
                if "water" not in p.types:
                    cn_chip = max(1, math.floor(p.max_hp / 6))
                    p.current_hp = max(0, p.current_hp - cn_chip)
                    self.log("field", f"🌊 [{p.display_name}] was buffeted by the torrent of G-Max Cannonade! (-{cn_chip} HP)", s.side_id)

            if s.gmax_vinelash_turns > 0 and p and not p.is_fainted:
                s.gmax_vinelash_turns -= 1
                if "grass" not in p.types:
                    vl_chip = max(1, math.floor(p.max_hp / 6))
                    p.current_hp = max(0, p.current_hp - vl_chip)
                    self.log("field", f"🌿 [{p.display_name}] was whipped by the ferocious vines of G-Max Vine Lash! (-{vl_chip} HP)", s.side_id)

            if s.gmax_volcalith_turns > 0 and p and not p.is_fainted:
                s.gmax_volcalith_turns -= 1
                if "rock" not in p.types:
                    vc_chip = max(1, math.floor(p.max_hp / 6))
                    p.current_hp = max(0, p.current_hp - vc_chip)
                    self.log("field", f"🪨 [{p.display_name}] was scorched by the jagged rocks of G-Max Volcalith! (-{vc_chip} HP)", s.side_id)

            # Check faint from status/chip
            if p.is_fainted:
                self.log("faint", f"☠️ {p.display_name} fainted!", s.side_id)
                self.prompt_replacement(s)
            else:
                p.turns_on_field += 1
                if s.side_id not in getattr(self, "switched_in_this_turn", set()):
                    p.can_fake_out = False
                self.check_status_berry(p, s)
                if p.is_gmax and p.gmax_turns > 0:
                    p.gmax_turns -= 1
                    if p.gmax_turns <= 0:
                        p.is_gmax = False
                        p.max_hp = max(1, math.floor(p.max_hp / 1.5))
                        p.current_hp = min(p.max_hp, p.current_hp)
                        self.log("omni", f"⚡ [{s.name}] {p.display_name}'s Gigantamax energy subsided!", s.side_id, {"omniEnd": "gmax"})

        # 2. Countdowns
        if self.weather_turns > 0:
            self.weather_turns -= 1
            if self.weather_turns == 0:
                self.log("weather", f"The {self.weather} subsided.")
                self.weather = "none"

        if self.terrain_turns > 0:
            self.terrain_turns -= 1
            if self.terrain_turns == 0:
                self.log("terrain", f"The {self.terrain} terrain disappeared.")
                self.terrain = "none"

        if self.trick_room_turns > 0:
            self.trick_room_turns -= 1
            if self.trick_room_turns == 0:
                self.log("field", "The twisted dimensions returned to normal!")

        for s in (self.side1, self.side2):
            if s.tailwind_turns > 0:
                s.tailwind_turns -= 1
                if s.tailwind_turns == 0:
                    self.log("field", f"{s.name}'s tailwind petered out!", s.side_id)
            if s.reflect_turns > 0:
                s.reflect_turns -= 1
                if s.reflect_turns == 0:
                    self.log("field", f"{s.name}'s Reflect wore off!", s.side_id)
            if s.light_screen_turns > 0:
                s.light_screen_turns -= 1
                if s.light_screen_turns == 0:
                    self.log("field", f"{s.name}'s Light Screen wore off!", s.side_id)
            if s.aurora_veil_turns > 0:
                s.aurora_veil_turns -= 1
                if s.aurora_veil_turns == 0:
                    self.log("field", f"{s.name}'s Aurora Veil wore off!", s.side_id)

    def prompt_replacement(self, side: BattleSide):
        """Auto-replaces fainted Pokémon with the best available alive teammate for AI, or flags pendingSwitch for human."""
        if not side.has_alive_pokemon:
            return
        alive = side.get_alive_bench_indices()
        if not alive:
            return
        opp_side = self.side2 if side.side_id == "side1" else self.side1

        if side.is_ai:
            chosen_idx = self.choose_ai_replacement(side, opp_side)
            self.perform_switch(side, opp_side, chosen_idx, is_replacement=True)
        else:
            self.pending_switch[side.side_id] = True

    def choose_ai_replacement(self, side: BattleSide, opp_side: BattleSide) -> int:
        """Selects optimal replacement based on HP and defensive/offensive matchup."""
        alive = side.get_alive_bench_indices()
        if not alive:
            return 0
        if len(alive) == 1:
            return alive[0]
        opp_active = opp_side.active_pokemon
        if not opp_active:
            return alive[0]

        best_score = -999.0
        best_idx = alive[0]
        for idx in alive:
            cand = side.team[idx]
            score = (cand.current_hp / max(1, cand.max_hp)) * 40.0
            for o_type in opp_active.types:
                eff = 1.0
                for c_type in cand.types:
                    eff *= get_type_multiplier(o_type, [c_type])
                if eff < 1.0:
                    score += 25.0
                elif eff > 1.0:
                    score -= 25.0
            for c_type in cand.types:
                eff = get_type_multiplier(c_type, opp_active.types)
                if eff > 1.0:
                    score += 20.0
            if score > best_score:
                best_score = score
                best_idx = idx
        return best_idx

    def check_faint_and_win(self):
        """Checks if either side has run out of usable Pokémon."""
        s1_alive = self.side1.has_alive_pokemon
        s2_alive = self.side2.has_alive_pokemon

        if not s1_alive and not s2_alive:
            self.is_finished = True
            if getattr(self, "suicide_side", None):
                # Official rule: user of suicide move (Final Gambit/Explosion) loses if both players lose their last Pokemon
                self.winner = self.side2.side_id if self.suicide_side == "side1" else self.side1.side_id
                winner_side = self.side2 if self.suicide_side == "side1" else self.side1
                self.log("gameover", f"🏆 {winner_side.name} won the battle! (Self-sacrifice resulted in defeat)", winner_side.side_id)
            else:
                self.winner = "draw"
                self.log("gameover", "🏁 The battle ended in a draw!")
        elif not s1_alive:
            self.is_finished = True
            self.winner = self.side2.side_id
            self.log("gameover", f"🏆 {self.side2.name} won the battle!", self.side2.side_id)
        elif not s2_alive:
            self.is_finished = True
            self.winner = self.side1.side_id
            self.log("gameover", f"🏆 {self.side1.name} won the battle!", self.side1.side_id)

    def to_dict(self) -> Dict[str, Any]:
        """Complete serializable state dictionary."""
        return {
            "turn": self.turn,
            "ruleset": self.ruleset,
            "level": self.level,
            "field": {
                "weather": self.weather,
                "weatherTurns": self.weather_turns,
                "terrain": self.terrain,
                "terrainTurns": self.terrain_turns,
                "trickRoom": self.trick_room_turns,
                "gravity": self.gravity_turns
            },
            "side1": self.side1.to_dict(),
            "side2": self.side2.to_dict(),
            "winner": self.winner,
            "isFinished": self.is_finished,
            "battleLog": self.battle_log[-45:],
            "pendingSwitch": self.pending_switch.get("side1", False) if not self.side1.is_ai else False
        }
