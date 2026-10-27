# app.py
"""
Pokémon Championship Web Application & Showdown Battle Engine
=============================================================

A high-performance, tournament-compliant Flask application providing:
1. Pokédex Catalog: 1,025+ species, multi-mode search (regex, wildcard, substring), dynamic sorting.
2. MoveDex, AbilityDex, ItemDex: Exhaustive competitive entity explorers with PokéAPI and offline caching.
3. Type Effectiveness Tool: Multi-type offensive coverage and 8x to 0x defensive vulnerability analyzer.
4. Championship Teambuilder: 6-slot roster builder, Serebii Champions format validation, AI coach telemetry.
5. Showdown Battle Simulator: 4,000+ line Gen 9 competitive engine (Omni Ring, Mega Evolution, G-Max, Tera,
   consecutive Protect decay, Struggle fallback, recoil capping, and Minimax AI lookahead).
"""

import random
import os
import re
from flask import Flask, render_template, request, redirect, url_for, jsonify
from urllib.parse import urlencode

from utils import cache
from utils.naming import humanize_name
from utils.favorites import load_favorites, toggle_favorite, is_favorite
from utils.special_pokemon import SPECIAL_CATEGORIES, matches_special_filter
from utils.pokeapi import (
    get_pokemon,
    get_species,
    get_form_variants,
    get_all_form_flavor_texts,
    get_all_species_flavor_texts,
    get_ability,
    get_ability_effect,
    get_ability_flavor_text,
    get_move_short_effect,
    get_item,
    get_item_short_effect,
    get_item_flavor_text,
)
from utils.cache import (
    get_all_pokemon_names_cached,
    get_all_types_cached,
    refresh_lists,
    get_pokemon_cached,
    get_species_cached,
    get_evolution_chain_cached,
    get_type_cached,
    get_generation_cached,
    get_form_cached,
    get_ability_cached,
    get_all_ability_names_cached,
    refresh_cache,
    backup_cache,
    recover_cache,
    backup_extra_cache,
    refresh_extra_cache,
    recover_extra_cache,
    get_move_cached,
    get_all_move_names_cached,
    backup_moves_cache,
    refresh_moves_cache,
    recover_moves_cache,
    get_item_cached,
    get_all_item_names_cached,
    backup_abilities_cache,
    refresh_abilities_cache,
    recover_abilities_cache,
    backup_items_cache,
    refresh_items_cache,
    recover_items_cache,
    get_cache_stats,
)
from utils.type_effectiveness import (
    build_effectiveness,
    calc_defense_buckets,
    calc_offense_buckets,
    calc_offense_coverage_buckets,
    get_type_matrix,
    get_pokemon_with_types,
)

app = Flask(__name__)

# --------------------------------------------------------------------------- #
# Helpers & Filters
# --------------------------------------------------------------------------- #

STAT_KEYS = [
    "hp", "attack", "defense", "special-attack", "special-defense", "speed",
    "bst", "height", "weight"
]

LABEL_OVERRIDES = {
    "hp": "HP",
    "attack": "Atk",
    "defense": "Def",
    "special-attack": "SpA",
    "special_attack": "SpA",
    "special attack": "SpA",
    "sp. atk": "SpA",
    "sp atk": "SpA",
    "spa": "SpA",
    "special-defense": "SpD",
    "special_defense": "SpD",
    "special defense": "SpD",
    "sp. def": "SpD",
    "sp def": "SpD",
    "spd": "SpD",
    "speed": "Spe",
    "spe": "Spe",
    "bst": "BST"
}


def labelize(s: str) -> str:
    """Format technical identifier strings into user-friendly title casing."""
    if not s:
        return ""
    clean = str(s).strip()
    return LABEL_OVERRIDES.get(clean.lower(), humanize_name(clean))


app.jinja_env.filters["labelize"] = labelize
app.jinja_env.filters["humanize"] = humanize_name
STAT_LABELS = {k: labelize(k) for k in STAT_KEYS}
ALL_GENS = list(range(1, 11))

GEN_LABELS = {
    1: "Gen 1 (Kanto)",
    2: "Gen 2 (Johto)",
    3: "Gen 3 (Hoenn)",
    4: "Gen 4 (Sinnoh)",
    5: "Gen 5 (Unova)",
    6: "Gen 6 (Kalos)",
    7: "Gen 7 (Alola)",
    8: "Gen 8 (Galar)",
    9: "Gen 9 (Paldea)",
    10: "Gen 10",
}


def best_sprite(p: dict) -> str:
    """Return the best available official artwork or sprite URL for a Pokémon."""
    sprites = (p or {}).get("sprites", {})
    other = sprites.get("other", {})
    return (
        other.get("official-artwork", {}).get("front_default")
        or sprites.get("front_default")
        or other.get("dream_world", {}).get("front_default")
        or other.get("home", {}).get("front_default")
        or url_for("static", filename="img/placeholder.png")
    )


def best_shiny_sprite(p: dict) -> str:
    """Return the best available shiny artwork or sprite URL for a Pokémon."""
    sprites = (p or {}).get("sprites", {})
    other = sprites.get("other", {})
    return (
        other.get("official-artwork", {}).get("front_shiny")
        or sprites.get("front_shiny")
        or other.get("home", {}).get("front_shiny")
        or other.get("official-artwork", {}).get("front_default")
        or sprites.get("front_default")
        or url_for("static", filename="img/placeholder.png")
    )


@app.template_global()
def pokedex_url(**kwargs):
    """Builds clean URL for pokedex filtering preserving other active parameters."""
    params = dict(request.args)
    for k, v in kwargs.items():
        if v is None or v == "":
            params.pop(k, None)
        else:
            params[k] = str(v)
    if "offset" not in kwargs:
        params.pop("offset", None)
    qs = urlencode(params)
    return "/pokedex" + (f"?{qs}" if qs else "")


def page_bounds(offset: int, limit: int, total: int) -> tuple[int, int]:
    """Calculate 1-indexed start and end bounds for pagination display."""
    if total <= 0:
        return 0, 0
    return offset + 1, min(offset + limit, total)


def filter_by_search(names: list[str], search_query: str) -> list[str]:
    """Filter names supporting regex ('re:<pattern>'), wildcards ('*'), or substring matching."""
    if not search_query:
        return names
    query = search_query.strip()
    query_lc = query.lower()
    try:
        if query.startswith("re:"):
            regex = re.compile(query[3:], re.I)
            return [n for n in names if regex.search(n)]
        if "*" in query_lc:
            pattern = "^" + re.escape(query_lc).replace(r"\*", ".*") + "$"
            regex = re.compile(pattern)
            return [n for n in names if regex.search(n.lower())]
        return [n for n in names if query_lc in n.lower()]
    except re.error:
        return [n for n in names if query_lc in n.lower()]


def extract_generation_varieties(gen_id: int | str) -> list[str]:
    """Extract all Pokémon variety names belonging to a generation."""
    gd = get_generation_cached(gen_id)
    if not gd:
        return []
    varieties = []
    for s in gd.get("pokemon_species", []):
        sp = get_species_cached(s["name"])
        if sp and sp.get("varieties"):
            varieties.extend(
                v["pokemon"]["name"]
                for v in sp["varieties"]
                if v.get("pokemon", {}).get("name")
            )
        else:
            varieties.append(s["name"])
    return list(dict.fromkeys(varieties))


def display_metric(key: str, val) -> str | None:
    """Format numerical stat values with appropriate units for display."""
    if val is None or key not in STAT_LABELS:
        return None
    if key == "height":
        return f"{val} dm"
    if key == "weight":
        return f"{val} hg"
    return str(val)


def get_pokemon_sort_metric(name: str, sort_by: str):
    """Retrieve the sorting metric for a given Pokémon name."""
    p = get_pokemon_cached(name, get_pokemon) or {}
    if sort_by == "id":
        return p.get("id", 0)
    if sort_by in ("height", "weight"):
        return p.get(sort_by, 0) or 0
    stats = {s["stat"]["name"]: s["base_stat"] for s in p.get("stats", [])}
    if sort_by == "bst":
        return sum(stats.values()) if stats else 0
    return stats.get(sort_by, 0)


def build_pokemon_card(name: str, sort_by: str = "id") -> dict | None:
    """Build standardized display card dictionary for a Pokémon."""
    p = get_pokemon_cached(name, get_pokemon)
    if not p:
        return None

    types = [t["type"]["name"] for t in p.get("types", [])]
    stats = {s["stat"]["name"]: s["base_stat"] for s in p.get("stats", [])}
    bst = sum(stats.values()) if stats else 0

    metric_map = {
        "id": p.get("id"),
        "name": p.get("name", ""),
        "hp": stats.get("hp", 0),
        "attack": stats.get("attack", 0),
        "defense": stats.get("defense", 0),
        "special-attack": stats.get("special-attack", 0),
        "special-defense": stats.get("special-defense", 0),
        "speed": stats.get("speed", 0),
        "bst": bst,
        "height": p.get("height") or 0,
        "weight": p.get("weight") or 0,
    }
    sort_value = metric_map.get(sort_by, metric_map["id"])

    return {
        "name": p.get("name", "").capitalize(),
        "id": p.get("id"),
        "sprite": best_sprite(p),
        "sprite_shiny": best_shiny_sprite(p),
        "types": types,
        "sort_value": sort_value,
        "sort_display": display_metric(sort_by, sort_value),
    }


def sort_and_paginate_names(
    names: list[str],
    sort_by: str = "id",
    reverse: bool = False,
    offset: int = 0,
    limit: int = 12
) -> list[str]:
    """Sort a list of Pokémon names globally by requested metric, then paginate."""
    if sort_by == "name":
        sorted_names = sorted(names, key=lambda n: n.capitalize(), reverse=reverse)
    else:
        metrics = {n: get_pokemon_sort_metric(n, sort_by) for n in names}
        sorted_names = sorted(names, key=lambda n: metrics[n], reverse=reverse)
    return sorted_names[offset:offset + limit]


# --------------------------------------------------------------------------- #
# Cache & Logging Administration Routes
# --------------------------------------------------------------------------- #

def _admin_redirect(msg: str | None = None):
    """Safely redirects the user back to the referring page with an optional status message query."""
    target = request.referrer or url_for("home")
    if msg:
        sep = "&" if "?" in target else "?"
        return redirect(f"{target}{sep}message={msg}")
    return redirect(target)


@app.route("/toggle_logging")
def toggle_logging():
    """Toggles verbose disk-cache operational logging in data/cache_log.txt."""
    cache.ENABLE_VERBOSE_LOGGING = not cache.ENABLE_VERBOSE_LOGGING
    state = "enabled" if cache.ENABLE_VERBOSE_LOGGING else "disabled"
    return _admin_redirect(f"Verbose logging {state}")


@app.route("/backup_cache")
def backup_cache_route():
    """Creates a timestamped snapshot backup of pokemon_cache.json."""
    ok = backup_cache()
    return _admin_redirect("Backed up Pokémon cache" if ok else "Backup failed")


@app.route("/refresh_cache")
def refresh_cache_route():
    """Flushes pokemon_cache in memory and on disk."""
    refresh_cache()
    return _admin_redirect("Pokémon cache refreshed")


@app.route("/recover_cache")
def recover_cache_route():
    """Recovers the most recent valid backup for pokemon_cache.json."""
    ok = recover_cache()
    return _admin_redirect("Recovered Pokémon cache" if ok else "Recover failed")


@app.route("/backup_extra_cache")
def backup_extra_cache_route():
    """Creates a timestamped snapshot backup of extra_cache.json."""
    ok = backup_extra_cache()
    return _admin_redirect("Backed up extra cache" if ok else "Backup failed")


@app.route("/refresh_extra_cache")
def refresh_extra_cache_route():
    """Flushes extra_cache in memory and on disk."""
    refresh_extra_cache()
    return _admin_redirect("Extra cache refreshed")


@app.route("/recover_extra_cache")
def recover_extra_cache_route():
    """Recovers the most recent valid backup for extra_cache.json."""
    ok = recover_extra_cache()
    return _admin_redirect("Recovered extra cache" if ok else "Recover failed")


@app.route("/backup_moves_cache")
def backup_moves_cache_route():
    """Creates a timestamped snapshot backup of moves_cache.json."""
    ok = backup_moves_cache()
    return _admin_redirect("Backed up moves cache" if ok else "Backup failed")


@app.route("/refresh_moves_cache")
def refresh_moves_cache_route():
    """Flushes moves_cache in memory and on disk."""
    refresh_moves_cache()
    return _admin_redirect("Moves cache refreshed")


@app.route("/recover_moves_cache")
def recover_moves_cache_route():
    """Recovers the most recent valid backup for moves_cache.json."""
    ok = recover_moves_cache()
    return _admin_redirect("Recovered moves cache" if ok else "Recover failed")


@app.route("/backup_abilities_cache")
def backup_abilities_cache_route():
    """Creates a timestamped snapshot backup of abilities_cache.json."""
    ok = backup_abilities_cache()
    return _admin_redirect("Backed up abilities cache" if ok else "Backup failed")


@app.route("/refresh_abilities_cache")
def refresh_abilities_cache_route():
    """Flushes abilities_cache in memory and on disk."""
    refresh_abilities_cache()
    return _admin_redirect("Abilities cache refreshed")


@app.route("/recover_abilities_cache")
def recover_abilities_cache_route():
    """Recovers the most recent valid backup for abilities_cache.json."""
    ok = recover_abilities_cache()
    return _admin_redirect("Recovered abilities cache" if ok else "Recover failed")


@app.route("/backup_items_cache")
def backup_items_cache_route():
    """Creates a timestamped snapshot backup of items_cache.json."""
    ok = backup_items_cache()
    return _admin_redirect("Backed up items cache" if ok else "Backup failed")


@app.route("/refresh_items_cache")
def refresh_items_cache_route():
    """Flushes items_cache in memory and on disk."""
    refresh_items_cache()
    return _admin_redirect("Items cache refreshed")


@app.route("/recover_items_cache")
def recover_items_cache_route():
    """Recovers the most recent valid backup for items_cache.json."""
    ok = recover_items_cache()
    return _admin_redirect("Recovered items cache" if ok else "Recover failed")


@app.route("/refresh_lists")
def refresh_lists_route():
    """Refreshes species names, type lists, and generational variety indexes."""
    refresh_lists()
    get_all_pokemon_names_cached()
    get_all_types_cached(exclude_special=False)
    get_all_types_cached(exclude_special=True)
    return _admin_redirect("Lists refreshed")


# --------------------------------------------------------------------------- #
# Application Pages & Views
# --------------------------------------------------------------------------- #

@app.route("/")
def home():
    """Home landing page & central developer diagnostics hub."""
    stats = get_cache_stats()

    # Read last 40 lines of cache_log.txt if present
    log_lines = []
    log_path = os.path.join(cache.DATA_DIR, "cache_log.txt")
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                log_lines = lines[-40:]
                log_lines.reverse()
        except Exception:
            pass

    return render_template(
        "home.html",
        cache_stats=stats,
        logging_enabled=cache.ENABLE_VERBOSE_LOGGING,
        log_lines=log_lines,
        sample_teams_count=len(get_sample_teams()),
        competitive_items_count=len(get_competitive_items()),
        message=request.args.get("message"),
    )


@app.route("/random")
def global_random():
    """Context-aware randomizer routing across Pokédex, Movedex, Abilitydex, Itemdex, Type Tool, and Teambuilder."""
    context = request.args.get("context", "").strip().lower()
    ref = request.referrer or ""

    if not context:
        if "/movedex" in ref or "/move/" in ref:
            context = "moves"
        elif "/abilitydex" in ref or "/ability/" in ref:
            context = "abilities"
        elif "/itemdex" in ref or "/item/" in ref:
            context = "items"
        elif "/type_tool" in ref:
            context = "type_tool"
        elif "/teambuilder" in ref:
            context = "teambuilder"
        elif "/simulator" in ref:
            context = "simulator"
        elif "/pokedex" in ref or "/pokemon/" in ref:
            context = "pokemon"
        elif ref.endswith("/") or "home" in ref:
            context = "home"
        else:
            context = "home"

    if context in ("moves", "movedex", "move"):
        if "/move/" in ref and not ref.endswith("/movedex"):
            all_m = list(get_all_move_names_cached())
            if all_m:
                return redirect(url_for("move_detail", name=random.choice(all_m)))
        return redirect(url_for("movedex", random="true"))

    elif context in ("abilities", "abilitydex", "ability"):
        if "/ability/" in ref and not ref.endswith("/abilitydex"):
            all_a = list(get_all_ability_names_cached())
            if all_a:
                return redirect(url_for("ability_detail", name=random.choice(all_a)))
        return redirect(url_for("abilitydex", random="true"))

    elif context in ("items", "itemdex", "item"):
        if "/item/" in ref and not ref.endswith("/itemdex"):
            all_i = list(get_all_item_names_cached())
            if all_i:
                return redirect(url_for("item_detail", name=random.choice(all_i)))
        return redirect(url_for("itemdex", random="true"))

    elif context in ("type_tool", "typetool", "type"):
        return redirect(url_for("type_tool", random="true"))

    elif context in ("teambuilder", "teams"):
        return redirect(url_for("teambuilder", random="true"))

    elif context in ("simulator", "battle"):
        return redirect(url_for("battle_simulator", random="true"))

    elif context in ("pokemon", "pokedex"):
        if "/pokemon/" in ref and not ref.endswith("/pokedex"):
            all_p = list(get_all_pokemon_names_cached())
            if all_p:
                return redirect(url_for("pokemon_detail", name=random.choice(all_p)))
        return redirect(url_for("pokedex", random="true"))

    elif context == "home":
        targets = [
            url_for("pokedex", random="true"),
            url_for("movedex", random="true"),
            url_for("abilitydex", random="true"),
            url_for("itemdex", random="true"),
            url_for("type_tool", random="true"),
            url_for("teambuilder", random="true"),
            url_for("battle_simulator", random="true"),
        ]
        return redirect(random.choice(targets))

    return redirect(url_for("pokedex", random="true"))


@app.route("/pokedex")
def pokedex():
    """Main Pokédex catalog controller.
    
    Supports:
    - Multi-mode search: Substring, wildcards (*saur, char*), and regex (re:^pik.*)
    - Filtering: Elemental Type (18 types), Debut Generation (1-9), Special (Legendary, Paradox, Mega, etc.)
    - Favorites filtering backed by atomic disk persistence
    - Dynamic multi-column sorting: ID, Name, BST, individual Base Stats, Height, Weight
    - Shiny mode toggle and responsive pagination
    """
    limit = int(request.args.get("limit") or 12)
    offset = int(request.args.get("offset") or 0)
    sort_by = request.args.get("sort", "id")
    reverse_sort = request.args.get("reverse") == "true"

    type_filter = request.args.get("type")
    generation = request.args.get("generation")
    special_filter = request.args.get("special")
    favorites_only = request.args.get("favorites") == "true"
    shiny_mode = request.args.get("shiny") == "true"
    selected_name = request.args.get("pokemon")
    search_raw = request.args.get("search", "")
    randomize = request.args.get("random") == "true"

    all_pokemon_names = get_all_pokemon_names_cached()
    all_types = get_all_types_cached(exclude_special=False)
    species_list = list(all_pokemon_names)

    # 1. Favorites Filter
    fav_set = load_favorites()
    if favorites_only:
        species_list = [n for n in species_list if n.lower() in fav_set]

    # 2. Special Category Filter
    if special_filter:
        species_list = [n for n in species_list if matches_special_filter(n, special_filter)]

    # 3. Type Filter
    if type_filter:
        td = get_type_cached(type_filter)
        if td and "pokemon" in td:
            type_names = {e["pokemon"]["name"] for e in td["pokemon"]}
            species_list = [n for n in species_list if n in type_names]

    # 4. Generation Filter
    if generation:
        gen_varieties = set(extract_generation_varieties(generation))
        species_list = [n for n in species_list if n in gen_varieties]

    # 5. Search Filter
    if search_raw:
        species_list = filter_by_search(species_list, search_raw)

    total_matches = len(species_list)

    # 6. Selection, Randomization, or Global Sorting & Pagination
    if selected_name:
        page_names = [selected_name]
    elif randomize:
        page_names = random.sample(species_list, min(limit, total_matches))
    else:
        page_names = sort_and_paginate_names(
            species_list, sort_by=sort_by, reverse=reverse_sort, offset=offset, limit=limit
        )

    pokemon_data = [card for name in page_names if (card := build_pokemon_card(name, sort_by))]
    start_idx, end_idx = page_bounds(offset, limit, total_matches)

    current_special_obj = next((sc for sc in SPECIAL_CATEGORIES if sc["id"] == special_filter), None)
    current_special_label = current_special_obj["label"] if current_special_obj else ""

    return render_template(
        "pokedex.html",
        pokemon_list=pokemon_data,
        all_types=all_types,
        all_gens=ALL_GENS,
        gen_labels=GEN_LABELS,
        all_pokemon_names=all_pokemon_names,
        current_type=type_filter,
        current_sort=sort_by,
        reverse_sort=reverse_sort,
        stat_labels=STAT_LABELS,
        sort_label=STAT_LABELS.get(sort_by),
        offset=offset,
        limit=limit,
        search=search_raw.lower(),
        start_idx=start_idx,
        end_idx=end_idx,
        total_matches=total_matches,
        favorites=fav_set,
        favorites_count=len(fav_set),
        is_favorites_active=favorites_only,
        current_special=special_filter,
        current_special_label=current_special_label,
        all_specials=SPECIAL_CATEGORIES,
        is_shiny=shiny_mode,
        logging_enabled=cache.ENABLE_VERBOSE_LOGGING,
        cache_stats=get_cache_stats(),
    )


@app.route("/api/favorites", methods=["GET"])
def api_get_favorites():
    """Returns the list and count of currently favorited Pokémon species."""
    favs = list(load_favorites())
    return jsonify({"success": True, "favorites": favs, "count": len(favs)})


@app.route("/api/favorites/toggle", methods=["POST"])
def api_toggle_favorite():
    """Toggles favorite status for a given Pokémon species and persists to disk."""
    data = request.get_json() or {}
    name = data.get("name")
    if not name:
        return jsonify({"success": False, "error": "Missing pokemon name"}), 400
    is_fav = toggle_favorite(name)
    favs = list(load_favorites())
    return jsonify({
        "success": True,
        "name": name.lower(),
        "isFavorite": is_fav,
        "favorites": favs,
        "count": len(favs)
    })


@app.route("/pokemon/<name>")
def pokemon_detail(name: str):
    """Detailed view for a single Pokémon."""

    def stat_color(value: int) -> str:
        """Computes dynamic RGB spectrum color for a Pokémon stat value (0-255)."""
        if value <= 128:
            r, g = 255, int((value / 128) * 255)
        else:
            r, g = int((1 - ((value - 128) / 128)) * 255), 255
        return f"rgb({r},{g},0)"

    poke = get_pokemon_cached(name, get_pokemon)
    if not poke:
        return "Pokémon not found", 404

    species_name = (poke.get("species") or {}).get("name") or name
    species = get_species_cached(species_name)

    # 1. Fetch flavor text descriptions (forms first, then species)
    descriptions = []
    is_form_specific = False

    form_raw = get_form_cached(name)
    if form_raw:
        descriptions = get_all_form_flavor_texts(form_raw)
        if descriptions:
            is_form_specific = True

    if not descriptions and species:
        descriptions = get_all_species_flavor_texts(species)

    flavor = descriptions[0]["flavor_text"] if descriptions else "No description available."

    # 2. Forms & Varieties
    form_data = []
    if species:
        for f in (get_form_variants(species) or []):
            pf = get_pokemon_cached(f["name"], get_pokemon)
            if pf:
                form_data.append({
                    "name": f["name"].capitalize(),
                    "sprite": (pf.get("sprites") or {}).get("front_default"),
                    "is_default": f.get("is_default", False),
                })

    # 3. Evolution Chain
    evolution_data = []
    if species:
        for evo_name in (get_evolution_chain_cached(species) or []):
            ed = get_pokemon_cached(evo_name, get_pokemon)
            if ed:
                evolution_data.append({
                    "name": evo_name.capitalize(),
                    "sprite": (ed.get("sprites") or {}).get("front_default"),
                })

    # 4. Base Stats & Type Effectiveness
    stats = {s["stat"]["name"]: s["base_stat"] for s in poke.get("stats", [])}
    stat_colors = {k: stat_color(v) for k, v in stats.items()}
    types_list = [t["type"]["name"] for t in poke.get("types", [])]
    effectiveness = build_effectiveness([t.lower() for t in types_list])

    # 5. Abilities
    ability_list = []
    for ab_entry in poke.get("abilities", []):
        raw_name = ab_entry["ability"]["name"]
        ab_data = get_ability_cached(raw_name)
        effect_desc = get_ability_effect(ab_data) if ab_data else "No description available."
        ability_list.append({
            "name": labelize(raw_name),
            "raw_name": raw_name,
            "is_hidden": ab_entry.get("is_hidden", False),
            "description": effect_desc,
        })

    # 6. Moves Learned
    pokemon_moves = []
    for m_entry in poke.get("moves", []):
        m_raw_name = m_entry["move"]["name"]
        vg_details = m_entry.get("version_group_details", [])
        latest_vg = vg_details[-1] if vg_details else {}
        learn_method = latest_vg.get("move_learn_method", {}).get("name", "unknown")
        level_learned = latest_vg.get("level_learned_at", 0)

        m_data = get_move_cached(m_raw_name)
        pokemon_moves.append({
            "name": labelize(m_raw_name),
            "raw_name": m_raw_name,
            "type": (m_data.get("type") or {}).get("name", "unknown") if m_data else "unknown",
            "damage_class": (m_data.get("damage_class") or {}).get("name", "status") if m_data else "status",
            "power": m_data.get("power") if m_data and m_data.get("power") is not None else "—",
            "accuracy": f"{m_data.get('accuracy')}%" if m_data and m_data.get("accuracy") is not None else "—",
            "method": labelize(learn_method),
            "level": level_learned if learn_method == "level-up" else "—",
        })

    # Order moves: level-up moves by level first, then alphabetically
    pokemon_moves.sort(key=lambda m: (0, int(m["level"])) if m["level"] != "—" else (1, m["name"]))

    sprites = poke.get("sprites") or {}
    artwork = (sprites.get("other") or {}).get("official-artwork") or {}

    p = {
        "name": poke["name"].capitalize(),
        "id": poke["id"],
        "is_default": poke.get("is_default", False),
        "sprite": artwork.get("front_default") or sprites.get("front_default"),
        "shiny_sprite": artwork.get("front_shiny") or sprites.get("front_shiny"),
        "types": types_list,
        "stats": stats,
        "stat_colors": stat_colors,
        "description": flavor,
        "descriptions": descriptions,
        "is_form_specific": is_form_specific,
        "evolutions": evolution_data,
        "forms": form_data,
        "height": poke.get("height"),
        "weight": poke.get("weight"),
        "base_experience": poke.get("base_experience"),
        "abilities": ability_list,
        "egg_groups": [g["name"] for g in species.get("egg_groups", [])] if species else [],
        "effectiveness": effectiveness,
        "all_types": list(effectiveness["defense"].keys()),
        "moves": pokemon_moves,
    }

    return render_template("pokemon_detail.html", p=p)


@app.route("/generation/<int:gen_id>")
def generation_view(gen_id: int):
    """Generation page with search, type filtering, sorting, and pagination."""
    limit = int(request.args.get("limit") or 20)
    offset = int(request.args.get("offset") or 0)
    type_filter = request.args.get("type")
    sort_by = request.args.get("sort", "id")
    reverse_sort = request.args.get("reverse") == "true"
    search_raw = request.args.get("search", "")

    all_types = get_all_types_cached(exclude_special=True)
    species_list = extract_generation_varieties(gen_id)
    if not species_list:
        return f"Generation {gen_id} not found", 404

    if type_filter:
        td = get_type_cached(type_filter)
        if td and "pokemon" in td:
            type_names = {e["pokemon"]["name"] for e in td["pokemon"]}
            species_list = [n for n in species_list if n in type_names]

    if search_raw:
        species_list = filter_by_search(species_list, search_raw)

    total_matches = len(species_list)
    page_names = sort_and_paginate_names(
        species_list, sort_by=sort_by, reverse=reverse_sort, offset=offset, limit=limit
    )

    pokemon_list = [card for name in page_names if (card := build_pokemon_card(name, sort_by))]
    start_idx, end_idx = page_bounds(offset, limit, total_matches)

    return render_template(
        "generation_view.html",
        gen_id=gen_id,
        pokemon_list=pokemon_list,
        all_types=all_types,
        all_gens=ALL_GENS,
        gen_labels=GEN_LABELS,
        current_type=type_filter,
        current_sort=sort_by,
        reverse_sort=reverse_sort,
        stat_labels=STAT_LABELS,
        sort_label=STAT_LABELS.get(sort_by),
        offset=offset,
        limit=limit,
        search=search_raw.lower(),
        start_idx=start_idx,
        end_idx=end_idx,
        total_matches=total_matches,
    )


@app.route("/type/<type_name>")
def type_view(type_name: str):
    """Type page showing damage relations and Pokémon belonging to that type."""
    limit = int(request.args.get("limit") or 20)
    offset = int(request.args.get("offset") or 0)
    sort_by = request.args.get("sort", "id")
    reverse_sort = request.args.get("reverse") == "true"
    generation = request.args.get("generation")
    search_raw = request.args.get("search", "")

    type_data = get_type_cached(type_name)
    if not type_data:
        return f"Type '{type_name}' not found", 404

    allowed_types = get_all_types_cached(exclude_special=True)
    species_list = [e["pokemon"]["name"] for e in type_data.get("pokemon", [])]

    if generation:
        gen_varieties = set(extract_generation_varieties(generation))
        species_list = [n for n in species_list if n in gen_varieties]

    if search_raw:
        species_list = filter_by_search(species_list, search_raw)

    total_matches = len(species_list)
    page_names = sort_and_paginate_names(
        species_list, sort_by=sort_by, reverse=reverse_sort, offset=offset, limit=limit
    )

    pokemon_list = [card for name in page_names if (card := build_pokemon_card(name, sort_by))]
    start_idx, end_idx = page_bounds(offset, limit, total_matches)

    return render_template(
        "type_view.html",
        type_name=type_name,
        pokemon_list=pokemon_list,
        rel=type_data["damage_relations"],
        all_types=allowed_types,
        all_gens=ALL_GENS,
        gen_labels=GEN_LABELS,
        current_sort=sort_by,
        reverse_sort=reverse_sort,
        stat_labels=STAT_LABELS,
        sort_label=STAT_LABELS.get(sort_by),
        offset=offset,
        limit=limit,
        search=search_raw.lower(),
        start_idx=start_idx,
        end_idx=end_idx,
        total_matches=total_matches,
    )


@app.route("/movedex")
def movedex():
    """Move dex browser with filtering, search, and sorting."""
    limit = int(request.args.get("limit") or 25)
    offset = int(request.args.get("offset") or 0)
    type_filter = request.args.get("type")
    damage_class = request.args.get("damage_class")
    sort_by = request.args.get("sort", "name")
    reverse_sort = request.args.get("reverse") == "true"
    search_raw = request.args.get("search", "").strip()
    search_lc = search_raw.lower()

    allowed_types = get_all_types_cached(exclude_special=True)
    all_move_names = get_all_move_names_cached()
    move_list = list(all_move_names)

    if search_lc:
        move_list = [m for m in move_list if search_lc in m.lower()]

    if type_filter or damage_class:
        filtered = []
        for m_name in move_list:
            m = get_move_cached(m_name)
            if not m:
                continue
            if type_filter and (m.get("type") or {}).get("name") != type_filter.lower():
                continue
            if damage_class and (m.get("damage_class") or {}).get("name") != damage_class.lower():
                continue
            filtered.append(m_name)
        move_list = filtered

    total_matches = len(move_list)

    def move_metric(m_name: str):
        """Extracts the numeric or alphabetical metric for move sorting."""
        m = get_move_cached(m_name) or {}
        if sort_by == "power":
            return m.get("power") or 0
        if sort_by == "accuracy":
            return m.get("accuracy") or 0
        if sort_by == "pp":
            return m.get("pp") or 0
        return m.get("name", "")

    randomize = request.args.get("random") == "true"
    if randomize:
        page_moves = random.sample(move_list, min(limit, total_matches))
    elif sort_by == "name":
        sorted_moves = sorted(move_list, key=lambda n: n.capitalize(), reverse=reverse_sort)
        page_moves = sorted_moves[offset:offset + limit]
    else:
        metrics = {n: move_metric(n) for n in move_list}
        sorted_moves = sorted(move_list, key=lambda n: metrics[n], reverse=reverse_sort)
        page_moves = sorted_moves[offset:offset + limit]

    move_data = []
    for m_name in page_moves:
        m = get_move_cached(m_name)
        if not m:
            continue
        move_data.append({
            "id": m.get("id"),
            "name": labelize(m.get("name")),
            "raw_name": m.get("name"),
            "type": (m.get("type") or {}).get("name", "unknown"),
            "damage_class": (m.get("damage_class") or {}).get("name", "status"),
            "power": m.get("power") if m.get("power") is not None else "—",
            "accuracy": f"{m.get('accuracy')}%" if m.get("accuracy") is not None else "—",
            "pp": m.get("pp") or "—",
            "effect": get_move_short_effect(m),
        })

    start_idx, end_idx = page_bounds(offset, limit, total_matches)

    return render_template(
        "movedex.html",
        moves=move_data,
        all_types=allowed_types,
        damage_classes=["physical", "special", "status"],
        current_type=type_filter,
        current_class=damage_class,
        current_sort=sort_by,
        reverse_sort=reverse_sort,
        search=search_lc,
        offset=offset,
        limit=limit,
        start_idx=start_idx,
        end_idx=end_idx,
        total_matches=total_matches,
    )


@app.route("/move/<move_name>")
def move_detail(move_name: str):
    """Detailed view for an individual move."""
    move = get_move_cached(move_name)
    if not move:
        return f"Move '{move_name}' not found", 404

    effect = get_move_short_effect(move)
    flavor_entries = [
        e.get("flavor_text", "").replace("\n", " ").replace("\f", " ")
        for e in move.get("flavor_text_entries", [])
        if e.get("language", {}).get("name") == "en"
    ]
    flavor = flavor_entries[0] if flavor_entries else "No description available."

    learned_names = [p["name"] for p in move.get("learned_by_pokemon", [])]
    pokemon_cards = []
    for p_name in learned_names:
        p_data = get_pokemon_cached(p_name, get_pokemon)
        if not p_data:
            continue
        pokemon_cards.append({
            "name": p_data.get("name", "").capitalize(),
            "id": p_data.get("id"),
            "types": [t["type"]["name"] for t in p_data.get("types", [])],
            "sprite": best_sprite(p_data),
        })

    m_data = {
        "id": move.get("id"),
        "name": labelize(move.get("name")),
        "raw_name": move.get("name"),
        "type": (move.get("type") or {}).get("name", "unknown"),
        "damage_class": (move.get("damage_class") or {}).get("name", "status"),
        "power": move.get("power") if move.get("power") is not None else "—",
        "accuracy": f"{move.get('accuracy')}%" if move.get("accuracy") is not None else "—",
        "pp": move.get("pp") or "—",
        "priority": move.get("priority", 0),
        "effect": effect,
        "flavor": flavor,
        "learned_by": pokemon_cards,
    }

    return render_template("move_detail.html", m=m_data)


@app.route("/abilitydex")
def abilitydex():
    """Ability dex browser with filtering, search, and sorting."""
    limit = int(request.args.get("limit") or 24)
    offset = int(request.args.get("offset") or 0)
    generation_filter = request.args.get("generation")
    sort_by = request.args.get("sort", "name")
    reverse_sort = request.args.get("reverse") == "true"
    search_raw = request.args.get("search", "").strip()
    search_lc = search_raw.lower()

    all_ability_names = get_all_ability_names_cached()
    ability_list = list(all_ability_names)

    if search_lc:
        ability_list = [a for a in ability_list if search_lc in a.lower()]

    if generation_filter:
        filtered = []
        for a_name in ability_list:
            ab = get_ability_cached(a_name)
            if not ab:
                continue
            gen_url = (ab.get("generation") or {}).get("url", "")
            gen_num = gen_url.strip("/").split("/")[-1] if gen_url else ""
            if gen_num == str(generation_filter):
                filtered.append(a_name)
        ability_list = filtered

    total_matches = len(ability_list)

    def ability_metric(a_name: str):
        """Extracts the numeric or alphabetical metric for ability sorting."""
        ab = get_ability_cached(a_name) or {}
        if sort_by == "id":
            return ab.get("id") or 99999
        if sort_by == "pokemon_count":
            return len(ab.get("pokemon", []))
        return a_name.capitalize()

    randomize = request.args.get("random") == "true"
    if randomize:
        page_abilities = random.sample(ability_list, min(limit, total_matches))
    elif sort_by == "name":
        sorted_abilities = sorted(ability_list, key=lambda n: n.capitalize(), reverse=reverse_sort)
        page_abilities = sorted_abilities[offset:offset + limit]
    else:
        metrics = {n: ability_metric(n) for n in ability_list}
        sorted_abilities = sorted(ability_list, key=lambda n: metrics[n], reverse=reverse_sort)
        page_abilities = sorted_abilities[offset:offset + limit]

    ability_data = []
    for a_name in page_abilities:
        ab = get_ability_cached(a_name)
        if ab:
            gen_name = (ab.get("generation") or {}).get("name", "")
            gen_label = gen_name.replace("generation-", "Gen ").upper() if gen_name else "—"
            pokemon_cnt = len(ab.get("pokemon", []))
            effect_val = get_ability_effect(ab)
            ab_id = ab.get("id")
        else:
            gen_label = "—"
            pokemon_cnt = "—"
            effect_val = "Select ability to view details."
            ab_id = None

        ability_data.append({
            "id": ab_id,
            "name": labelize(a_name),
            "raw_name": a_name,
            "generation": gen_label,
            "pokemon_count": pokemon_cnt,
            "effect": effect_val,
        })

    start_idx, end_idx = page_bounds(offset, limit, total_matches)

    return render_template(
        "abilitydex.html",
        abilities=ability_data,
        all_gens=list(range(3, 10)),
        gen_labels=GEN_LABELS,
        current_gen=generation_filter,
        current_sort=sort_by,
        reverse_sort=reverse_sort,
        search=search_lc,
        offset=offset,
        limit=limit,
        start_idx=start_idx,
        end_idx=end_idx,
        total_matches=total_matches,
    )


@app.route("/ability/<ability_name>")
def ability_detail(ability_name: str):
    """Detailed view for an individual ability."""
    ability = get_ability_cached(ability_name)
    if not ability:
        return f"Ability '{ability_name}' not found", 404

    effect = get_ability_effect(ability)
    flavor = get_ability_flavor_text(ability)
    gen_name = (ability.get("generation") or {}).get("name", "")
    gen_label = gen_name.replace("generation-", "Generation ").title() if gen_name else "Unknown"

    pokemon_cards = []
    for p_entry in ability.get("pokemon", []):
        p_info = p_entry.get("pokemon", {})
        p_name = p_info.get("name")
        if not p_name:
            continue
        p_data = get_pokemon_cached(p_name, get_pokemon)
        if not p_data:
            continue
        pokemon_cards.append({
            "name": p_data.get("name", "").capitalize(),
            "raw_name": p_data.get("name"),
            "id": p_data.get("id"),
            "types": [t["type"]["name"] for t in p_data.get("types", [])],
            "sprite": best_sprite(p_data),
            "is_hidden": p_entry.get("is_hidden", False),
            "slot": p_entry.get("slot", 1),
        })

    pokemon_cards.sort(key=lambda x: x["id"] or 99999)

    ab_data = {
        "id": ability.get("id"),
        "name": labelize(ability.get("name")),
        "raw_name": ability.get("name"),
        "generation": gen_label,
        "is_main_series": ability.get("is_main_series", True),
        "effect": effect,
        "flavor": flavor,
        "pokemon": pokemon_cards,
    }

    return render_template("ability_detail.html", a=ab_data)


@app.route("/itemdex")
def itemdex():
    """Item dex browser with filtering, search, and sorting."""
    limit = int(request.args.get("limit") or 24)
    offset = int(request.args.get("offset") or 0)
    category_filter = request.args.get("category")
    sort_by = request.args.get("sort", "name")
    reverse_sort = request.args.get("reverse") == "true"
    search_raw = request.args.get("search", "").strip()
    search_lc = search_raw.lower()

    all_item_names = get_all_item_names_cached()
    item_list = list(all_item_names)

    if search_lc:
        item_list = [i for i in item_list if search_lc in i.lower()]

    if category_filter:
        filtered = []
        for i_name in item_list:
            it = get_item_cached(i_name)
            if not it:
                continue
            cat = (it.get("category") or {}).get("name", "")
            if cat == category_filter.lower():
                filtered.append(i_name)
        item_list = filtered

    total_matches = len(item_list)

    def item_metric(i_name: str):
        """Extracts the numeric or alphabetical metric for item sorting."""
        it = get_item_cached(i_name) or {}
        if sort_by == "id":
            return it.get("id") or 99999
        if sort_by == "cost":
            return it.get("cost") or 0
        return i_name.capitalize()

    randomize = request.args.get("random") == "true"
    if randomize:
        page_items = random.sample(item_list, min(limit, total_matches))
    elif sort_by == "name":
        sorted_items = sorted(item_list, key=lambda n: n.capitalize(), reverse=reverse_sort)
        page_items = sorted_items[offset:offset + limit]
    else:
        metrics = {n: item_metric(n) for n in item_list}
        sorted_items = sorted(item_list, key=lambda n: metrics[n], reverse=reverse_sort)
        page_items = sorted_items[offset:offset + limit]

    item_data = []
    for i_name in page_items:
        it = get_item_cached(i_name)
        if it:
            cat_name = (it.get("category") or {}).get("name", "general")
            cat_label = labelize(cat_name)
            sprite = (it.get("sprites") or {}).get("default") or ""
            cost_val = f"₽{it.get('cost'):,}" if it.get("cost") else "—"
            effect_val = get_item_short_effect(it)
            item_id = it.get("id")
        else:
            cat_label = "Item"
            cat_name = "general"
            sprite = ""
            cost_val = "—"
            effect_val = "Select item to view details."
            item_id = None

        item_data.append({
            "id": item_id,
            "name": labelize(i_name),
            "raw_name": i_name,
            "category": cat_label,
            "raw_category": cat_name,
            "cost": cost_val,
            "sprite": sprite,
            "effect": effect_val,
        })

    start_idx, end_idx = page_bounds(offset, limit, total_matches)

    popular_categories = [
        "standard-balls", "special-balls", "healing", "status-cures",
        "held-items", "choice", "berries", "evolution", "mega-stones",
        "stat-boosts", "plates", "key-items", "tera-shards"
    ]

    return render_template(
        "itemdex.html",
        items=item_data,
        categories=popular_categories,
        current_category=category_filter,
        current_sort=sort_by,
        reverse_sort=reverse_sort,
        search=search_lc,
        offset=offset,
        limit=limit,
        start_idx=start_idx,
        end_idx=end_idx,
        total_matches=total_matches,
    )


@app.route("/item/<item_name>")
def item_detail(item_name: str):
    """Detailed view for an individual item."""
    item = get_item_cached(item_name)
    if not item:
        return f"Item '{item_name}' not found", 404

    effect = get_item_short_effect(item)
    flavor = get_item_flavor_text(item)
    cat_name = (item.get("category") or {}).get("name", "general")
    cat_label = labelize(cat_name)

    held_by_cards = []
    for h in item.get("held_by_pokemon", []):
        p_name = h.get("pokemon", {}).get("name")
        if not p_name:
            continue
        p_data = get_pokemon_cached(p_name, get_pokemon)
        if not p_data:
            continue
        rarity = 0
        v_details = h.get("version_details", [])
        if v_details:
            rarity = v_details[-1].get("rarity", 0)
        held_by_cards.append({
            "name": p_data.get("name", "").capitalize(),
            "raw_name": p_data.get("name"),
            "id": p_data.get("id"),
            "types": [t["type"]["name"] for t in p_data.get("types", [])],
            "sprite": best_sprite(p_data),
            "rarity": f"{rarity}%",
        })

    it_data = {
        "id": item.get("id"),
        "name": labelize(item.get("name")),
        "raw_name": item.get("name"),
        "category": cat_label,
        "cost": f"₽{item.get('cost'):,}" if item.get("cost") else "Free / Unsellable",
        "fling_power": item.get("fling_power") or "—",
        "sprite": (item.get("sprites") or {}).get("default") or "",
        "effect": effect,
        "flavor": flavor,
        "attributes": [labelize(a.get("name", "")) for a in item.get("attributes", [])],
        "held_by": held_by_cards,
    }

    return render_template("item_detail.html", it=it_data)


@app.route("/type_tool")
def type_tool():
    """Interactive type calculator for defensive matchups and offensive coverage."""
    allowed_types = get_all_types_cached(exclude_special=True)
    all_pokemon_names = list(get_all_pokemon_names_cached())

    pokemon_param = (request.args.get("pokemon") or "").strip().lower()
    d1 = (request.args.get("d1") or "").lower()
    d2 = (request.args.get("d2") or "").lower()
    d3 = (request.args.get("d3") or "").lower()
    a1 = (request.args.get("a1") or "").lower()
    a2 = (request.args.get("a2") or "").lower()
    a3 = (request.args.get("a3") or "").lower()
    a4 = (request.args.get("a4") or "").lower()

    loaded_pokemon = None
    if pokemon_param and not d1:
        p_loaded = get_pokemon_cached(pokemon_param, get_pokemon)
        if p_loaded:
            loaded_pokemon = p_loaded["name"].capitalize()
            p_types = [t["type"]["name"] for t in p_loaded.get("types", []) if t.get("type", {}).get("name") in allowed_types]
            if len(p_types) >= 1:
                d1 = p_types[0]
            if len(p_types) >= 2:
                d2 = p_types[1]
            if len(p_types) >= 3:
                d3 = p_types[2]

    # Defaults if neither pokemon nor slots were specified
    if not d1 and not d2 and not d3 and not a1 and not a2 and not a3 and not a4:
        d1 = "water"
        a1 = "water"
    elif not d1 and not d2 and not d3:
        d1 = "water"

    if not a1 and not a2 and not a3 and not a4:
        a1 = "water"

    defense_types = [t for t in [d1, d2, d3] if t in allowed_types]
    offense_types = [t for t in [a1, a2, a3, a4] if t in allowed_types]

    defense = calc_defense_buckets(defense_types, allowed_types) if defense_types else None
    offense = calc_offense_buckets(offense_types, allowed_types) if offense_types else None
    coverage_offense = calc_offense_coverage_buckets(offense_types, allowed_types) if offense_types else None
    type_matrix = get_type_matrix(allowed_types)

    matched_cards = []
    if defense_types:
        for name in get_pokemon_with_types(defense_types)[:300]:
            p = get_pokemon_cached(name, get_pokemon)
            if not p:
                continue
            matched_cards.append({
                "id": p.get("id"),
                "name": p["name"].capitalize(),
                "raw_name": p["name"],
                "sprite": best_sprite(p),
                "types": [t["type"]["name"] for t in p.get("types", [])],
            })

    return render_template(
        "type_tool.html",
        all_types=allowed_types,
        all_pokemon_names=all_pokemon_names,
        defense_types=defense_types,
        offense_types=offense_types,
        d1=d1, d2=d2, d3=d3,
        a1=a1, a2=a2, a3=a3, a4=a4,
        defense=defense,
        offense=offense,
        coverage_offense=coverage_offense,
        matched=matched_cards,
        type_matrix=type_matrix,
        loaded_pokemon=loaded_pokemon,
    )


@app.route("/api/pokemon_types/<name>")
def api_pokemon_types(name):
    """Return type array and basic info for a given Pokémon name (for type-tool auto-load)."""
    p = get_pokemon_cached(name.strip().lower(), get_pokemon)
    if not p:
        return jsonify({"error": "Pokemon not found"}), 404
    types = [t["type"]["name"] for t in p.get("types", [])]
    return jsonify({
        "id": p.get("id"),
        "name": p["name"].capitalize(),
        "raw_name": p["name"],
        "sprite": best_sprite(p),
        "types": types,
    })


@app.route("/api/pokemon_by_types")
def api_pokemon_by_types():
    """Return matching Pokémon cards for selected defensive types."""
    types_raw = request.args.get("types", "")
    types = [t.strip().lower() for t in types_raw.split(",") if t.strip()]
    if not types:
        return jsonify({"pokemon": [], "total": 0})

    names = get_pokemon_with_types(types)
    cards = []
    for n in names[:300]:
        p = get_pokemon_cached(n, get_pokemon)
        if not p:
            continue
        cards.append({
            "id": p.get("id"),
            "name": p["name"].capitalize(),
            "raw_name": p["name"],
            "sprite": best_sprite(p),
            "types": [t["type"]["name"] for t in p.get("types", [])],
        })

    return jsonify({"pokemon": cards, "total": len(names)})


# --------------------------------------------------------------------------- #
# Teambuilder & Competitive Championship Routes
# --------------------------------------------------------------------------- #

from utils.teambuilder_storage import (
    get_competitive_items,
    save_competitive_item,
    delete_competitive_item,
    get_sample_teams,
    save_sample_team,
    delete_sample_team,
    get_legal_pokemon_list,
)
from utils.ai_coach import analyze_team_with_coach


@app.route("/teambuilder")
def teambuilder():
    """Championship Pokémon Teambuilder with defensive & offensive synergy analysis."""
    all_pokemon_names = get_all_pokemon_names_cached()
    all_types = get_all_types_cached(exclude_special=False)
    return render_template(
        "teambuilder.html",
        all_pokemon_names=all_pokemon_names,
        all_types=all_types,
    )


@app.route("/api/sample_teams", methods=["GET", "POST"])
def api_sample_teams_route():
    """Get all sample teams or save/update a sample team to disk cache."""
    if request.method == "POST":
        data = request.get_json() or {}
        if not data.get("name") or not data.get("members"):
            return jsonify({"error": "Invalid team data"}), 400
        saved_teams = save_sample_team(data)
        return jsonify({"success": True, "teams": saved_teams})

    return jsonify({"teams": get_sample_teams()})


@app.route("/api/sample_teams/<team_id>", methods=["DELETE"])
def api_delete_sample_team_route(team_id):
    """Delete a sample team from disk cache."""
    saved_teams = delete_sample_team(team_id)
    return jsonify({"success": True, "teams": saved_teams})


@app.route("/api/competitive_items", methods=["GET", "POST"])
def api_competitive_items():
    """Get all competitive items or save/update an item to disk cache."""
    if request.method == "POST":
        data = request.get_json() or {}
        if not data.get("name"):
            return jsonify({"error": "Item name is required"}), 400
        items = save_competitive_item(data)
        return jsonify({"success": True, "items": items})

    return jsonify({"items": get_competitive_items()})


@app.route("/api/competitive_items/<item_name>", methods=["DELETE"])
def api_delete_competitive_item_route(item_name):
    """Delete a competitive item from disk cache."""
    items = delete_competitive_item(item_name)
    return jsonify({"success": True, "items": items})


@app.route("/api/legal_pokemon")
def api_legal_pokemon():
    """Return legal Pokémon list for the specified rule ('champions' vs 'smogon')."""
    rule = request.args.get("rule", "champions").lower()
    from utils.cache import pokemon_cache
    pokemon = get_legal_pokemon_list(
        rule=rule,
        all_names_fn=get_all_pokemon_names_cached,
        poke_cache_fn=lambda: pokemon_cache
    )
    return jsonify({"rule": rule, "count": len(pokemon), "pokemon": pokemon})


@app.route("/api/itemdex_search")
def api_itemdex_search():
    """Search ItemDex cache and return rich item suggestions."""
    q = (request.args.get("q") or "").strip().lower()
    all_names = get_all_item_names_cached()
    matches = [n for n in all_names if q in n.lower()][:40] if q else list(all_names)[:40]
    results = []
    for m in matches:
        it = get_item_cached(m) or {}
        results.append({
            "name": m,
            "displayName": humanize_name(m),
            "sprite": it.get("sprites", {}).get("default") or f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/{m}.png",
            "category": it.get("category", {}).get("name", "item") if isinstance(it.get("category"), dict) else "item",
            "effect": get_item_short_effect(it) or ""
        })
    return jsonify({"query": q, "count": len(results), "items": results})


@app.route("/api/ai_coach_insight", methods=["POST"])
def api_ai_coach_insight():
    """Generate dynamic AI Championship Coach insights for the current team."""
    data = request.get_json() or {}
    team_data = data.get("team") or {}
    user_question = data.get("question") or ""
    api_key = data.get("api_key") or ""

    insight = analyze_team_with_coach(team_data, user_question, api_key)
    return jsonify(insight)


@app.route("/api/pokemon_teambuilder_data/<name>")
def api_pokemon_teambuilder_data(name):
    """Return all necessary data to build a competitive Pokémon profile."""
    name = str(name).strip().lower()
    p = get_pokemon_cached(name, get_pokemon)
    if not p:
        return jsonify({"error": "Pokemon not found"}), 404

    # Extract base stats
    stats = {}
    for s in p.get("stats", []):
        stats[s["stat"]["name"]] = s["base_stat"]

    # Extract abilities
    abilities = []
    for a in p.get("abilities", []):
        ab_name = a["ability"]["name"]
        abilities.append({
            "name": ab_name,
            "display_name": humanize_name(ab_name),
            "is_hidden": a.get("is_hidden", False)
        })

    # Extract moves and enrich with cached move definitions
    from utils.battle_engine import get_move_metadata, EXHAUSTIVE_MOVES_DATA
    moves_list = []
    for m in p.get("moves", []):
        m_name = m["move"]["name"]
        m_meta = get_move_metadata(m_name)
        m_info = cache.moves_cache.get(m_name) or {}

        if m_name in EXHAUSTIVE_MOVES_DATA:
            m_type = m_meta.get("type", "normal")
            m_class = m_meta.get("category", "physical")
            m_power = m_meta.get("power")
            m_accuracy = m_meta.get("accuracy")
            m_pp = m_meta.get("pp")
        else:
            raw_t = m_info.get("type", {}).get("name") if isinstance(m_info.get("type"), dict) else m_info.get("type")
            m_type = raw_t or m_meta.get("type") or "normal"

            raw_c = m_info.get("damage_class", {}).get("name") if isinstance(m_info.get("damage_class"), dict) else m_info.get("damage_class")
            m_class = raw_c or m_meta.get("category") or "physical"

            m_power = m_info.get("power") if m_info.get("power") is not None else m_meta.get("power")
            m_accuracy = m_info.get("accuracy") if m_info.get("accuracy") is not None else m_meta.get("accuracy")
            m_pp = m_info.get("pp") if m_info.get("pp") is not None else m_meta.get("pp")

        moves_list.append({
            "name": m_name,
            "display_name": humanize_name(m_name),
            "type": str(m_type).lower(),
            "power": m_power,
            "accuracy": m_accuracy,
            "damage_class": str(m_class).lower(),
            "pp": m_pp
        })
    moves_list.sort(key=lambda x: x["display_name"])

    return jsonify({
        "id": p.get("id"),
        "name": p.get("name"),
        "display_name": humanize_name(p.get("name")),
        "sprite": best_sprite(p),
        "types": [t["type"]["name"] for t in p.get("types", [])],
        "base_stats": stats,
        "abilities": abilities,
        "moves": moves_list,
    })


# --------------------------------------------------------------------------- #
# Pokémon Battle Simulator & Showdown AI Arena Routes
# --------------------------------------------------------------------------- #

import uuid
import threading
from typing import Any
from utils.battle_engine import BattleSimulator
from utils.battle_ai import choose_ai_action
from utils.battle_knowledge import (
    load_battle_knowledge,
    save_battle_knowledge,
    record_battle_outcome,
    reset_battle_knowledge,
)


class ActiveBattleStore:
    """Thread-safe bounded battle storage with LRU and finished-session eviction to prevent memory leaks."""

    def __init__(self, max_size: int = 100):
        self._battles: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, battle_id: str, default: Any = None) -> Any:
        """Retrieves an active battle instance by session ID."""
        with self._lock:
            return self._battles.get(battle_id, default)

    def set(self, battle_id: str, battle: Any) -> None:
        """Stores a battle instance, evicting oldest finished battles if max capacity is reached."""
        with self._lock:
            if len(self._battles) >= self._max_size:
                # Evict finished battles first, or oldest
                finished = [k for k, b in self._battles.items() if getattr(b, "is_finished", False)]
                if finished:
                    del self._battles[finished[0]]
                elif self._battles:
                    first_k = next(iter(self._battles))
                    del self._battles[first_k]
            self._battles[battle_id] = battle

    def __setitem__(self, battle_id: str, battle: Any) -> None:
        self.set(battle_id, battle)

    def __getitem__(self, battle_id: str) -> Any:
        with self._lock:
            return self._battles[battle_id]

    def __contains__(self, battle_id: str) -> bool:
        with self._lock:
            return battle_id in self._battles

    def __len__(self) -> int:
        with self._lock:
            return len(self._battles)


ACTIVE_BATTLES = ActiveBattleStore(max_size=100)


@app.route("/simulator")
def battle_simulator():
    """Renders the Showdown-style Battle Simulator page."""
    sample_teams = get_sample_teams()
    return render_template(
        "simulator.html",
        sample_teams=sample_teams,
        is_random=request.args.get("random") == "true",
    )


@app.route("/api/simulator/init", methods=["POST"])
def api_simulator_init():
    """Initializes a new battle with custom or sample teams and AI difficulty."""
    try:
        data = request.get_json() or {}
        team1_data = data.get("team1") or []
        team2_data = data.get("team2") or []

        sample_teams = get_sample_teams()
        if isinstance(team1_data, str) and sample_teams and team1_data in sample_teams:
            team1_data = sample_teams[team1_data].get("members", [])
        if isinstance(team2_data, str) and sample_teams and team2_data in sample_teams:
            team2_data = sample_teams[team2_data].get("members", [])

        if not team1_data and sample_teams:
            team1_data = list(sample_teams.values())[0].get("members", [])
        if not team2_data and sample_teams:
            team2_data = list(sample_teams.values())[min(1, len(sample_teams) - 1)].get("members", [])

        name1 = data.get("name1") or "Player"
        name2 = data.get("name2") or "Championship AI"
        is_ai1 = bool(data.get("isAi1", False))
        diff1 = int(data.get("difficulty1", 75))
        is_ai2 = bool(data.get("isAi2", True))
        diff2 = int(data.get("difficulty2", 90))
        ruleset = data.get("ruleset") or "singles"
        level = int(data.get("level", 50))

        battle_id = f"battle_{uuid.uuid4().hex[:10]}"
        battle = BattleSimulator(
            team1_data=team1_data,
            team2_data=team2_data,
            name1=name1,
            name2=name2,
            is_ai_side1=is_ai1,
            difficulty1=diff1,
            is_ai_side2=is_ai2,
            difficulty2=diff2,
            ruleset=ruleset,
            level=level,
        )
        ACTIVE_BATTLES[battle_id] = battle

        return jsonify({
            "success": True,
            "battleId": battle_id,
            "state": battle.to_dict(),
        })
    except Exception as e:
        logger.error(f"Error initializing simulator battle: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/simulator/step", methods=["POST"])
def api_simulator_step():
    """Executes a single turn of the battle."""
    try:
        data = request.get_json() or {}
        battle_id = data.get("battleId")
        battle = ACTIVE_BATTLES.get(battle_id)
        if not battle:
            return jsonify({"error": "Battle session expired or not found"}), 404

        knowledge = load_battle_knowledge()

        # Determine Action 1 (Player or AI 1)
        if battle.side1.is_ai:
            coach1 = data.get("coachDirective1")
            action1 = choose_ai_action(
                battle, "side1", difficulty=battle.side1.difficulty,
                coach_directive=coach1, knowledge_heuristics=knowledge,
            )
        else:
            action1 = data.get("action1")
            # If user must select a replacement switch after faint
            if battle.pending_switch.get("side1"):
                if action1 and action1.get("type") == "switch":
                    t_idx = action1.get("targetIndex", 0)
                    alive_bench = battle.side1.get_alive_bench_indices()
                    if t_idx in alive_bench:
                        events_before = len(battle.battle_log)
                        battle.perform_switch(battle.side1, battle.side2, t_idx, is_replacement=True)
                        battle.pending_switch["side1"] = False
                        new_events = battle.battle_log[events_before:]
                        return jsonify({
                            "success": True,
                            "state": battle.to_dict(),
                            "newEvents": new_events,
                            "outcome": None,
                        })
                return jsonify({"error": "Your active Pokémon fainted. Please choose a Pokémon to send out."}), 400

            if not action1:
                active_m = battle.side1.active_pokemon.moves if battle.side1.active_pokemon else ["tackle"]
                action1 = {"type": "move", "move": active_m[0]}

        # Determine Action 2 (AI 2)
        coach2 = data.get("coachDirective2")
        action2 = choose_ai_action(
            battle, "side2", difficulty=battle.side2.difficulty,
            coach_directive=coach2, knowledge_heuristics=knowledge,
        )

        events_before = len(battle.battle_log)
        battle.execute_turn(action1, action2)
        new_events = battle.battle_log[events_before:]

        outcome = None
        if battle.is_finished:
            try:
                outcome = record_battle_outcome(battle)
            except Exception as rec_err:
                logger.error(f"Error recording battle outcome: {rec_err}")

        return jsonify({
            "success": True,
            "state": battle.to_dict(),
            "newEvents": new_events,
            "outcome": outcome,
        })
    except Exception as e:
        logger.error(f"Error executing simulator step: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/simulator/switch_replacement", methods=["POST"])
def api_simulator_switch_replacement():
    """Handles user selecting a replacement Pokémon after active Pokémon faints."""
    try:
        data = request.get_json() or {}
        battle_id = data.get("battleId")
        battle = ACTIVE_BATTLES.get(battle_id)
        if not battle:
            return jsonify({"error": "Battle session expired or not found"}), 404

        target_idx = data.get("targetIndex")
        if target_idx is None:
            return jsonify({"error": "Missing targetIndex"}), 400

        alive_bench = battle.side1.get_alive_bench_indices()
        if target_idx not in alive_bench:
            return jsonify({"error": "Invalid replacement target index"}), 400

        events_before = len(battle.battle_log)
        battle.perform_switch(battle.side1, battle.side2, target_idx, is_replacement=True)
        battle.pending_switch["side1"] = False
        new_events = battle.battle_log[events_before:]

        return jsonify({
            "success": True,
            "state": battle.to_dict(),
            "newEvents": new_events,
        })
    except Exception as e:
        logger.error(f"Error performing replacement switch: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/simulator/knowledge", methods=["GET"])
def api_simulator_knowledge():
    """Returns AI battle knowledge cache telemetry and heuristics."""
    return jsonify({"success": True, "knowledge": load_battle_knowledge()})


@app.route("/api/simulator/knowledge/reset", methods=["POST"])
def api_simulator_knowledge_reset():
    """Resets the AI battle knowledge cache."""
    return jsonify({"success": True, "knowledge": reset_battle_knowledge()})


@app.route("/guide")
@app.route("/docs/guide")
def operational_guide():
    """Operational & Strategy Master Guide for PokéDex Hub."""
    return render_template("operational_guide.html")


@app.route("/developer")
@app.route("/docs/developer")
def developer_docs():
    """Developer Technical Documentation & Architecture Reference Manual."""
    return render_template("developer_docs.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n🚀 Pokémon Web App running on http://127.0.0.1:{port}/")
    print(f"ℹ️  Defaulting to port {port} to prevent conflicts with macOS AirPlay Receiver on port 5000.\n")
    app.run(debug=True, host="127.0.0.1", port=port)
