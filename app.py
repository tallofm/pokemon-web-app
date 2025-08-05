from flask import Flask, render_template, request
from utils.pokeapi import get_pokemon
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

if __name__ == '__main__':
    app.run(debug=True)
