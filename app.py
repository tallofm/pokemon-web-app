from flask import Flask, render_template, request, redirect, url_for
from utils.pokeapi import get_pokemon, get_species, get_flavor_text, get_evolution_chain, get_form_variants
from utils.cache import (
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

    full_res = requests.get("https://pokeapi.co/api/v2/pokemon?limit=10000&offset=0")
    all_pokemon_urls = full_res.json()["results"]
    all_pokemon_names = [p["name"] for p in all_pokemon_urls]

    species_list = all_pokemon_names

    if type_filter:
        type_data = get_type_cached(type_filter)
        if type_data:
            type_pokemon_names = [entry["pokemon"]["name"] for entry in type_data["pokemon"]]
            species_list = list(set(species_list) & set(type_pokemon_names))

    if generation:
        gen_data = get_generation_cached(generation)
        if gen_data:
            gen_species = [s["name"] for s in gen_data["pokemon_species"]]
            gen_pokemon_names = bulk_prime_default_varieties(gen_species)  # batch, single save
            species_list = list(set(species_list) & set(gen_pokemon_names))

    if search:
        def wildcard_to_regex(pattern):
            escaped = re.escape(pattern)
            regex_pattern = '^' + escaped.replace(r'\*', '.*') + '$'
            return regex_pattern

        pattern = wildcard_to_regex(search)
        regex = re.compile(pattern)
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

    if sort_by == "name":
        pokemon_data.sort(key=lambda x: x["name"])
    else:
        pokemon_data.sort(key=lambda x: x["id"])

    type_res = requests.get("https://pokeapi.co/api/v2/type")
    all_types = sorted([t["name"] for t in type_res.json()["results"]])
    all_gens = list(range(1, 10))

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

@app.route('/type/<type_name>')
def type_view(type_name):
    type_data = get_type_cached(type_name)
    if not type_data:
        return f"Type '{type_name}' not found", 404

    pokemon_entries = type_data["pokemon"]
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

    return render_template("type_view.html", type_name=type_name, pokemon_list=pokemon_list)

if __name__ == '__main__':
    app.run(debug=True)
