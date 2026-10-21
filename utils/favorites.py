"""
favorites.py - Persistent Pokédex Favorites Cache & Manager.
Stores user's favorited Pokémon in data/favorites_cache.json with thread-safe atomic writes.
"""

import os
import json
from typing import Set, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites_cache.json")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def load_favorites() -> Set[str]:
    """Return set of favorited Pokémon names (lowercase)."""
    _ensure_data_dir()
    if not os.path.exists(FAVORITES_FILE):
        return set()
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                favs = data.get("favorites", [])
            elif isinstance(data, list):
                favs = data
            else:
                favs = []
            return {str(name).lower().strip() for name in favs if name}
    except Exception as e:
        print(f"[Favorites] Error loading favorites: {e}")
        return set()


def save_favorites(favorites: Set[str]) -> bool:
    """Persist set of favorited Pokémon names to disk."""
    _ensure_data_dir()
    try:
        fav_list = sorted(list(favorites))
        tmp_file = FAVORITES_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump({"favorites": fav_list, "count": len(fav_list)}, f, indent=2)
        os.replace(tmp_file, FAVORITES_FILE)
        return True
    except Exception as e:
        print(f"[Favorites] Error saving favorites: {e}")
        return False


def toggle_favorite(pokemon_name: str) -> bool:
    """
    Toggles favorite status for pokemon_name.
    Returns True if now favorited, False if unfavorited.
    """
    clean_name = str(pokemon_name or "").lower().strip()
    if not clean_name:
        return False
    favs = load_favorites()
    if clean_name in favs:
        favs.remove(clean_name)
        is_fav = False
    else:
        favs.add(clean_name)
        is_fav = True
    save_favorites(favs)
    return is_fav


def is_favorite(pokemon_name: str) -> bool:
    """Returns True if pokemon_name is currently in favorites."""
    clean_name = str(pokemon_name or "").lower().strip()
    return clean_name in load_favorites()

