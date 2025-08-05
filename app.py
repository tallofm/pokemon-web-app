from flask import Flask, render_template, request
from utils.pokeapi import get_pokemon
from utils.pokeapi import get_pokemon, get_species, get_flavor_text
import requests

app = Flask(__name__)

@app.route('/pokedex')
def pokedex():
    import requests  # needed for list query
    from collections import OrderedDict

    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))
    sort_by = request.args.get("sort", "id")
    type_filter = request.args.get("type")

    res = requests.get(f"https://pokeapi.co/api/v2/pokemon?limit={limit}&offset={offset}")
    if res.status_code != 200:
        return "Failed to fetch Pokémon", 500

    results = res.json().get("results", [])
    pokemon_data = []
    for r in results:
        poke = get_pokemon(r["name"])
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

    if sort_by == "name":
        pokemon_data.sort(key=lambda x: x["name"])
    elif sort_by == "id":
        pokemon_data.sort(key=lambda x: x["id"])

    # create unique type list
    all_types = sorted(set(t for p in pokemon_data for t in p["types"]))

    return render_template("pokedex.html",
                           pokemon_list=pokemon_data,
                           all_types=all_types,
                           current_type=type_filter,
                           current_sort=sort_by)

@app.route('/pokemon/<name>')
def pokemon_detail(name):
    poke = get_pokemon(name)
    species = get_species(name)
    flavor = get_flavor_text(species)

    if not poke:
        return "Pokémon not found", 404

    data = {
        "name": poke["name"].capitalize(),
        "id": poke["id"],
        "sprite": poke["sprites"]["other"]["official-artwork"]["front_default"],
        "types": [t["type"]["name"] for t in poke["types"]],
        "stats": {s["stat"]["name"]: s["base_stat"] for s in poke["stats"]},
        "description": flavor
    }
    return render_template("pokemon_detail.html", p=data)


if __name__ == '__main__':
    app.run(debug=True)
