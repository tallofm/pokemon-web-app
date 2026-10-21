"""
special_pokemon.py - Special Pokémon Category Classifications & Filters.
Accurately categorizes Legendaries, Sub-Legendaries, Mythicals, Ultra Beasts,
Paradox Pokémon, Pseudo-Legendaries, Megas, Gigantamax, Regional Forms, and Special Forms.
"""

from typing import List, Dict, Optional, Set

RESTRICTED_LEGENDS: Set[str] = {
    "mewtwo", "lugia", "ho-oh", "kyogre", "groudon", "rayquaza",
    "dialga", "palkia", "giratina", "reshiram", "zekrom", "kyurem",
    "xerneas", "yveltal", "zygarde", "cosmog", "cosmoem", "solgaleo",
    "lunala", "necrozma", "zacian", "zamazenta", "eternatus",
    "calyrex", "koraidon", "miraidon", "terapagos"
}

SUB_LEGENDS: Set[str] = {
    "articuno", "zapdos", "moltres", "raikou", "entei", "suicune",
    "regirock", "regice", "registeel", "latias", "latios", "uxie",
    "mesprit", "azelf", "heatran", "regigigas", "cresselia",
    "cobalion", "terrakion", "virizion", "tornadus", "thundurus",
    "landorus", "enamorus", "type-null", "silvally", "tapu-koko",
    "tapu-lele", "tapu-bulu", "tapu-fini", "kubfu", "urshifu",
    "regieleki", "regidrago", "glastrier", "spectrier",
    "wo-chien", "chien-pao", "ting-lu", "chi-yu", "okidogi",
    "munkidori", "fezandipiti", "ogerpon", "ursaluna-bloodmoon"
}

MYTHICALS: Set[str] = {
    "mew", "celebi", "jirachi", "deoxys", "phione", "manaphy",
    "darkrai", "shaymin", "arceus", "victini", "keldeo", "meloetta",
    "genesect", "diancie", "hoopa", "volcanion", "magearna",
    "marshadow", "zeraora", "meltan", "melmetal", "zarude", "pecharunt"
}

ULTRA_BEASTS: Set[str] = {
    "nihilego", "buzzwole", "pheromosa", "xurkitree", "celesteela",
    "kartana", "guzzlord", "poipole", "naganadel", "stakataka", "blacephalon"
}

PARADOX: Set[str] = {
    "great-tusk", "scream-tail", "brute-bonnet", "flutter-mane",
    "slither-wing", "sandy-shocks", "roaring-moon", "iron-treads",
    "iron-bundle", "iron-hands", "iron-jugulis", "iron-moth",
    "iron-thorns", "iron-valiant", "walking-wake", "iron-leaves",
    "gouging-fire", "raging-bolt", "iron-boulder", "iron-crown"
}

PSEUDO_LEGENDS: Set[str] = {
    "dratini", "dragonair", "dragonite",
    "larvitar", "pupitar", "tyranitar",
    "bagon", "shelgon", "salamence",
    "beldum", "metang", "metagross",
    "gible", "gabite", "garchomp",
    "deino", "zweilous", "hydreigon",
    "goomy", "sliggoo", "goodra",
    "jangmo-o", "hakamo-o", "kommo-o",
    "dreepy", "drakloak", "dragapult",
    "frigibax", "arctibax", "baxcalibur"
}

SPECIAL_CATEGORIES: List[Dict[str, str]] = [
    {"id": "all_special", "label": "All Special", "icon": "⭐", "desc": "All special forms & legendaries"},
    {"id": "legendary", "label": "Legendary", "icon": "👑", "desc": "Major / Box Legendary Pokémon"},
    {"id": "sub_legendary", "label": "Sub-Legendary", "icon": "⚡", "desc": "Sub-Legendaries & Guardian Deities"},
    {"id": "mythical", "label": "Mythical", "icon": "✨", "desc": "Mythical & Event Pokémon"},
    {"id": "ultra_beast", "label": "Ultra Beasts", "icon": "🌌", "desc": "Extradimensional Ultra Beasts"},
    {"id": "paradox", "label": "Paradox", "icon": "⏳", "desc": "Ancient & Future Paradox Pokémon"},
    {"id": "pseudo_legendary", "label": "Pseudo-Legendary", "icon": "🐉", "desc": "600 BST Pseudo-Legendary Families"},
    {"id": "mega", "label": "Mega Evolution", "icon": "🧬", "desc": "Mega Evolutions & Primal Reversions"},
    {"id": "gmax", "label": "Gigantamax", "icon": "💥", "desc": "Gigantamax Forms"},
    {"id": "regional", "label": "Regional Forms", "icon": "🗺️", "desc": "Alolan, Galarian, Hisuian, & Paldean"},
    {"id": "special_forms", "label": "Special Forms", "icon": "🎭", "desc": "Cap, Totem, Origin, and unique battle forms"},
]


def get_special_category(name: str) -> Optional[str]:
    """Classifies a Pokémon name into its primary special category, or None if standard."""
    clean = str(name or "").lower().strip()
    base = clean.split("-")[0]

    # 1. Megas & Primals
    if "-mega" in clean or "-primal" in clean:
        return "mega"

    # 2. Gigantamax
    if "-gmax" in clean:
        return "gmax"

    # 3. Regional Forms
    if any(rf in clean for rf in ("-alola", "-galar", "-hisui", "-paldea")):
        return "regional"

    # 4. Ultra Beasts
    if clean in ULTRA_BEASTS or base in ULTRA_BEASTS:
        return "ultra_beast"

    # 5. Paradox Pokémon
    if clean in PARADOX or base in PARADOX:
        return "paradox"

    # 6. Mythicals
    if clean in MYTHICALS or base in MYTHICALS:
        return "mythical"

    # 7. Restricted / Box Legends
    if clean in RESTRICTED_LEGENDS or base in RESTRICTED_LEGENDS:
        return "legendary"

    # 8. Sub-Legendaries
    if clean in SUB_LEGENDS or base in SUB_LEGENDS:
        return "sub_legendary"

    # 9. Pseudo-Legendaries
    if clean in PSEUDO_LEGENDS or base in PSEUDO_LEGENDS:
        return "pseudo_legendary"

    # 10. Special Forms
    special_suffixes = (
        "-cap", "-totem", "-ash", "-cosplay", "-libre", "-pop-star",
        "-phd", "-belle", "-rock-star", "-starter", "-therian", "-origin",
        "-crowned", "-eternamax", "-dada", "-hero", "-roaming", "-blade",
        "-school", "-zen", "-resolute", "-pirouette", "-sky", "-stellar"
    )
    if any(sf in clean for sf in special_suffixes):
        return "special_forms"

    return None


def matches_special_filter(name: str, filter_id: str) -> bool:
    """Returns True if the given Pokémon matches the requested special filter."""
    if not filter_id:
        return True
    
    clean_filter = filter_id.lower().strip()
    cat = get_special_category(name)

    if clean_filter in ("all", "all_special"):
        return cat is not None
    
    return cat == clean_filter

