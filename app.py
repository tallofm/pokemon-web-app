from flask import Flask, render_template, request, redirect, url_for
from utils.pokeapi import get_pokemon, get_species, get_flavor_text, get_evolution_chain, get_form_variants
from utils.cache import (
    get_pokemon_cached,
    get_species_cached,
    get_evolution_chain_cached,
    get_type_cached,
    get_generation_cached,
    refresh_cache,
    backup_cache,
    recover_cache,
    backup_extra_cache,
    refresh_extra_cache,
    recover_extra_cache
)
import requests
import random
from utils import cache

app = Flask(__name__)

@app.route('/toggle_logging')
def toggle_logging():
    cache.ENABLE_VERBOSE_LOGGING = not cache.ENABLE_VERBOSE_LOGGING
    state = "enabled" if cache.ENABLE_VERBOSE_LOGGING else "disabled"
    return redirect(url_for('pokedex', message=f"Verbose logging {state}"))

@app.route('/refresh_cache')
def refresh_cache_route():
    refresh_cache()
    return redirect(url_for('pokedex'))

@app.route('/backup_cache')
def backup_cache_route():
    backup_cache()
    return redirect(url_for('pokedex'))

@app.route('/recover_cache')
def recover_cache_route():
    recover_cache()
    return redirect(url_for('pokedex'))

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
    recover_extra_cache()
    return redirect(url_for('pokedex'))

@app.route('/')
def home():
    return "<h1>Welcome to the Pokémon App!</h1>"

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
            species_list = list(set(species_list) & set(gen_species))

    if search:
        species_list = [name for name in species_list if name.startswith(search)]

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
            "sprite": poke["sprites"]["other"]["official-artwork"]["front_default"],
            "shiny_sprite": poke["sprites"]["other"]["official-artwork"]["front_shiny"],
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
    def stat_color(value):
        """Returns a color from red (0) → yellow (128) → green (256)"""
        if value <= 128:
            r = 255
            g = int((value / 128) * 255)
        else:
            r = int((1 - ((value - 128) / 128)) * 255)
            g = 255
        return f'rgb({r},{g},0)'

    poke = get_pokemon_cached(name, get_pokemon)
    species = get_species_cached(name)
    flavor = get_flavor_text(species) if species else "No description available."

    form_variants = get_form_variants(species) if species else []
    form_data = []
    for f in form_variants:
        poke_form = get_pokemon_cached(f["name"], get_pokemon)
        if poke_form:
            form_data.append({
                "name": f["name"].capitalize(),
                "sprite": poke_form["sprites"]["front_default"],
                "is_default": f["is_default"]
            })

    evolutions = get_evolution_chain_cached(species) if species else []
    evolution_data = []
    for evo_name in evolutions:
        evo_data = get_pokemon_cached(evo_name, get_pokemon)
        if evo_data:
            evolution_data.append({
                "name": evo_name.capitalize(),
                "sprite": evo_data["sprites"]["front_default"]
            })

    if not poke:
        return "Pokémon not found", 404

    data = {
        "name": poke["name"].capitalize(),
        "id": poke["id"],
        "sprite": poke["sprites"]["other"]["official-artwork"]["front_default"],
        "shiny_sprite": poke["sprites"]["other"]["official-artwork"]["front_shiny"],
        "types": [t["type"]["name"] for t in poke["types"]],
        "stats": {s["stat"]["name"]: s["base_stat"] for s in poke["stats"]},
        "description": flavor,
        "evolutions": evolution_data,
        "forms": form_data,
        "height": poke["height"],
        "weight": poke["weight"],
        "base_experience": poke["base_experience"],
        "abilities": [a["ability"]["name"] for a in poke["abilities"]],
        "egg_groups": [g["name"] for g in species["egg_groups"]] if species else [],
    }

    return render_template("pokemon_detail.html", p=data, stat_color=stat_color)

@app.route('/generation/<int:gen_id>')
def generation_view(gen_id):
    data = get_generation_cached(gen_id)
    if not data:
        return f"Generation {gen_id} not found", 404

    species_list = sorted([s["name"].capitalize() for s in data["pokemon_species"]])

    pokemon_list = []
    for name in species_list:
        poke = get_pokemon_cached(name, get_pokemon)
        if poke:
            pokemon_list.append({
                "name": poke["name"].capitalize(),
                "id": poke["id"],
                "types": [t["type"]["name"] for t in poke["types"]],
                "sprite": poke["sprites"]["front_default"]
            })

    return render_template("generation_view.html",
        gen_id=gen_id,
        pokemon_list=pokemon_list
    )

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
                "sprite": poke["sprites"]["front_default"]
            })

    pokemon_list.sort(key=lambda x: x["id"])

    return render_template("type_view.html", type_name=type_name, pokemon_list=pokemon_list)

if __name__ == '__main__':
    app.run(debug=True)
