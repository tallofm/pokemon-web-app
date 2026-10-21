# utils/type_effectiveness.py
"""Calculates Pokémon type effectiveness for defense, offense, and multi-type tooling."""

from fractions import Fraction
from typing import Dict, List
from utils.cache import get_type_cached

TYPES: List[str] = [
    "normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground",
    "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy"
]

DEF_BUCKETS_ORDER: List[str] = ["8x", "4x", "2x", "1x", "1/2x", "1/4x", "1/8x", "0x"]

DEF_MAP: Dict[Fraction, str] = {
    Fraction(8, 1): "8x",
    Fraction(4, 1): "4x",
    Fraction(2, 1): "2x",
    Fraction(1, 1): "1x",
    Fraction(1, 2): "1/2x",
    Fraction(1, 4): "1/4x",
    Fraction(1, 8): "1/8x",
    Fraction(0, 1): "0x",
}

OFF_BUCKETS_ORDER: List[str] = ["4x", "2x", "1x", "1/2x", "1/4x", "0x"]

OFF_MAP: Dict[Fraction, str] = {
    Fraction(4, 1): "4x",
    Fraction(2, 1): "2x",
    Fraction(1, 1): "1x",
    Fraction(1, 2): "1/2x",
    Fraction(1, 4): "1/4x",
    Fraction(0, 1): "0x",
}


def get_type_damage_relations(type_name: str) -> dict:
    """Get damage relations dictionary for a single type."""
    t = get_type_cached(type_name) or {}
    rel = t.get("damage_relations", {})

    def names(key):
        return [x["name"] if isinstance(x, dict) else x for x in rel.get(key, [])]

    return {
        "double_from": names("double_damage_from"),
        "half_from": names("half_damage_from"),
        "no_from": names("no_damage_from"),
        "double_to": names("double_damage_to"),
        "half_to": names("half_damage_to"),
        "no_to": names("no_damage_to"),
    }


def build_effectiveness(pokemon_types: List[str]) -> Dict[str, Dict]:
    """Compute defense vs all attack types and offense per move type vs all defenders."""
    clean_types = [t.lower() for t in pokemon_types]

    # Defense: incoming attack type -> multiplier vs this pokemon
    defense = {atk: 1.0 for atk in TYPES}
    for ptype in clean_types:
        rel = get_type_damage_relations(ptype)
        for atk in TYPES:
            if atk in rel["no_from"]:
                defense[atk] *= 0.0
            elif atk in rel["double_from"]:
                defense[atk] *= 2.0
            elif atk in rel["half_from"]:
                defense[atk] *= 0.5

    # Offense: for each of pokemon's types (move type), multiplier vs each single-type defender
    offense = {}
    for mtype in clean_types:
        rel = get_type_damage_relations(mtype)
        row = {}
        for defn in TYPES:
            mult = 1.0
            if defn in rel["no_to"]:
                mult = 0.0
            elif defn in rel["double_to"]:
                mult = 2.0
            elif defn in rel["half_to"]:
                mult = 0.5
            row[defn] = mult
        offense[mtype] = row

    return {"defense": defense, "offense": offense}


def mult_vs(attacking_type: str, defender_type: str) -> Fraction:
    """Return multiplier of attacking_type vs defender_type as a Fraction (0, 1/2, 1, 2)."""
    t = get_type_cached(attacking_type) or {}
    rel = t.get("damage_relations") or {}

    if any(x.get("name") == defender_type for x in rel.get("no_damage_to", [])):
        return Fraction(0, 1)
    if any(x.get("name") == defender_type for x in rel.get("double_damage_to", [])):
        return Fraction(2, 1)
    if any(x.get("name") == defender_type for x in rel.get("half_damage_to", [])):
        return Fraction(1, 2)
    return Fraction(1, 1)


def calc_defense_buckets(def_types: List[str], allowed_types: List[str] | None = None) -> Dict[str, List[str]]:
    """Group incoming attacking types into effectiveness buckets (8x down to 0x)."""
    types_to_check = allowed_types if allowed_types is not None else TYPES
    buckets = {k: [] for k in DEF_BUCKETS_ORDER}

    for atk in types_to_check:
        mult = Fraction(1, 1)
        for d in def_types:
            mult *= mult_vs(atk, d)
            if mult == 0:
                break
        key = DEF_MAP.get(mult, "1x")
        buckets[key].append(atk)

    return buckets


def calc_offense_buckets(attacking_types: List[str], allowed_types: List[str] | None = None) -> Dict[str, List[str]]:
    """Group defender types into effectiveness buckets for the given attacking types (combined dual-move product)."""
    types_to_check = allowed_types if allowed_types is not None else TYPES
    buckets = {k: [] for k in OFF_BUCKETS_ORDER}

    for d in types_to_check:
        mult = Fraction(1, 1)
        for atk in attacking_types:
            mult *= mult_vs(atk, d)
            if mult == 0:
                break
        key = OFF_MAP.get(mult, "1x")
        buckets[key].append(d)

    return buckets


def calc_offense_coverage_buckets(attacking_types: List[str], allowed_types: List[str] | None = None) -> Dict[str, List[str]]:
    """Group defender types by the best multiplier from any selected move (standard coverage)."""
    types_to_check = allowed_types if allowed_types is not None else TYPES
    buckets = {k: [] for k in OFF_BUCKETS_ORDER}

    for d in types_to_check:
        if not attacking_types:
            best_mult = Fraction(1, 1)
        else:
            best_mult = max(mult_vs(atk, d) for atk in attacking_types)
        key = OFF_MAP.get(best_mult, "1x")
        buckets[key].append(d)

    return buckets


def get_type_matrix(allowed_types: List[str] | None = None) -> Dict[str, Dict[str, float]]:
    """Return full multiplier matrix {atk: {defn: float(mult)}} for client-side live calculation."""
    types_to_use = allowed_types if allowed_types is not None else TYPES
    return {
        atk: {defn: float(mult_vs(atk, defn)) for defn in types_to_use}
        for atk in types_to_use
    }


def get_pokemon_with_types(def_types: List[str]) -> List[str]:
    """Get Pokémon names that have all selected defender types."""
    if not def_types:
        return []
    first = get_type_cached(def_types[0]) or {}
    names = {p["pokemon"]["name"] for p in first.get("pokemon", [])}
    for t in def_types[1:]:
        td = get_type_cached(t) or {}
        names &= {p["pokemon"]["name"] for p in td.get("pokemon", [])}
    return sorted(names)
