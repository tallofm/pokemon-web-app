import requests

POKEMON_API = "https://pokeapi.co/api/v2/pokemon/"
SPECIES_API = "https://pokeapi.co/api/v2/pokemon-species/"

def get_pokemon(name_or_id):
    url = f"{POKEMON_API}{name_or_id.strip().lower()}/"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    return res.json()

def get_species(name_or_id):
    url = f"{SPECIES_API}{name_or_id.strip().lower()}/"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    return res.json()

def get_flavor_text(species_json):
    entries = species_json.get("flavor_text_entries", [])
    for e in entries:
        if e["language"]["name"] == "en":
            return e["flavor_text"].replace("\n", " ").replace("\f", " ")
    return "No description available."
