"""
Storage manager for Teambuilder sample teams and competitive items cache.
Provides thread-safe atomic reading and writing to disk.
"""

import json
import os
import threading
from typing import Dict, List, Any, Set, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAMPLE_TEAMS_FILE = os.path.join(DATA_DIR, "sample_teams.json")
COMPETITIVE_ITEMS_FILE = os.path.join(DATA_DIR, "competitive_items.json")

_storage_lock = threading.Lock()

# --------------------------------------------------------------------------- #
# Default Initial Datasets
# --------------------------------------------------------------------------- #

DEFAULT_COMPETITIVE_ITEMS: List[Dict[str, Any]] = [
    # Choice Items
    {"name": "choice-scarf", "display_name": "Choice Scarf", "category": "Choice", "effect": "Boosts Speed by 50%, but locks into the first move used."},
    {"name": "choice-band", "display_name": "Choice Band", "category": "Choice", "effect": "Boosts Attack by 50%, but locks into the first move used."},
    {"name": "choice-specs", "display_name": "Choice Specs", "category": "Choice", "effect": "Boosts Sp. Atk by 50%, but locks into the first move used."},

    # Survival & Defense
    {"name": "focus-sash", "display_name": "Focus Sash", "category": "Defense", "effect": "Survives any single hit from full HP with at least 1 HP."},
    {"name": "assault-vest", "display_name": "Assault Vest", "category": "Defense", "effect": "Boosts Sp. Def by 50%, but prevents the use of status moves."},
    {"name": "eviolite", "display_name": "Eviolite", "category": "Defense", "effect": "Boosts Defense and Sp. Def by 50% for unevolved Pokémon."},
    {"name": "heavy-duty-boots", "display_name": "Heavy-Duty Boots", "category": "Defense", "effect": "Provides total immunity to entry hazard damage upon switching in."},
    {"name": "rocky-helmet", "display_name": "Rocky Helmet", "category": "Defense", "effect": "Damages the attacker for 1/6 max HP upon contact."},
    {"name": "covert-cloak", "display_name": "Covert Cloak", "category": "Defense", "effect": "Protects the holder from secondary effects of attacks (e.g. Fake Out flinch)."},
    {"name": "safety-goggles", "display_name": "Safety Goggles", "category": "Defense", "effect": "Grants immunity to powder moves (Spore, Rage Powder) and weather damage."},
    {"name": "clear-amulet", "display_name": "Clear Amulet", "category": "Defense", "effect": "Protects against all stat drops inflicted by opposing Pokémon (e.g. Intimidate)."},

    # Offensive Enhancements
    {"name": "life-orb", "display_name": "Life Orb", "category": "Offense", "effect": "Boosts attack damage by 30%, but takes 10% max HP recoil on each hit."},
    {"name": "booster-energy", "display_name": "Booster Energy", "category": "Offense", "effect": "Instantly activates Protosynthesis or Quark Drive to boost highest stat."},
    {"name": "loaded-dice", "display_name": "Loaded Dice", "category": "Offense", "effect": "Guarantees multi-hit attacks (Bullet Seed, Icicle Spear) hit 4 or 5 times."},
    {"name": "expert-belt", "display_name": "Expert Belt", "category": "Offense", "effect": "Boosts damage by 20% on super-effective attacks without recoil."},
    {"name": "weakness-policy", "display_name": "Weakness Policy", "category": "Offense", "effect": "Boosts Attack and Sp. Atk by +2 stages when struck by a super-effective move."},
    {"name": "light-clay", "display_name": "Light Clay", "category": "Support", "effect": "Extends barrier duration (Reflect, Light Screen, Aurora Veil) from 5 to 8 turns."},
    {"name": "terrain-extender", "display_name": "Terrain Extender", "category": "Support", "effect": "Extends terrain duration from 5 to 8 turns."},

    # Recovery & Berries
    {"name": "leftovers", "display_name": "Leftovers", "category": "Recovery", "effect": "Restores 1/16 of max HP at the conclusion of every turn."},
    {"name": "sitrus-berry", "display_name": "Sitrus Berry", "category": "Recovery", "effect": "Restores 25% of max HP when falling below 50% HP threshold."},
    {"name": "lum-berry", "display_name": "Lum Berry", "category": "Recovery", "effect": "Instantly cures any status condition (burn, paralysis, sleep, poison, freeze) once."},
    {"name": "mental-herb", "display_name": "Mental Herb", "category": "Recovery", "effect": "Removes Taunt, Encore, Torment, and infatuation effects once."},
    {"name": "white-herb", "display_name": "White Herb", "category": "Recovery", "effect": "Restores all lowered stat stages back to neutral once."},
    {"name": "aguav-berry", "display_name": "Aguav Berry", "category": "Recovery", "effect": "Restores 33% max HP when dropping below 25% HP."},
    {"name": "figy-berry", "display_name": "Figy Berry", "category": "Recovery", "effect": "Restores 33% max HP when dropping below 25% HP."},
    {"name": "iapapa-berry", "display_name": "Iapapa Berry", "category": "Recovery", "effect": "Restores 33% max HP when dropping below 25% HP."},
    {"name": "mago-berry", "display_name": "Mago Berry", "category": "Recovery", "effect": "Restores 33% max HP when dropping below 25% HP."},
    {"name": "wiki-berry", "display_name": "Wiki Berry", "category": "Recovery", "effect": "Restores 33% max HP when dropping below 25% HP."},

    # Type Enhancers
    {"name": "mystic-water", "display_name": "Mystic Water", "category": "Type Boost", "effect": "Boosts Water-type attack damage by 20%."},
    {"name": "miracle-seed", "display_name": "Miracle Seed", "category": "Type Boost", "effect": "Boosts Grass-type attack damage by 20%."},
    {"name": "charcoal", "display_name": "Charcoal", "category": "Type Boost", "effect": "Boosts Fire-type attack damage by 20%."},
    {"name": "black-glasses", "display_name": "Black Glasses", "category": "Type Boost", "effect": "Boosts Dark-type attack damage by 20%."},
    {"name": "magnet", "display_name": "Magnet", "category": "Type Boost", "effect": "Boosts Electric-type attack damage by 20%."},
    {"name": "soft-sand", "display_name": "Soft Sand", "category": "Type Boost", "effect": "Boosts Ground-type attack damage by 20%."},
    {"name": "hard-stone", "display_name": "Hard Stone", "category": "Type Boost", "effect": "Boosts Rock-type attack damage by 20%."},
    {"name": "spell-tag", "display_name": "Spell Tag", "category": "Type Boost", "effect": "Boosts Ghost-type attack damage by 20%."},
    {"name": "fairy-feather", "display_name": "Fairy Feather", "category": "Type Boost", "effect": "Boosts Fairy-type attack damage by 20%."},

    # Weather Rocks & Orbs
    {"name": "damp-rock", "display_name": "Damp Rock", "category": "Weather", "effect": "Extends Rain duration from 5 turns to 8 turns."},
    {"name": "heat-rock", "display_name": "Heat Rock", "category": "Weather", "effect": "Extends Sun duration from 5 turns to 8 turns."},
    {"name": "icy-rock", "display_name": "Icy Rock", "category": "Weather", "effect": "Extends Snow / Hail duration from 5 turns to 8 turns."},
    {"name": "smooth-rock", "display_name": "Smooth Rock", "category": "Weather", "effect": "Extends Sandstorm duration from 5 turns to 8 turns."},
    {"name": "flame-orb", "display_name": "Flame Orb", "category": "Orb", "effect": "Inflicts burn at the end of the turn (activates Guts & Flare Boost)."},
    {"name": "toxic-orb", "display_name": "Toxic Orb", "category": "Orb", "effect": "Badly poisons the holder at the end of the turn (activates Poison Heal & Guts)."},
    {"name": "power-herb", "display_name": "Power Herb", "category": "Offense", "effect": "Allows a two-turn attack (Meteor Beam, Solar Beam) to strike on turn one."},

    # Canonical Mega Stones (Required for Mega Evolution)
    {"name": "lucarionite", "display_name": "Lucarionite", "category": "Mega Stone", "effect": "Allows Lucario to Mega Evolve into Mega Lucario."},
    {"name": "lucarionite-z", "display_name": "Lucarionite Z", "category": "Mega Stone", "effect": "Allows Lucario to Mega Evolve into Mega Lucario Z."},
    {"name": "charizardite-x", "display_name": "Charizardite X", "category": "Mega Stone", "effect": "Allows Charizard to Mega Evolve into Mega Charizard X."},
    {"name": "charizardite-y", "display_name": "Charizardite Y", "category": "Mega Stone", "effect": "Allows Charizard to Mega Evolve into Mega Charizard Y."},
    {"name": "garchompite", "display_name": "Garchompite", "category": "Mega Stone", "effect": "Allows Garchomp to Mega Evolve into Mega Garchomp."},
    {"name": "garchompite-z", "display_name": "Garchompite Z", "category": "Mega Stone", "effect": "Allows Garchomp to Mega Evolve into Mega Garchomp Z."},
    {"name": "absolite", "display_name": "Absolite", "category": "Mega Stone", "effect": "Allows Absol to Mega Evolve into Mega Absol."},
    {"name": "absolite-z", "display_name": "Absolite Z", "category": "Mega Stone", "effect": "Allows Absol to Mega Evolve into Mega Absol Z."},
    {"name": "mewtwonite-x", "display_name": "Mewtwonite X", "category": "Mega Stone", "effect": "Allows Mewtwo to Mega Evolve into Mega Mewtwo X."},
    {"name": "mewtwonite-y", "display_name": "Mewtwonite Y", "category": "Mega Stone", "effect": "Allows Mewtwo to Mega Evolve into Mega Mewtwo Y."},
    {"name": "venusaurite", "display_name": "Venusaurite", "category": "Mega Stone", "effect": "Allows Venusaur to Mega Evolve into Mega Venusaur."},
    {"name": "blastoisinite", "display_name": "Blastoisinite", "category": "Mega Stone", "effect": "Allows Blastoise to Mega Evolve into Mega Blastoise."},
    {"name": "alakazite", "display_name": "Alakazite", "category": "Mega Stone", "effect": "Allows Alakazam to Mega Evolve into Mega Alakazam."},
    {"name": "gengarite", "display_name": "Gengarite", "category": "Mega Stone", "effect": "Allows Gengar to Mega Evolve into Mega Gengar."},
    {"name": "kangaskhanite", "display_name": "Kangaskhanite", "category": "Mega Stone", "effect": "Allows Kangaskhan to Mega Evolve into Mega Kangaskhan."},
    {"name": "pinsirite", "display_name": "Pinsirite", "category": "Mega Stone", "effect": "Allows Pinsir to Mega Evolve into Mega Pinsir."},
    {"name": "gyaradosite", "display_name": "Gyaradosite", "category": "Mega Stone", "effect": "Allows Gyarados to Mega Evolve into Mega Gyarados."},
    {"name": "aerodactylite", "display_name": "Aerodactylite", "category": "Mega Stone", "effect": "Allows Aerodactyl to Mega Evolve into Mega Aerodactyl."},
    {"name": "ampharosite", "display_name": "Ampharosite", "category": "Mega Stone", "effect": "Allows Ampharos to Mega Evolve into Mega Ampharos."},
    {"name": "steelixite", "display_name": "Steelixite", "category": "Mega Stone", "effect": "Allows Steelix to Mega Evolve into Mega Steelix."},
    {"name": "scizorite", "display_name": "Scizorite", "category": "Mega Stone", "effect": "Allows Scizor to Mega Evolve into Mega Scizor."},
    {"name": "heracronite", "display_name": "Heracronite", "category": "Mega Stone", "effect": "Allows Heracross to Mega Evolve into Mega Heracross."},
    {"name": "houndoominite", "display_name": "Houndoominite", "category": "Mega Stone", "effect": "Allows Houndoom to Mega Evolve into Mega Houndoom."},
    {"name": "tyranitarite", "display_name": "Tyranitarite", "category": "Mega Stone", "effect": "Allows Tyranitar to Mega Evolve into Mega Tyranitar."},
    {"name": "sceptilite", "display_name": "Sceptilite", "category": "Mega Stone", "effect": "Allows Sceptile to Mega Evolve into Mega Sceptile."},
    {"name": "blazikenite", "display_name": "Blazikenite", "category": "Mega Stone", "effect": "Allows Blaziken to Mega Evolve into Mega Blaziken."},
    {"name": "swampertite", "display_name": "Swampertite", "category": "Mega Stone", "effect": "Allows Swampert to Mega Evolve into Mega Swampert."},
    {"name": "gardevoirite", "display_name": "Gardevoirite", "category": "Mega Stone", "effect": "Allows Gardevoir to Mega Evolve into Mega Gardevoir."},
    {"name": "sablenite", "display_name": "Sablenite", "category": "Mega Stone", "effect": "Allows Sableye to Mega Evolve into Mega Sableye."},
    {"name": "mawilite", "display_name": "Mawilite", "category": "Mega Stone", "effect": "Allows Mawile to Mega Evolve into Mega Mawile."},
    {"name": "aggronite", "display_name": "Aggronite", "category": "Mega Stone", "effect": "Allows Aggron to Mega Evolve into Mega Aggron."},
    {"name": "medichamite", "display_name": "Medichamite", "category": "Mega Stone", "effect": "Allows Medicham to Mega Evolve into Mega Medicham."},
    {"name": "manectite", "display_name": "Manectite", "category": "Mega Stone", "effect": "Allows Manectric to Mega Evolve into Mega Manectric."},
    {"name": "sharpedonite", "display_name": "Sharpedonite", "category": "Mega Stone", "effect": "Allows Sharpedo to Mega Evolve into Mega Sharpedo."},
    {"name": "cameruptite", "display_name": "Cameruptite", "category": "Mega Stone", "effect": "Allows Camerupt to Mega Evolve into Mega Camerupt."},
    {"name": "altarianite", "display_name": "Altarianite", "category": "Mega Stone", "effect": "Allows Altaria to Mega Evolve into Mega Altaria."},
    {"name": "banettite", "display_name": "Banettite", "category": "Mega Stone", "effect": "Allows Banette to Mega Evolve into Mega Banette."},
    {"name": "salamencite", "display_name": "Salamencite", "category": "Mega Stone", "effect": "Allows Salamence to Mega Evolve into Mega Salamence."},
    {"name": "metagrossite", "display_name": "Metagrossite", "category": "Mega Stone", "effect": "Allows Metagross to Mega Evolve into Mega Metagross."},
    {"name": "latiasite", "display_name": "Latiasite", "category": "Mega Stone", "effect": "Allows Latias to Mega Evolve into Mega Latias."},
    {"name": "latiosite", "display_name": "Latiosite", "category": "Mega Stone", "effect": "Allows Latios to Mega Evolve into Mega Latios."},
    {"name": "lopunnite", "display_name": "Lopunnite", "category": "Mega Stone", "effect": "Allows Lopunny to Mega Evolve into Mega Lopunny."},
    {"name": "abomasite", "display_name": "Abomasite", "category": "Mega Stone", "effect": "Allows Abomasnow to Mega Evolve into Mega Abomasnow."},
    {"name": "galladite", "display_name": "Galladite", "category": "Mega Stone", "effect": "Allows Gallade to Mega Evolve into Mega Gallade."},
    {"name": "audinite", "display_name": "Audinite", "category": "Mega Stone", "effect": "Allows Audino to Mega Evolve into Mega Audino."},
    {"name": "diancite", "display_name": "Diancite", "category": "Mega Stone", "effect": "Allows Diancie to Mega Evolve into Mega Diancie."},
    {"name": "beedrillite", "display_name": "Beedrillite", "category": "Mega Stone", "effect": "Allows Beedrill to Mega Evolve into Mega Beedrill."},
    {"name": "pidgeotite", "display_name": "Pidgeotite", "category": "Mega Stone", "effect": "Allows Pidgeot to Mega Evolve into Mega Pidgeot."},
    {"name": "slowbronite", "display_name": "Slowbronite", "category": "Mega Stone", "effect": "Allows Slowbro to Mega Evolve into Mega Slowbro."},
    {"name": "glalitite", "display_name": "Glalitite", "category": "Mega Stone", "effect": "Allows Glalie to Mega Evolve into Mega Glalie."},
]

DEFAULT_SAMPLE_TEAMS: Dict[str, Any] = {
    # ------------------ DOUBLES / VGC CHAMPIONSHIPS ------------------ #
    "vgc-reg-h-balance": {
        "id": "vgc-reg-h-balance",
        "name": "🏆 VGC Reg H Championship Balance",
        "mode": "doubles",
        "archetype": "balance",
        "level": 50,
        "author": "Official Championship Meta",
        "description": "Premier tournament-winning balance core utilizing Intimidate, Grassy Surge, Stamina Archaludon, and high-impact pivot cycles.",
        "notes": {
            "leads": "Lead Incineroar + Rillaboom for double Fake Out, or Archaludon + Primarina against special cores.",
            "weather": "Archaludon turns Rain against opponents with Stamina + Electro Shot. Primarina handles Sun.",
            "tr": "Cycle Parting Shot and Fake Out to exhaust Trick Room turns safely.",
            "general": "Rotate Intimidate and Grassy Terrain recovery for sustained end-game positioning."
        },
        "members": [
            {
                "species": "incineroar",
                "displayName": "Incineroar",
                "item": "Sitrus Berry",
                "ability": "intimidate",
                "teraType": "ghost",
                "level": 50,
                "shiny": False,
                "nature": "Careful",
                "evs": { "hp": 252, "attack": 4, "defense": 156, "special-attack": 0, "special-defense": 96, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["fake-out", "knock-off", "parting-shot", "flare-blitz"],
                "types": ["fire", "dark"]
            },
            {
                "species": "rillaboom",
                "displayName": "Rillaboom",
                "item": "Assault Vest",
                "ability": "grassy-surge",
                "teraType": "fire",
                "level": 50,
                "shiny": False,
                "nature": "Adamant",
                "evs": { "hp": 252, "attack": 116, "defense": 4, "special-attack": 0, "special-defense": 100, "speed": 36 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["grassy-glide", "wood-hammer", "high-horsepower", "u-turn"],
                "types": ["grass"]
            },
            {
                "species": "primarina",
                "displayName": "Primarina",
                "item": "Life Orb",
                "ability": "liquid-voice",
                "teraType": "grass",
                "level": 50,
                "shiny": False,
                "nature": "Modest",
                "evs": { "hp": 252, "attack": 0, "defense": 100, "special-attack": 156, "special-defense": 0, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["hyper-voice", "moonblast", "haze", "protect"],
                "types": ["water", "fairy"]
            },
            {
                "species": "archaludon",
                "displayName": "Archaludon",
                "item": "Leftovers",
                "ability": "stamina",
                "teraType": "grass",
                "level": 50,
                "shiny": False,
                "nature": "Modest",
                "evs": { "hp": 252, "attack": 0, "defense": 4, "special-attack": 196, "special-defense": 52, "speed": 4 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["body-press", "flash-cannon", "draco-meteor", "protect"],
                "types": ["steel", "dragon"]
            },
            {
                "species": "garchomp",
                "displayName": "Garchomp",
                "item": "Clear Amulet",
                "ability": "rough-skin",
                "teraType": "steel",
                "level": 50,
                "shiny": False,
                "nature": "Jolly",
                "evs": { "hp": 4, "attack": 252, "defense": 0, "special-attack": 0, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["earthquake", "dragon-claw", "swords-dance", "protect"],
                "types": ["dragon", "ground"]
            },
            {
                "species": "gholdengo",
                "displayName": "Gholdengo",
                "item": "Choice Specs",
                "ability": "good-as-gold",
                "teraType": "steel",
                "level": 50,
                "shiny": False,
                "nature": "Modest",
                "evs": { "hp": 196, "attack": 0, "defense": 4, "special-attack": 156, "special-defense": 4, "speed": 148 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["make-it-rain", "shadow-ball", "thunderbolt", "trick"],
                "types": ["steel", "ghost"]
            }
        ]
    },

    "vgc-rain-offense": {
        "id": "vgc-rain-offense",
        "name": "🌧️ VGC Pelipper Rain & Swift Swim",
        "mode": "doubles",
        "archetype": "weather",
        "level": 50,
        "author": "Pikalytics Top Meta",
        "description": "Devastating weather squad featuring Drizzle Pelipper, Swift Swim Barraskewda/Palafin, and Stamina Archaludon Electro Shot.",
        "notes": {
            "leads": "Lead Pelipper + Archaludon for instant turn-1 Electro Shot or Pelipper + Urshifu for immense pressure.",
            "weather": "Preserve Pelipper in the back to reclaim Rain against Sun/Snow teams.",
            "tr": "Amoonguss Spore thrives under Trick Room against slow teams.",
            "general": "Surging Strikes ignores Protect and deals 50% boosted damage in Rain."
        },
        "members": [
            {
                "species": "pelipper",
                "displayName": "Pelipper",
                "item": "Focus Sash",
                "ability": "drizzle",
                "teraType": "ghost",
                "level": 50,
                "shiny": False,
                "nature": "Modest",
                "evs": { "hp": 4, "attack": 0, "defense": 0, "special-attack": 252, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["weather-ball", "hurricane", "tailwind", "protect"],
                "types": ["water", "flying"]
            },
            {
                "species": "archaludon",
                "displayName": "Archaludon",
                "item": "Assault Vest",
                "ability": "stamina",
                "teraType": "grass",
                "level": 50,
                "shiny": False,
                "nature": "Modest",
                "evs": { "hp": 196, "attack": 0, "defense": 4, "special-attack": 196, "special-defense": 60, "speed": 52 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["electro-shot", "draco-meteor", "flash-cannon", "body-press"],
                "types": ["steel", "dragon"]
            },
            {
                "species": "urshifu-rapid-strike",
                "displayName": "Urshifu-Rapid-Strike",
                "item": "Mystic Water",
                "ability": "unseen-fist",
                "teraType": "water",
                "level": 50,
                "shiny": False,
                "nature": "Adamant",
                "evs": { "hp": 4, "attack": 252, "defense": 0, "special-attack": 0, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["surging-strikes", "close-combat", "aqua-jet", "detect"],
                "types": ["fighting", "water"]
            },
            {
                "species": "amoonguss",
                "displayName": "Amoonguss",
                "item": "Rocky Helmet",
                "ability": "regenerator",
                "teraType": "water",
                "level": 50,
                "shiny": False,
                "nature": "Relaxed",
                "evs": { "hp": 236, "attack": 0, "defense": 156, "special-attack": 0, "special-defense": 116, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["spore", "rage-powder", "pollen-puff", "protect"],
                "types": ["grass", "poison"]
            },
            {
                "species": "rillaboom",
                "displayName": "Rillaboom",
                "item": "Miracle Seed",
                "ability": "grassy-surge",
                "teraType": "fire",
                "level": 50,
                "shiny": False,
                "nature": "Adamant",
                "evs": { "hp": 252, "attack": 196, "defense": 20, "special-attack": 0, "special-defense": 36, "speed": 4 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["fake-out", "grassy-glide", "wood-hammer", "u-turn"],
                "types": ["grass"]
            },
            {
                "species": "palafin",
                "displayName": "Palafin",
                "item": "Choice Band",
                "ability": "zero-to-hero",
                "teraType": "water",
                "level": 50,
                "shiny": False,
                "nature": "Adamant",
                "evs": { "hp": 252, "attack": 252, "defense": 4, "special-attack": 0, "special-defense": 0, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["wave-crash", "jet-punch", "close-combat", "flip-turn"],
                "types": ["water"]
            }
        ]
    },

    "vgc-hard-trick-room": {
        "id": "vgc-hard-trick-room",
        "name": "🌀 VGC Hard Trick Room & Psyspam",
        "mode": "doubles",
        "archetype": "trick-room",
        "level": 50,
        "author": "Championship VGC Archetype",
        "description": "Psychic Surge prevents priority moves while Armarouge Expanding Force sweeps, backed by Bloodmoon Ursaluna.",
        "notes": {
            "leads": "Indeedee-F + Armarouge or Indeedee-F + Porygon2 to guarantee Trick Room setup.",
            "weather": "Torkoal clears Sun and fires devastating Eruptions under Trick Room.",
            "tr": "Keep Trick Room up; Bloodmoon Ursaluna outspeeds and OHKOs fast sweepers.",
            "general": "Psychic Terrain shuts down opposing Fake Out, Sucker Punch, and Grassy Glide."
        },
        "members": [
            {
                "species": "indeedee-female",
                "displayName": "Indeedee-F",
                "item": "Psychic Seed",
                "ability": "psychic-surge",
                "teraType": "fairy",
                "level": 50,
                "shiny": False,
                "nature": "Relaxed",
                "evs": { "hp": 252, "attack": 0, "defense": 252, "special-attack": 0, "special-defense": 4, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["follow-me", "trick-room", "helping-hand", "dazzling-gleam"],
                "types": ["psychic", "normal"]
            },
            {
                "species": "armarouge",
                "displayName": "Armarouge",
                "item": "Life Orb",
                "ability": "flash-fire",
                "teraType": "psychic",
                "level": 50,
                "shiny": False,
                "nature": "Quiet",
                "evs": { "hp": 252, "attack": 0, "defense": 4, "special-attack": 252, "special-defense": 0, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["expanding-force", "armor-cannon", "wide-guard", "trick-room"],
                "types": ["fire", "psychic"]
            },
            {
                "species": "ursaluna-bloodmoon",
                "displayName": "Ursaluna-Bloodmoon",
                "item": "Silk Scarf",
                "ability": "mind-eye",
                "teraType": "normal",
                "level": 50,
                "shiny": False,
                "nature": "Quiet",
                "evs": { "hp": 244, "attack": 0, "defense": 12, "special-attack": 252, "special-defense": 0, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["blood-moon", "hyper-voice", "earth-power", "protect"],
                "types": ["ground", "normal"]
            },
            {
                "species": "torkoal",
                "displayName": "Torkoal",
                "item": "Charcoal",
                "ability": "drought",
                "teraType": "fire",
                "level": 50,
                "shiny": False,
                "nature": "Quiet",
                "evs": { "hp": 252, "attack": 0, "defense": 0, "special-attack": 252, "special-defense": 4, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["eruption", "heat-wave", "solar-beam", "protect"],
                "types": ["fire"]
            },
            {
                "species": "porygon2",
                "displayName": "Porygon2",
                "item": "Eviolite",
                "ability": "download",
                "teraType": "ghost",
                "level": 50,
                "shiny": False,
                "nature": "Sassy",
                "evs": { "hp": 244, "attack": 0, "defense": 100, "special-attack": 12, "special-defense": 148, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["trick-room", "recover", "ice-beam", "tri-attack"],
                "types": ["normal"]
            },
            {
                "species": "kingambit",
                "displayName": "Kingambit",
                "item": "Black Glasses",
                "ability": "defiant",
                "teraType": "flying",
                "level": 50,
                "shiny": False,
                "nature": "Brave",
                "evs": { "hp": 252, "attack": 252, "defense": 4, "special-attack": 0, "special-defense": 0, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["kowtow-cleave", "sucker-punch", "iron-head", "protect"],
                "types": ["dark", "steel"]
            }
        ]
    },

    "vgc-sun-hyper-offense": {
        "id": "vgc-sun-hyper-offense",
        "name": "☀️ VGC Sun & Protosynthesis Hyper Offense",
        "mode": "doubles",
        "archetype": "weather",
        "level": 50,
        "author": "VGC Regional Meta",
        "description": "High-octane sun offense pairing Drought Torkoal and Chi-Yu Beads of Ruin with Flutter Mane and Roaring Moon.",
        "notes": {
            "leads": "Lead Flutter Mane + Chi-Yu for immediate overwhelming special damage, or Torkoal + Roaring Moon.",
            "weather": "Sun gives Roaring Moon and Flutter Mane +30% stats without needing Booster Energy.",
            "tr": "Torkoal acts as an anti-Trick Room emergency nuke with base 20 speed Eruption.",
            "general": "Hearthflame Ogerpon under Sun with Embody Aspect deals game-ending physical damage."
        },
        "members": [
            {
                "species": "flutter-mane",
                "displayName": "Flutter Mane",
                "item": "Focus Sash",
                "ability": "protosynthesis",
                "teraType": "fairy",
                "level": 50,
                "shiny": False,
                "nature": "Timid",
                "evs": { "hp": 4, "attack": 0, "defense": 0, "special-attack": 252, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["moonblast", "shadow-ball", "dazzling-gleam", "protect"],
                "types": ["ghost", "fairy"]
            },
            {
                "species": "chi-yu",
                "displayName": "Chi-Yu",
                "item": "Choice Scarf",
                "ability": "beads-of-ruin",
                "teraType": "ghost",
                "level": 50,
                "shiny": False,
                "nature": "Modest",
                "evs": { "hp": 4, "attack": 0, "defense": 0, "special-attack": 252, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["heat-wave", "dark-pulse", "overheat", "snarl"],
                "types": ["dark", "fire"]
            },
            {
                "species": "torkoal",
                "displayName": "Torkoal",
                "item": "Sitrus Berry",
                "ability": "drought",
                "teraType": "grass",
                "level": 50,
                "shiny": False,
                "nature": "Quiet",
                "evs": { "hp": 252, "attack": 0, "defense": 0, "special-attack": 252, "special-defense": 4, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 0 },
                "moves": ["eruption", "heat-wave", "solar-beam", "protect"],
                "types": ["fire"]
            },
            {
                "species": "roaring-moon",
                "displayName": "Roaring Moon",
                "item": "Booster Energy",
                "ability": "protosynthesis",
                "teraType": "flying",
                "level": 50,
                "shiny": False,
                "nature": "Jolly",
                "evs": { "hp": 0, "attack": 252, "defense": 4, "special-attack": 0, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["acrobatics", "knock-off", "tailwind", "protect"],
                "types": ["dragon", "dark"]
            },
            {
                "species": "raging-bolt",
                "displayName": "Raging Bolt",
                "item": "Assault Vest",
                "ability": "protosynthesis",
                "teraType": "electric",
                "level": 50,
                "shiny": False,
                "nature": "Modest",
                "evs": { "hp": 188, "attack": 0, "defense": 84, "special-attack": 196, "special-defense": 36, "speed": 4 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["thunderclap", "dragon-pulse", "electroweb", "snarl"],
                "types": ["electric", "dragon"]
            },
            {
                "species": "ogerpon-hearthflame",
                "displayName": "Ogerpon-Hearthflame",
                "item": "Hearthflame Mask",
                "ability": "mold-breaker",
                "teraType": "fire",
                "level": 50,
                "shiny": False,
                "nature": "Jolly",
                "evs": { "hp": 4, "attack": 252, "defense": 0, "special-attack": 0, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["ivy-cudgel", "horn-leech", "spiky-shield", "follow-me"],
                "types": ["grass", "fire"]
            }
        ]
    },

    # ------------------ SINGLES (SMOGON OU / 6v6) ------------------ #
    "singles-ou-hyper-offense": {
        "id": "singles-ou-hyper-offense",
        "name": "⚡ Smogon OU Hyper Offense",
        "mode": "singles",
        "archetype": "hyper-offense",
        "level": 100,
        "author": "Smogon OU Sample Archive",
        "description": "Blistering Singles hyper offense using Deoxys-S hazards to set up sweeps for Iron Valiant and Supreme Overlord Kingambit.",
        "notes": {
            "leads": "Lead Deoxys-Speed for guaranteed Stealth Rock and Spikes, Taunt opposing hazard setters.",
            "weather": "Gouging Fire DDance in Sun or neutral sweeps opposing balance cores.",
            "tr": "Kingambit Sucker Punch bypasses Trick Room priority.",
            "general": "Keep pressure high; Iron Valiant Booster Energy cleans late game."
        },
        "members": [
            {
                "species": "deoxys-speed",
                "displayName": "Deoxys-Speed",
                "item": "Focus Sash",
                "ability": "pressure",
                "teraType": "ghost",
                "level": 100,
                "shiny": False,
                "nature": "Timid",
                "evs": { "hp": 252, "attack": 0, "defense": 0, "special-attack": 4, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["stealth-rock", "spikes", "taunt", "psycho-boost"],
                "types": ["psychic"]
            },
            {
                "species": "kingambit",
                "displayName": "Kingambit",
                "item": "Black Glasses",
                "ability": "supreme-overlord",
                "teraType": "dark",
                "level": 100,
                "shiny": False,
                "nature": "Adamant",
                "evs": { "hp": 112, "attack": 252, "defense": 0, "special-attack": 0, "special-defense": 0, "speed": 144 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["swords-dance", "sucker-punch", "kowtow-cleave", "iron-head"],
                "types": ["dark", "steel"]
            },
            {
                "species": "iron-valiant",
                "displayName": "Iron Valiant",
                "item": "Booster Energy",
                "ability": "quark-drive",
                "teraType": "fairy",
                "level": 100,
                "shiny": False,
                "nature": "Timid",
                "evs": { "hp": 0, "attack": 0, "defense": 4, "special-attack": 252, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["moonblast", "close-combat", "encore", "thunderbolt"],
                "types": ["fairy", "fighting"]
            },
            {
                "species": "gouging-fire",
                "displayName": "Gouging Fire",
                "item": "Booster Energy",
                "ability": "protosynthesis",
                "teraType": "flying",
                "level": 100,
                "shiny": False,
                "nature": "Adamant",
                "evs": { "hp": 44, "attack": 252, "defense": 0, "special-attack": 0, "special-defense": 0, "speed": 212 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["dragon-dance", "heat-crash", "earthquake", "dragon-claw"],
                "types": ["fire", "dragon"]
            },
            {
                "species": "great-tusk",
                "displayName": "Great Tusk",
                "item": "Booster Energy",
                "ability": "protosynthesis",
                "teraType": "ice",
                "level": 100,
                "shiny": False,
                "nature": "Jolly",
                "evs": { "hp": 0, "attack": 252, "defense": 4, "special-attack": 0, "special-defense": 0, "speed": 252 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["headlong-rush", "close-combat", "ice-spinner", "rapid-spin"],
                "types": ["ground", "fighting"]
            },
            {
                "species": "dragonite",
                "displayName": "Dragonite",
                "item": "Loaded Dice",
                "ability": "multiscale",
                "teraType": "normal",
                "level": 100,
                "shiny": False,
                "nature": "Adamant",
                "evs": { "hp": 144, "attack": 252, "defense": 0, "special-attack": 0, "special-defense": 0, "speed": 112 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["dragon-dance", "extreme-speed", "scale-shot", "earthquake"],
                "types": ["dragon", "flying"]
            }
        ]
    },

    "singles-ou-bulky-balance": {
        "id": "singles-ou-bulky-balance",
        "name": "🛡️ Smogon OU Bulky Balance",
        "mode": "singles",
        "archetype": "balance",
        "level": 100,
        "author": "Smogon OU Meta",
        "description": "Rock-solid singles balance team with Great Tusk hazard removal, Ting-Lu special bulk, Gliscor Toxic stall, and Dragapult pivot.",
        "notes": {
            "leads": "Lead Ting-Lu to set Spikes, or Dragapult to U-turn into favorable matchup.",
            "weather": "Gliscor and Ting-Lu sponge hits easily from weather teams.",
            "tr": "Ting-Lu and Gliscor stall out Trick Room with Protect and Whirlwind.",
            "general": "Keep Gholdengo healthy to block opposing Rapid Spin and Defog attempts."
        },
        "members": [
            {
                "species": "great-tusk",
                "displayName": "Great Tusk",
                "item": "Leftovers",
                "ability": "protosynthesis",
                "teraType": "water",
                "level": 100,
                "shiny": False,
                "nature": "Impish",
                "evs": { "hp": 252, "attack": 0, "defense": 240, "special-attack": 0, "special-defense": 0, "speed": 16 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["earthquake", "rapid-spin", "stealth-rock", "knock-off"],
                "types": ["ground", "fighting"]
            },
            {
                "species": "ting-lu",
                "displayName": "Ting-Lu",
                "item": "Leftovers",
                "ability": "vessel-of-ruin",
                "teraType": "poison",
                "level": 100,
                "shiny": False,
                "nature": "Careful",
                "evs": { "hp": 252, "attack": 4, "defense": 0, "special-attack": 0, "special-defense": 252, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["spikes", "ruination", "earthquake", "whirlwind"],
                "types": ["dark", "ground"]
            },
            {
                "species": "gholdengo",
                "displayName": "Gholdengo",
                "item": "Air Balloon",
                "ability": "good-as-gold",
                "teraType": "fighting",
                "level": 100,
                "shiny": False,
                "nature": "Timid",
                "evs": { "hp": 0, "attack": 0, "defense": 0, "special-attack": 252, "special-defense": 4, "speed": 252 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["nasty-plot", "shadow-ball", "make-it-rain", "focus-blast"],
                "types": ["steel", "ghost"]
            },
            {
                "species": "gliscor",
                "displayName": "Gliscor",
                "item": "Toxic Orb",
                "ability": "poison-heal",
                "teraType": "water",
                "level": 100,
                "shiny": False,
                "nature": "Careful",
                "evs": { "hp": 244, "attack": 0, "defense": 244, "special-attack": 0, "special-defense": 20, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["earthquake", "toxic", "spikes", "protect"],
                "types": ["ground", "flying"]
            },
            {
                "species": "dragapult",
                "displayName": "Dragapult",
                "item": "Choice Specs",
                "ability": "infiltrator",
                "teraType": "ghost",
                "level": 100,
                "shiny": False,
                "nature": "Timid",
                "evs": { "hp": 0, "attack": 0, "defense": 0, "special-attack": 252, "special-defense": 4, "speed": 252 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["shadow-ball", "draco-meteor", "u-turn", "flamethrower"],
                "types": ["dragon", "ghost"]
            },
            {
                "species": "clefable",
                "displayName": "Clefable",
                "item": "Leftovers",
                "ability": "magic-guard",
                "teraType": "steel",
                "level": 100,
                "shiny": False,
                "nature": "Bold",
                "evs": { "hp": 252, "attack": 0, "defense": 252, "special-attack": 0, "special-defense": 4, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["moonblast", "soft-boiled", "calm-mind", "stealth-rock"],
                "types": ["fairy"]
            }
        ]
    },

    "singles-stall-fat": {
        "id": "singles-stall-fat",
        "name": "🧱 Smogon OU Unaware Stall Fortress",
        "mode": "singles",
        "archetype": "stall",
        "level": 100,
        "author": "Smogon OU Stall Specialists",
        "description": "Classic impenetrable stall team: dual Unaware walls (Dondozo & Clodsire) ignore enemy stat boosts, supported by Blissey and Corviknight.",
        "notes": {
            "leads": "Lead Corviknight or Ting-Lu to scout and absorb incoming attacks.",
            "weather": "Dondozo handles Rain effortlessly; Clodsire walls Sun sweepers.",
            "tr": "Stall teams naturally outlast Trick Room through Recover cycles.",
            "general": "Never let Clodsire or Dondozo take unnecessary chip before setup threats are removed."
        },
        "members": [
            {
                "species": "dondozo",
                "displayName": "Dondozo",
                "item": "Heavy-Duty Boots",
                "ability": "unaware",
                "teraType": "fighting",
                "level": 100,
                "shiny": False,
                "nature": "Impish",
                "evs": { "hp": 252, "attack": 0, "defense": 252, "special-attack": 0, "special-defense": 4, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["liquidation", "rest", "sleep-talk", "body-press"],
                "types": ["water"]
            },
            {
                "species": "blissey",
                "displayName": "Blissey",
                "item": "Heavy-Duty Boots",
                "ability": "natural-cure",
                "teraType": "ghost",
                "level": 100,
                "shiny": False,
                "nature": "Calm",
                "evs": { "hp": 4, "attack": 0, "defense": 252, "special-attack": 0, "special-defense": 252, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["soft-boiled", "seismic-toss", "stealth-rock", "shadow-ball"],
                "types": ["normal"]
            },
            {
                "species": "clodsire",
                "displayName": "Clodsire",
                "item": "Heavy-Duty Boots",
                "ability": "unaware",
                "teraType": "dark",
                "level": 100,
                "shiny": False,
                "nature": "Careful",
                "evs": { "hp": 248, "attack": 0, "defense": 8, "special-attack": 0, "special-defense": 252, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["earthquake", "recover", "toxic", "spikes"],
                "types": ["poison", "ground"]
            },
            {
                "species": "corviknight",
                "displayName": "Corviknight",
                "item": "Leftovers",
                "ability": "pressure",
                "teraType": "dragon",
                "level": 100,
                "shiny": False,
                "nature": "Impish",
                "evs": { "hp": 252, "attack": 0, "defense": 252, "special-attack": 0, "special-defense": 4, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["roost", "defog", "brave-bird", "u-turn"],
                "types": ["steel", "flying"]
            },
            {
                "species": "toxapex",
                "displayName": "Toxapex",
                "item": "Heavy-Duty Boots",
                "ability": "regenerator",
                "teraType": "fairy",
                "level": 100,
                "shiny": False,
                "nature": "Bold",
                "evs": { "hp": 252, "attack": 0, "defense": 192, "special-attack": 0, "special-defense": 64, "speed": 0 },
                "ivs": { "hp": 31, "attack": 0, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["scald", "recover", "haze", "toxic-spikes"],
                "types": ["poison", "water"]
            },
            {
                "species": "ting-lu",
                "displayName": "Ting-Lu",
                "item": "Leftovers",
                "ability": "vessel-of-ruin",
                "teraType": "poison",
                "level": 100,
                "shiny": False,
                "nature": "Careful",
                "evs": { "hp": 252, "attack": 4, "defense": 0, "special-attack": 0, "special-defense": 252, "speed": 0 },
                "ivs": { "hp": 31, "attack": 31, "defense": 31, "special-attack": 31, "special-defense": 31, "speed": 31 },
                "moves": ["spikes", "ruination", "earthquake", "whirlwind"],
                "types": ["dark", "ground"]
            }
        ]
    }
}

# --------------------------------------------------------------------------- #
# Public Storage Functions
# --------------------------------------------------------------------------- #

def sync_competitive_items_with_mega_stones(items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], bool]:
    """
    Dynamically syncs competitive items with all Mega Stones discovered in mega_stones_cache.
    Ensures every Mega Stone is present with category 'Mega Stone', humanized display name,
    and battle effect description.
    """
    from utils.naming import humanize_name
    from utils.cache import get_mega_stone_map

    mega_map = get_mega_stone_map()
    existing_names = {x.get("name") for x in items if isinstance(x, dict)}
    changed = False

    for species, stones in mega_map.items():
        for stone_name, target_mega in stones.items():
            # Avoid redundant undashed aliases like 'lucarionitez', 'charizarditex' in the item selector
            if stone_name.endswith(("itex", "itey", "itez")):
                continue
            if "-" in stone_name and not stone_name.endswith(("-x", "-y", "-z")):
                continue
            if stone_name in existing_names:
                continue

            disp_name = humanize_name(stone_name)
            mega_disp = humanize_name(target_mega)
            sp_disp = humanize_name(species)
            effect_str = f"Enables {sp_disp} to Mega Evolve during battle into {mega_disp}."

            items.append({
                "name": stone_name,
                "display_name": disp_name,
                "category": "Mega Stone",
                "effect": effect_str
            })
            existing_names.add(stone_name)
            changed = True

    return items, changed


def get_competitive_items() -> List[Dict[str, Any]]:
    """Return all cached competitive items, dynamically synced with Mega Stones."""
    with _storage_lock:
        items = get_competitive_items_internal()
        items, changed = sync_competitive_items_with_mega_stones(items)
        if changed or not os.path.exists(COMPETITIVE_ITEMS_FILE):
            save_competitive_items_internal(items)
        return items


def save_competitive_item(item_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Add or update an item in the competitive items cache."""
    with _storage_lock:
        items = get_competitive_items_internal()
        name = str(item_dict.get("name", "")).strip().lower().replace(" ", "-")
        display_name = item_dict.get("display_name") or name.replace("-", " ").title()
        category = item_dict.get("category") or "General"
        effect = item_dict.get("effect") or ""

        # Update if exists, or append
        existing_idx = next((i for i, x in enumerate(items) if x.get("name") == name), -1)
        item_obj = {
            "name": name,
            "display_name": display_name,
            "category": category,
            "effect": effect
        }
        if existing_idx != -1:
            items[existing_idx] = item_obj
        else:
            items.append(item_obj)

        save_competitive_items_internal(items)
        return items


def delete_competitive_item(name: str) -> List[Dict[str, Any]]:
    """Delete an item from the competitive items cache."""
    name = str(name).strip().lower()
    with _storage_lock:
        items = get_competitive_items_internal()
        items = [x for x in items if x.get("name") != name]
        save_competitive_items_internal(items)
        return items


def get_sample_teams() -> Dict[str, Any]:
    """Return all cached sample teams, initializing disk file if missing."""
    with _storage_lock:
        if os.path.exists(SAMPLE_TEAMS_FILE):
            try:
                with open(SAMPLE_TEAMS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and len(data) > 0:
                        return data
            except Exception:
                pass

        # Initialize disk with defaults
        save_sample_teams_internal(DEFAULT_SAMPLE_TEAMS)
        return dict(DEFAULT_SAMPLE_TEAMS)


def save_sample_team(team_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add or update a sample team in the cache."""
    with _storage_lock:
        teams = get_sample_teams_internal()
        team_id = team_dict.get("id") or ("team_" + str(int(os.times().elapsed * 1000)))
        team_dict["id"] = team_id
        teams[team_id] = team_dict
        save_sample_teams_internal(teams)
        return teams


def delete_sample_team(team_id: str) -> Dict[str, Any]:
    """Delete a sample team from the cache."""
    with _storage_lock:
        teams = get_sample_teams_internal()
        if team_id in teams:
            del teams[team_id]
            save_sample_teams_internal(teams)
        return teams


# --------------------------------------------------------------------------- #
# Internal Helpers (Must be called within _storage_lock)
# --------------------------------------------------------------------------- #

def get_competitive_items_internal() -> List[Dict[str, Any]]:
    """Internal reader loading competitive items from disk or falling back to defaults."""
    if os.path.exists(COMPETITIVE_ITEMS_FILE):
        try:
            with open(COMPETITIVE_ITEMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return list(DEFAULT_COMPETITIVE_ITEMS)


def save_competitive_items_internal(items: List[Dict[str, Any]]) -> None:
    """Internal writer persisting competitive items to disk atomically."""
    tmp_path = COMPETITIVE_ITEMS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, COMPETITIVE_ITEMS_FILE)


def get_sample_teams_internal() -> Dict[str, Any]:
    """Internal reader loading pre-loaded competitive sample teams from disk."""
    if os.path.exists(SAMPLE_TEAMS_FILE):
        try:
            with open(SAMPLE_TEAMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_SAMPLE_TEAMS)


def save_sample_teams_internal(teams: Dict[str, Any]) -> None:
    """Internal writer persisting competitive sample teams to disk atomically."""
    tmp_path = SAMPLE_TEAMS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(teams, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, SAMPLE_TEAMS_FILE)


# --------------------------------------------------------------------------- #
# Dynamic Legality Registry
# --------------------------------------------------------------------------- #

_CHAMPIONS_LEGAL_CACHE = None

CHAMPIONS_ROSTER_FILE = os.path.join(DATA_DIR, "champions_roster.json")

def load_champions_roster() -> Set[str]:
    """Loads the cached Pokémon Champions roster (scraped from Serebii)."""
    if os.path.exists(CHAMPIONS_ROSTER_FILE):
        try:
            with open(CHAMPIONS_ROSTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(x.lower().strip() for x in data if x)
        except Exception:
            pass
    return set()

CHAMPIONS_ROSTER: Set[str] = load_champions_roster()

from utils.special_pokemon import RESTRICTED_LEGENDS, SUB_LEGENDS, MYTHICALS, ULTRA_BEASTS, PARADOX
BANNED_CHAMPIONS = RESTRICTED_LEGENDS | SUB_LEGENDS | MYTHICALS | ULTRA_BEASTS | PARADOX

def is_champions_banned(name: str) -> bool:
    """
    Return True if species is NOT in the official Pokémon Champions roster.
    Champions uses a specific confirmed roster (from Serebii) rather than blanket legendary bans,
    permitting species like Archaludon and others currently confirmed for the game.
    """
    clean = str(name or "").lower().strip()
    base = clean.split("-")[0]
    roster = CHAMPIONS_ROSTER or load_champions_roster()
    if roster:
        if clean in roster or base in roster:
            return False
        for r in roster:
            if clean == r or clean.startswith(f"{r}-"):
                return False
        return True
    return base in BANNED_CHAMPIONS or clean in BANNED_CHAMPIONS

def clear_champions_legal_cache():
    """Clear in-memory cache of legal champions pokemon."""
    global _CHAMPIONS_LEGAL_CACHE
    _CHAMPIONS_LEGAL_CACHE = None


def get_legal_pokemon_list(rule: str = "champions", all_names_fn=None, poke_cache_fn=None) -> List[Dict[str, str]]:
    """Return legal Pokémon list for given rule ('champions' vs 'smogon')."""
    from utils.naming import humanize_name
    global _CHAMPIONS_LEGAL_CACHE

    if rule == "smogon":
        if all_names_fn:
            names = all_names_fn()
        else:
            names = []
        return [{"name": n, "displayName": humanize_name(n)} for n in names]

    if _CHAMPIONS_LEGAL_CACHE is not None:
        return _CHAMPIONS_LEGAL_CACHE

    res = []
    names = all_names_fn() if all_names_fn else (list(poke_cache_fn().keys()) if poke_cache_fn else [])

    # Filter out cosmetic / non-competitive variants
    banned_suffixes = ("-totem", "-cap", "-starter", "-cosplay", "-libre", "-pop-star", "-phd", "-belle", "-rock-star")

    for name in names:
        if any(name.endswith(sfx) or f"{sfx}-" in name for sfx in banned_suffixes):
            continue
        if is_champions_banned(name):
            continue
        res.append({"name": name, "displayName": humanize_name(name)})

    # Sort alphabetically by displayName
    res.sort(key=lambda x: x["displayName"])
    _CHAMPIONS_LEGAL_CACHE = res
    return res

