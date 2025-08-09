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
        return {}
    return res.json()

def get_flavor_text(species_json):
    entries = species_json.get("flavor_text_entries", [])
    for e in entries:
        if e["language"]["name"] == "en":
            return e["flavor_text"].replace("\n", " ").replace("\f", " ")
    return "No description available."
    
 
def get_evolution_chain(species_json):
    evo_chain_url = species_json.get("evolution_chain", {}).get("url")
    if not evo_chain_url:
        return []

    res = requests.get(evo_chain_url)
    if res.status_code != 200:
        return []

    chain = res.json().get("chain", {})
    evolution_line = []

    def traverse(chain_node):
        name = chain_node["species"]["name"]
        evolution_line.append(name)
        for evo in chain_node.get("evolves_to", []):
            traverse(evo)

    traverse(chain)
    return evolution_line

def get_form_variants(species_json):
    forms = []
    varieties = species_json.get("varieties", [])
    for var in varieties:
        p = var["pokemon"]
        forms.append({
            "name": p["name"],
            "url": p["url"],
            "is_default": var.get("is_default", False)
        })
    return forms

def get_type(name: str):
    # returns minimal payload needed by type effectiveness
    n = str(name).lower()
    url = f"https://pokeapi.co/api/v2/type/{n}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    return {
        "name": data.get("name", n),
        "damage_relations": data.get("damage_relations", {})
    }