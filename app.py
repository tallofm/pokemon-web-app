from flask import Flask, render_template, request
from utils.pokeapi import get_pokemon, get_species, get_flavor_text, get_evolution_chain, get_form_variants
import requests
import random

app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>Welcome to the Pokémon App!</h1>"

@app.route('/pokedex')
def pokedex():
    limit = int(request.args.get("limit") or 12)
    offset = int(request.args.get("offset") or 0)
    sort_by = request.args.get("sort", "id")
    type_filter = request.args.get("type")
    randomize = request.args.get("random", "false") == "true"
    generation = request.args.get("generation")
    selected_name = request.args.get("pokemon")
    search = request.args.get("search", "").lower()

    # get full list of Pokémon names
    full_res = requests.get("https://pokeapi.co/api/v2/pokemon?limit=10000&offset=0")
    all_pokemon_urls = full_res.json()["results"]
    all_pokemon_names = [p["name"] for p in all_pokemon_urls]

    species_list = all_pokemon_names

    # if type filter is set, narrow species list
    if type_filter:
        type_res = requests.get(f"https://pokeapi.co/api/v2/type/{type_filter.lower()}")
        if type_res.status_code == 200:
            type_pokemon_names = [entry["pokemon"]["name"] for entry in type_res.json()["pokemon"]]
            species_list = list(set(species_list) & set(type_pokemon_names))

    # apply generation filter (if any)
    if generation:
        gen_res = requests.get(f"https://pokeapi.co/api/v2/generation/{generation}/")
        gen_species = [s["name"] for s in gen_res.json()["pokemon_species"]]
        species_list = list(set(species_list) & set(gen_species))

    # apply search
    if search:
        species_list = [name for name in species_list if name.startswith(search)]

    # decide what names to display
    if selected_name:
        selected_names = [selected_name]
    elif randomize:
        selected_names = random.sample(species_list, min(limit, len(species_list)))
    else:
        selected_names = species_list[offset:offset + limit]

    # fetch data for displayed Pokémon
    pokemon_data = []
    all_types_seen = set()

    for name in selected_names:
        poke = get_pokemon(name)
        if not poke:
            continue
        types = [t["type"]["name"] for t in poke["types"]]
        all_types_seen.update(types)
        if type_filter and type_filter.lower() not in types:
            continue
        pokemon_data.append({
            "name": poke["name"].capitalize(),
            "id": poke["id"],
            "sprite": poke["sprites"]["front_default"],
            "types": types
        })

    # sort if needed
    if sort_by == "name":
        pokemon_data.sort(key=lambda x: x["name"])
    else:
        pokemon_data.sort(key=lambda x: x["id"])

    # fetch full list of all Pokémon types (static source)
    type_res = requests.get("https://pokeapi.co/api/v2/type")
    all_types = sorted([t["name"] for t in type_res.json()["results"]])

    all_gens = list(range(1, 10))  # gen 1–9

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
        total_matches=len(species_list)
    )


@app.route('/pokemon/<name>')
def pokemon_detail(name):
    poke = get_pokemon(name)
    species = get_species(name)
    flavor = get_flavor_text(species) if species else "No description available."

    form_variants = get_form_variants(species) if species else []
    form_data = []
    for f in form_variants:
        poke_form = get_pokemon(f["name"])
        if poke_form:
            form_data.append({
                "name": f["name"].capitalize(),
                "sprite": poke_form["sprites"]["front_default"],
                "is_default": f["is_default"]
            })
    
    evolutions = get_evolution_chain(species) if species else []
    # fetch sprites for evolutions
    evolution_data = []
    for evo_name in evolutions:
        evo_data = get_pokemon(evo_name)
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
        "types": [t["type"]["name"] for t in poke["types"]],
        "stats": {s["stat"]["name"]: s["base_stat"] for s in poke["stats"]},
        "description": flavor,
        "evolutions": evolution_data,
        "forms": form_data
    }


    return render_template("pokemon_detail.html", p=data)

@app.route('/generation/<int:gen_id>')
def generation_view(gen_id):
    res = requests.get(f"https://pokeapi.co/api/v2/generation/{gen_id}/")
    if res.status_code != 200:
        return f"Generation {gen_id} not found", 404

    data = res.json()
    species_list = sorted(data["pokemon_species"], key=lambda x: x["name"])
    
    pokemon_list = []
    for s in species_list:
        # get ID from species URL
        url_parts = s["url"].rstrip("/").split("/")
        poke_id = int(url_parts[-1])
        pokemon_list.append({
            "name": s["name"].capitalize(),
            "id": poke_id
        })

    return render_template("generation_view.html", gen_id=gen_id, pokemon_list=pokemon_list)

@app.route('/type/<type_name>')
def type_view(type_name):
    # fetch all Pokémon by type
    type_res = requests.get(f"https://pokeapi.co/api/v2/type/{type_name.lower()}")
    if type_res.status_code != 200:
        return f"Type '{type_name}' not found", 404

    type_data = type_res.json()
    pokemon_entries = type_data["pokemon"]
    pokemon_list = []

    for entry in pokemon_entries:
        poke = get_pokemon(entry["pokemon"]["name"])
        if poke:
            pokemon_list.append({
                "name": poke["name"].capitalize(),
                "id": poke["id"],
                "types": [t["type"]["name"] for t in poke["types"]]
            })

    pokemon_list.sort(key=lambda x: x["id"])

    return render_template("type_view.html", type_name=type_name, pokemon_list=pokemon_list)


if __name__ == '__main__':
    app.run(debug=True)
