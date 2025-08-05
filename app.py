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
    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))
    sort_by = request.args.get("sort", "id")
    type_filter = request.args.get("type")
    randomize = request.args.get("random", "false") == "true"
    generation = request.args.get("generation")
    selected_name = request.args.get("pokemon")

    # get full list of Pokémon for dropdown
    full_res = requests.get("https://pokeapi.co/api/v2/pokemon?limit=10000&offset=0")
    all_pokemon_names = [p["name"] for p in full_res.json()["results"]]

    # apply generation filter
    if generation:
        gen_res = requests.get(f"https://pokeapi.co/api/v2/generation/{generation}/")
        species_list = [s["name"] for s in gen_res.json()["pokemon_species"]]
    else:
        species_list = all_pokemon_names

    # select names to load
    if selected_name:
        selected_names = [selected_name]
    elif randomize:
        selected_names = random.sample(species_list, min(limit, len(species_list)))
    else:
        selected_names = species_list[offset:offset + limit]

    # fetch data for selected Pokémon
    pokemon_data = []
    for name in selected_names:
        poke = get_pokemon(name)
        if not poke:
            continue
        types = [t["type"]["name"] for t in poke["types"]]
        if type_filter and type_filter.lower() not in types:
            continue

        pokemon_data.append({
            "name": poke["name"].capitalize(),
            "id": poke["id"],
            "sprite": poke["sprites"]["front_default"],
            "types": types
        })

    # sorting
    if sort_by == "name":
        pokemon_data.sort(key=lambda x: x["name"])
    else:
        pokemon_data.sort(key=lambda x: x["id"])

    # prepare values for UI
    all_types = sorted(set(t for p in pokemon_data for t in p["types"]))
    all_gens = list(range(1, 10))  # Generation 1 to 9

    return render_template("pokedex.html",
        pokemon_list=pokemon_data,
        all_types=all_types,
        all_gens=all_gens,
        all_pokemon_names=all_pokemon_names,
        current_type=type_filter,
        current_sort=sort_by,
        offset=offset,
        limit=limit
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

if __name__ == '__main__':
    app.run(debug=True)
