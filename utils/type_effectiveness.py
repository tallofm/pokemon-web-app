# utils/type_effectiveness.py
from typing import Dict, List
from utils.cache import get_type_cached
from utils.pokeapi import get_type

TYPES = [
    "normal","fire","water","electric","grass","ice","fighting","poison","ground",
    "flying","psychic","bug","rock","ghost","dragon","dark","steel","fairy"
]

def _relations(tname: str):
    """get damage relations for a single type"""
    t = get_type_cached(tname)  # no second arg
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
    """compute defense vs all attack types and offense per move type vs all defenders"""
    # defense: incoming attack type -> multiplier vs this pokemon
    defense = {atk: 1.0 for atk in TYPES}
    for ptype in pokemon_types:
        rel = _relations(ptype)
        for atk in TYPES:
            if atk in rel["no_from"]:
                defense[atk] *= 0.0
            elif atk in rel["double_from"]:
                defense[atk] *= 2.0
            elif atk in rel["half_from"]:
                defense[atk] *= 0.5

    # offense: for each of pokemon's types (move type), multiplier vs each single-type defender
    offense = {}
    for mtype in pokemon_types:
        rel = _relations(mtype)
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
