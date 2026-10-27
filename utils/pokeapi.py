import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Base API URLs
POKEMON_API = "https://pokeapi.co/api/v2/pokemon/"
SPECIES_API = "https://pokeapi.co/api/v2/pokemon-species/"
POKEMON_FORM_API = "https://pokeapi.co/api/v2/pokemon-form/"
ABILITY_API = "https://pokeapi.co/api/v2/ability/"
MOVE_API = "https://pokeapi.co/api/v2/move/"
TYPE_API = "https://pokeapi.co/api/v2/type/"
ITEM_API = "https://pokeapi.co/api/v2/item/"

DEFAULT_TIMEOUT = 3.0

# Shared session with retries for resilience
_session = requests.Session()
_retry = Retry(total=2, backoff_factor=0.2, status_forcelist=(429, 500, 502, 503, 504))
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _get_json(url: str, default=None, timeout: float = DEFAULT_TIMEOUT):
    """Safely fetch and return JSON from a URL with retries and timeout."""
    try:
        res = _session.get(url, timeout=timeout)
        if res.status_code == 200:
            return res.json()
        return default
    except requests.RequestException:
        return default


def _extract_flavor_texts(source_json: dict) -> list[dict]:
    """Helper to extract distinct English flavor text entries ordered latest-first."""
    results = []
    seen = set()
    for e in (source_json or {}).get("flavor_text_entries", []):
        if e.get("language", {}).get("name") == "en":
            game_raw = e.get("version", {}).get("name", "Unknown")
            game_name = game_raw.replace("-", " ").title()
            text = e.get("flavor_text", "").replace("\n", " ").replace("\f", " ")
            pair = (game_name, text)
            if pair not in seen:
                seen.add(pair)
                results.append({"game": game_name, "flavor_text": text})
    return list(reversed(results))


def get_move(name_or_id: str | int) -> dict | None:
    """Fetch raw move JSON from PokéAPI."""
    url = f"{MOVE_API}{str(name_or_id).strip().lower()}/"
    return _get_json(url, default=None)


def get_move_short_effect(move_json: dict) -> str:
    """Extract English short effect, replacing format tokens like $effect_chance%."""
    entries = (move_json or {}).get("effect_entries", [])
    chance = str((move_json or {}).get("effect_chance") or "")
    for e in entries:
        if e.get("language", {}).get("name") == "en":
            desc = e.get("short_effect") or e.get("effect", "")
            return desc.replace("$effect_chance%", f"{chance}%").replace("\n", " ").replace("\f", " ")

    # Fallback to flavor text if effect_entries is not present
    for f in (move_json or {}).get("flavor_text_entries", []):
        if f.get("language", {}).get("name") == "en":
            return f.get("flavor_text", "").replace("\n", " ").replace("\f", " ")

    return "No description available."


def get_ability(name_or_id: str | int) -> dict:
    """Fetch raw ability JSON from PokéAPI."""
    url = f"{ABILITY_API}{str(name_or_id).strip().lower()}/"
    return _get_json(url, default={}) or {}


def get_ability_effect(ability_json: dict) -> str:
    """Extract the clean English effect or short effect for an ability."""
    for entry in (ability_json or {}).get("effect_entries", []):
        if entry.get("language", {}).get("name") == "en":
            text = entry.get("short_effect") or entry.get("effect", "")
            return text.replace("\n", " ").replace("\f", " ")

    for entry in (ability_json or {}).get("flavor_text_entries", []):
        if entry.get("language", {}).get("name") == "en":
            return entry.get("flavor_text", "").replace("\n", " ").replace("\f", " ")

    return "No description available."


def get_ability_flavor_text(ability_json: dict) -> str:
    """Extract clean English flavor text for an ability."""
    for entry in reversed((ability_json or {}).get("flavor_text_entries", [])):
        if entry.get("language", {}).get("name") == "en":
            return entry.get("flavor_text", "").replace("\n", " ").replace("\f", " ")
    return "No flavor description available."


def get_item(name_or_id: str | int) -> dict | None:
    """Fetch raw item JSON from PokéAPI."""
    url = f"{ITEM_API}{str(name_or_id).strip().lower()}/"
    return _get_json(url, default=None)


def get_item_short_effect(item_json: dict) -> str:
    """Extract English short effect or effect for an item."""
    for entry in (item_json or {}).get("effect_entries", []):
        if entry.get("language", {}).get("name") == "en":
            text = entry.get("short_effect") or entry.get("effect", "")
            return text.replace("\n", " ").replace("\f", " ")

    for entry in reversed((item_json or {}).get("flavor_text_entries", [])):
        if entry.get("language", {}).get("name") == "en":
            return entry.get("text", "").replace("\n", " ").replace("\f", " ")

    return "No description available."


def get_item_flavor_text(item_json: dict) -> str:
    """Extract clean English flavor text for an item."""
    for entry in reversed((item_json or {}).get("flavor_text_entries", [])):
        if entry.get("language", {}).get("name") == "en":
            return entry.get("text", "").replace("\n", " ").replace("\f", " ")
    return "No flavor description available."


def get_form(name_or_id: str | int) -> dict:
    """Fetch raw pokemon form JSON from PokéAPI."""
    url = f"{POKEMON_FORM_API}{str(name_or_id).strip().lower()}/"
    return _get_json(url, default={}) or {}


def get_form_flavor_text(form_json: dict) -> str | None:
    """Extract the latest English flavor text for a form, or None."""
    texts = _extract_flavor_texts(form_json)
    return texts[0]["flavor_text"] if texts else None


def get_all_form_flavor_texts(form_json: dict) -> list[dict]:
    """Extract all English flavor texts for a form, latest first."""
    return _extract_flavor_texts(form_json)


def get_all_species_flavor_texts(species_json: dict) -> list[dict]:
    """Extract all English flavor texts for a species, latest first."""
    return _extract_flavor_texts(species_json)


def get_pokemon(name_or_id: str | int) -> dict | None:
    """Fetch raw pokemon JSON from PokéAPI."""
    url = f"{POKEMON_API}{str(name_or_id).strip().lower()}/"
    return _get_json(url, default=None)


def get_species(name_or_id: str | int) -> dict:
    """Fetch raw pokemon species JSON from PokéAPI."""
    url = f"{SPECIES_API}{str(name_or_id).strip().lower()}/"
    return _get_json(url, default={}) or {}


def get_flavor_text(species_json: dict) -> str:
    """Extract the latest English flavor text for a species."""
    texts = _extract_flavor_texts(species_json)
    return texts[0]["flavor_text"] if texts else "No description available."


def get_evolution_chain(species_json: dict) -> list[str]:
    """Traverse and return the ordered species names in the evolution chain."""
    evo_chain_url = (species_json or {}).get("evolution_chain", {}).get("url")
    if not evo_chain_url:
        return []

    chain_data = _get_json(evo_chain_url, default=None)
    if not chain_data:
        return []

    chain = chain_data.get("chain", {})
    evolution_line = []

    def traverse(node):
        """Recursively traverses PokéAPI evolution chain nodes."""
        if not node:
            return
        sp_name = node.get("species", {}).get("name")
        if sp_name:
            evolution_line.append(sp_name)
        for evo in node.get("evolves_to", []):
            traverse(evo)

    traverse(chain)
    return evolution_line


def get_form_variants(species_json: dict) -> list[dict]:
    """Extract varieties/forms from species data."""
    forms = []
    varieties = (species_json or {}).get("varieties", [])
    for var in varieties:
        p = var.get("pokemon")
        if p and p.get("name"):
            forms.append({
                "name": p["name"],
                "url": p.get("url", ""),
                "is_default": var.get("is_default", False)
            })
    return forms


def get_type(name: str) -> dict:
    """Returns minimal payload needed for type relations."""
    n = str(name).strip().lower()
    url = f"{TYPE_API}{n}"
    data = _get_json(url, default={}) or {}
    return {
        "name": data.get("name", n),
        "damage_relations": data.get("damage_relations", {})
    }
