from flask import Flask, render_template, request, redirect, url_for
from utils.pokeapi import get_pokemon, get_species, get_flavor_text, get_evolution_chain, get_form_variants
from utils.cache import (
    get_all_pokemon_names_cached,
    get_all_types_cached,
    refresh_lists,
    get_pokemon_cached,
    get_species_cached,
    get_evolution_chain_cached,
    get_type_cached,
    get_generation_cached,
    get_default_variety_cached,
    bulk_prime_default_varieties,
    refresh_cache,
    backup_cache,
    recover_cache,
    backup_extra_cache,
    refresh_extra_cache,
    recover_extra_cache
)
import requests
import random
import re
from utils import cache

app = Flask(__name__)

# helper: consistent labels for stats/types
def labelize(s: str) -> str:
    s = (s or "").replace("-", " ")
    overrides = {"hp": "HP", "sp atk": "Sp. Atk", "sp def": "Sp. Def",
                 "special attack": "SpAtk", "special defense": "SpDef"}
    t = s.strip().title()
    return overrides.get(s.strip().lower(), overrides.get(t.lower(), t))

app.jinja_env.filters['labelize'] = labelize

@app.route('/toggle_logging')
def toggle_logging():
    cache.ENABLE_VERBOSE_LOGGING = not cache.ENABLE_VERBOSE_LOGGING
    state = "enabled" if cache.ENABLE_VERBOSE_LOGGING else "disabled"
    return redirect(url_for('pokedex', message=f"Verbose logging {state}"))

@app.route('/backup_cache')
def backup_cache_route():
    backup_cache()
    return redirect(url_for('pokedex'))

@app.route('/refresh_cache')
def refresh_cache_route():
    refresh_cache()
    return redirect(url_for('pokedex'))

@app.route('/recover_cache')
def recover_cache_route():
    ok = recover_cache()
    return redirect(url_for('pokedex', message=('Recovered Pokémon cache' if ok else 'Recover failed')))

@app.route('/backup_extra_cache')
def backup_extra_cache_route():
    backup_extra_cache()
    return redirect(url_for('pokedex'))

@app.route('/refresh_extra_cache')
def refresh_extra_cache_route():
    refresh_extra_cache()
    return redirect(url_for('pokedex'))

@app.route('/recover_extra_cache')
def recover_extra_cache_route():
    ok = recover_extra_cache()
    return redirect(url_for('pokedex', message=('Recovered extra cache' if ok else 'Recover failed')))

# refresh pokemon and type list
@app.route('/refresh_lists')
def refresh_lists_route():
    # clears all list keys, then re-primes to keep UX snappy
    refresh_lists()  # wipe
    # re-prime both lists
    _ = get_all_pokemon_names_cached()
    _ = get_all_types_cached(exclude_special=False)
    _ = get_all_types_cached(exclude_special=True)
    return redirect(url_for('pokedex'))


@app.route('/')
def home():
    return "<h1>Welcome to the Pokémon App!</h1>"

def best_sprite(p):
    """return the best available sprite url"""
    s = p.get("sprites", {})
    other = s.get("other", {})
    return (
        other.get("official-artwork", {}).get("front_default")
        or s.get("front_default")
        or other.get("dream_world", {}).get("front_default")
        or other.get("home", {}).get("front_default")
    )

@app.route('/pokedex')
def pokedex():
    limit = int(request.args.get("limit") or 12)
    offset = int(request.args.get("offset") or 0)
    sort_by = request.args.get("sort", "id")
    type_filter = request.args.get("type")
    generation = request.args.get("generation")
    selected_name = request.args.get("pokemon")
    search = request.args.get("search", "").lower()
    randomize = request.args.get("random") == "true"

    # 🔸 cached once, re-used forever (until you refresh extra cache)
    all_pokemon_names = get_all_pokemon_names_cached()
    species_list = list(all_pokemon_names)

    if type_filter:
        type_data = get_type_cached(type_filter)
        if type_data:
            # get_type_cached now carries "pokemon" members in your latest version
            type_pokemon_names = [entry["pokemon"]["name"] for entry in type_data.get("pokemon", [])]
            species_list = list(set(species_list) & set(type_pokemon_names))

    if generation:
        gen_data = get_generation_cached(generation)
        if gen_data:
            gen_species = [s["name"] for s in gen_data["pokemon_species"]]
            gen_pokemon_names = bulk_prime_default_varieties(gen_species)
            species_list = list(set(species_list) & set(gen_pokemon_names))

    if search:
        def wildcard_to_regex(pattern):
            escaped = re.escape(pattern)
            return '^' + escaped.replace(r'\*', '.*') + '$'
        regex = re.compile(wildcard_to_regex(search))
        species_list = [name for name in species_list if regex.search(name)]

    if selected_name:
        selected_names = [selected_name]
    elif randomize:
        selected_names = random.sample(species_list, min(limit, len(species_list)))
    else:
        selected_names = species_list[offset:offset + limit]

    pokemon_data = []
    all_types_seen = set()

    for name in selected_names:
        poke = get_pokemon_cached(name, get_pokemon)
        if not poke:
            continue
        types = [t["type"]["name"] for t in poke["types"]]
        all_types_seen.update(types)
        if type_filter and type_filter.lower() not in types:
            continue
        pokemon_data.append({
            "name": poke["name"].capitalize(),
            "id": poke["id"],
            "sprite": best_sprite(poke),
            "shiny_sprite": (poke.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_shiny")),
            "types": types
        })

    pokemon_data.sort(key=(lambda x: x["name"]) if sort_by == "name" else (lambda x: x["id"]))

    all_gens = list(range(1, 10))
    all_types = get_all_types_cached()  # 🔸 cached type list

    return render_template("pokedex.html",
        pokemon_list=pokemon_data,
        all_types=all_types,
        all_gens=all_gens,
        all_pokemon_names=all_pokemon_names,
        current_type=type_filter,
        current_sort=sort_by,
        offset=offset,
        limit=limit,
        search=search,
        total_matches=len(species_list),
        logging_enabled=cache.ENABLE_VERBOSE_LOGGING
    )

@app.route('/pokemon/<name>')
def pokemon_detail(name):
    """pokemon detail page data loader"""

    # helper for stat heat color (0→red, 128→yellow, 256→green)
    def stat_color(value: int) -> str:
        if value <= 128:
            r, g = 255, int((value / 128) * 255)
        else:
            r, g = int((1 - ((value - 128) / 128)) * 255), 255
        return f'rgb({r},{g},0)'

    # fetch core data
    poke = get_pokemon_cached(name, get_pokemon)
    if not poke:
        return "Pokémon not found", 404

    species = get_species_cached(name)
    flavor = get_flavor_text(species) if species else "No description available."

    # build forms
    form_data = []
    if species:
        for f in (get_form_variants(species) or []):
            pf = get_pokemon_cached(f["name"], get_pokemon)
            if pf:
                form_data.append({
                    "name": f["name"].capitalize(),
                    "sprite": (pf.get("sprites", {})
                                 .get("front_default")),
                    "is_default": f.get("is_default", False),
                })

    # build evolutions
    evolution_data = []
    if species:
        for evo_name in (get_evolution_chain_cached(species) or []):
            ed = get_pokemon_cached(evo_name, get_pokemon)
            if ed:
                evolution_data.append({
                    "name": evo_name.capitalize(),
                    "sprite": (ed.get("sprites", {})
                                 .get("front_default")),
                })

    # stats + colors
    stats = {s["stat"]["name"]: s["base_stat"] for s in poke.get("stats", [])}
    stat_colors = {k: stat_color(v) for k, v in stats.items()}

    # type effectiveness (defense + offense)
    from utils.type_effectiveness import build_effectiveness
    types_list = [t["type"]["name"] for t in poke.get("types", [])]
    effectiveness = build_effectiveness([t.lower() for t in types_list])
    all_types = list(effectiveness["defense"].keys())

    # assemble payload
    p = {
        "name": poke["name"].capitalize(),
        "id": poke["id"],
        "sprite": (poke.get("sprites", {})
                        .get("other", {})
                        .get("official-artwork", {})
                        .get("front_default")),
        "shiny_sprite": (poke.get("sprites", {})
                             .get("other", {})
                             .get("official-artwork", {})
                             .get("front_shiny")),
        "types": types_list,
        "stats": stats,
        "stat_colors": stat_colors,          # use in template: p.stat_colors['hp']
        "description": flavor,
        "evolutions": evolution_data,
        "forms": form_data,
        "height": poke.get("height"),
        "weight": poke.get("weight"),
        "base_experience": poke.get("base_experience"),
        "abilities": [a["ability"]["name"] for a in poke.get("abilities", [])],
        "egg_groups": [g["name"] for g in species.get("egg_groups", [])] if species else [],
        "effectiveness": effectiveness,      # p.effectiveness.defense / offense
        "all_types": all_types               # iterate grid headings
    }

    # pass only p (keeps jinja clean)
    return render_template("pokemon_detail.html", p=p)


@app.route('/generation/<int:gen_id>')
def generation_view(gen_id):
    data = get_generation_cached(gen_id)
    if not data:
        return f"Generation {gen_id} not found", 404

    sp_names = [s["name"] for s in data.get("pokemon_species", [])]
    default_names = bulk_prime_default_varieties(sp_names)

    pokemon_list = []
    for poke_name in sorted(default_names):
        p = get_pokemon_cached(poke_name, get_pokemon)
        if not p:
            continue
        pokemon_list.append({
            "name": p.get("name", "").capitalize(),
            "id": p.get("id"),
            "types": [t["type"]["name"] for t in p.get("types", [])],
            "sprite": best_sprite(p) or url_for("static", filename="img/placeholder.png")
        })

    return render_template("generation_view.html", gen_id=gen_id, pokemon_list=pokemon_list)

ALLOWED_TYPES = get_all_types_cached(exclude_special=True)

@app.route('/type/<type_name>')
def type_view(type_name):
    type_data = get_type_cached(type_name)
    if not type_data:
        return f"Type '{type_name}' not found", 404

    pokemon_entries = type_data["pokemon"]
    rel = type_data["damage_relations"]
    pokemon_list = []

    for entry in pokemon_entries:
        poke = get_pokemon_cached(entry["pokemon"]["name"], get_pokemon)
        if poke:
            pokemon_list.append({
                "name": poke["name"].capitalize(),
                "id": poke["id"],
                "types": [t["type"]["name"] for t in poke["types"]],
                "sprite": best_sprite(poke) or url_for("static", filename="img/placeholder.png")
            })

    pokemon_list.sort(key=lambda x: x["id"])

    return render_template(
        "type_view.html",
        type_name=type_name,
        pokemon_list=pokemon_list,
        rel=rel,
        all_types=ALLOWED_TYPES
        )
        

from fractions import Fraction

def _mult_vs(attacking_type: str, defender_type: str) -> Fraction:
    """Return multiplier as a Fraction (0, 1/2, 1, 2)."""
    t = get_type_cached(attacking_type) or {}
    rel = (t.get("damage_relations") or {})
    if any(x.get("name") == defender_type for x in rel.get("no_damage_to", [])):
        return Fraction(0, 1)
    if any(x.get("name") == defender_type for x in rel.get("double_damage_to", [])):
        return Fraction(2, 1)
    if any(x.get("name") == defender_type for x in rel.get("half_damage_to", [])):
        return Fraction(1, 2)
    return Fraction(1, 1)

# ---- Defense: up to 3 defender types -> buckets including 8x and 1/8x
DEF_BUCKETS_ORDER = ["8x", "4x", "2x", "1x", "1/2x", "1/4x", "1/8x", "0x"]
DEF_MAP = {
    Fraction(8,1): "8x",
    Fraction(4,1): "4x",
    Fraction(2,1): "2x",
    Fraction(1,1): "1x",
    Fraction(1,2): "1/2x",
    Fraction(1,4): "1/4x",
    Fraction(1,8): "1/8x",
    Fraction(0,1): "0x",
}

def calc_defense_buckets(def_types: list[str]) -> dict[str, list[str]]:
    buckets = {k: [] for k in DEF_BUCKETS_ORDER}
    for atk in ALLOWED_TYPES:
        mult = Fraction(1,1)
        for d in def_types:
            mult *= _mult_vs(atk, d)
            if mult == 0:
                break
        key = DEF_MAP.get(mult, "1x")  # safety fallback
        buckets[key].append(atk)
    return buckets

# ---- Offense: up to 2 attacking types -> buckets including 4x and 1/4x
OFF_BUCKETS_ORDER = ["4x", "2x", "1x", "1/2x", "1/4x", "0x"]
OFF_MAP = {
    Fraction(4,1): "4x",
    Fraction(2,1): "2x",
    Fraction(1,1): "1x",
    Fraction(1,2): "1/2x",
    Fraction(1,4): "1/4x",
    Fraction(0,1): "0x",
}

def calc_offense_buckets(attacking_types: list[str]) -> dict[str, list[str]]:
    buckets = {k: [] for k in OFF_BUCKETS_ORDER}
    for d in ALLOWED_TYPES:
        mult = Fraction(1,1)
        for atk in attacking_types:
            mult *= _mult_vs(atk, d)
            if mult == 0:
                break
        key = OFF_MAP.get(mult, "1x")
        buckets[key].append(d)
    return buckets

def _names_with_types(def_types: list[str]) -> list[str]:
    """
    Get Pokémon names that have *all* selected defender types.
    Uses the type endpoint and intersects.
    """
    if not def_types:
        return []
    # start with the first list
    first = get_type_cached(def_types[0]) or {}
    names = {p["pokemon"]["name"] for p in first.get("pokemon", [])}
    # intersect with the rest
    for t in def_types[1:]:
        td = get_type_cached(t) or {}
        names &= {p["pokemon"]["name"] for p in td.get("pokemon", [])}
    # basic sort (dex-ish feel by fetching id for a handful only when rendering)
    return sorted(names)

@app.route("/type_tool")
def type_tool():
    # query params (defense up to 3, offense up to 2)
    d1 = (request.args.get("d1") or "water").lower()
    d2 = (request.args.get("d2") or "").lower()
    d3 = (request.args.get("d3") or "").lower()
    a1 = (request.args.get("a1") or "water").lower()
    a2 = (request.args.get("a2") or "").lower()

    defense_types = [t for t in [d1, d2, d3] if t in ALLOWED_TYPES]
    offense_types = [t for t in [a1, a2] if t in ALLOWED_TYPES]

    defense = calc_defense_buckets(defense_types) if defense_types else None
    offense = calc_offense_buckets(offense_types) if offense_types else None

    # build simple cards for Pokémon that match defense typing
    matched_cards = []
    if defense_types:
        for name in _names_with_types(defense_types)[:200]:  # safety cap
            p = get_pokemon_cached(name, get_pokemon)  # you already import this above
            if not p: 
                continue
            matched_cards.append({
                "name": p["name"].capitalize(),
                # "id": p["id"],
                "sprite": (
                    p.get("sprites", {})
                     .get("other", {})
                     .get("official-artwork", {})
                     .get("front_default")
                    or p.get("sprites", {}).get("front_default")
                )
            })

    return render_template(
        "type_tool.html",
        all_types=ALLOWED_TYPES,
        defense_types=defense_types,
        offense_types=offense_types,
        d1=d1, d2=d2, d3=d3, a1=a1, a2=a2,
        defense=defense,
        offense=offense,
        matched=matched_cards,
    )


if __name__ == '__main__':
    app.run(debug=True)
