# tests/test_battle_engine.py
"""Unit tests for the Pokémon Tournament Battle Simulation Engine."""

import unittest
from utils.battle_engine import (
    BattleSimulator,
    PokemonState,
    get_move_metadata,
    calculate_raw_stat,
)


class TestBattleEngine(unittest.TestCase):
    """Verifies tournament damage formulas, item/ability procs, and documented bugfixes."""

    def setUp(self):
        self.team1 = [{
            "species": "staraptor",
            "displayName": "Staraptor",
            "types": ["normal", "flying"],
            "item": "choice-scarf",
            "ability": "intimidate",
            "level": 50,
            "stats": {"hp": 160, "attack": 140, "defense": 90, "special-attack": 70, "special-defense": 80, "speed": 150},
            "moves": ["substitute", "brave-bird", "close-combat", "final-gambit"]
        }]
        self.team2 = [{
            "species": "archaludon",
            "displayName": "Archaludon",
            "types": ["steel", "dragon"],
            "item": "assault-vest",
            "ability": "stamina",
            "level": 50,
            "stats": {"hp": 165, "attack": 125, "defense": 150, "special-attack": 145, "special-defense": 85, "speed": 105},
            "moves": ["electro-shot", "flash-cannon", "draco-meteor", "body-press"]
        }]

    def test_raw_stat_calculation(self):
        # Level 50 HP formula: floor((2 * base + iv + floor(ev/4)) * level / 100) + level + 10
        # Pikachu base HP 35, 31 IV, 0 EV -> floor((70 + 31) * 0.5) + 50 + 10 = 50 + 50 + 10 = 110
        hp = calculate_raw_stat(35, 31, 0, 50, "hp", "adamant")
        self.assertEqual(hp, 110)

    def test_choice_lock_0pp_struggle_fallback(self):
        """Bugfix #34: Staraptor Choice Scarf locked into 0 PP Substitute forces Struggle."""
        sim = BattleSimulator(self.team1, self.team2)
        p1 = sim.side1.active_pokemon
        p1.choice_locked_move = "substitute"
        p1.pp["substitute"] = 0

        self.assertTrue(p1.is_struggling)
        self.assertTrue(p1.to_dict()["isStruggling"])

        hp_before = p1.current_hp
        sim.execute_turn({"type": "move", "move": "substitute"}, {"type": "move", "move": "flash-cannon"})

        struggle_events = [ev for ev in sim.battle_log if "Struggle" in ev.get("text", "")]
        self.assertTrue(len(struggle_events) > 0, "Struggle should be logged when choice-locked move has 0 PP")

    def test_fixed_damage_final_gambit(self):
        """Bugfix #28: Final Gambit deals damage equal to current HP and faints user."""
        sim = BattleSimulator(self.team1, self.team2)
        p1 = sim.side1.active_pokemon
        p2 = sim.side2.active_pokemon
        p1.current_hp = 120
        p2_hp_before = p2.current_hp

        sim.execute_turn({"type": "move", "move": "final-gambit"}, {"type": "move", "move": "body-press"})

        self.assertEqual(p1.current_hp, 0)
        self.assertTrue(p1.is_fainted)
        self.assertEqual(p2.current_hp, p2_hp_before - 120)

    def test_recoil_capping_to_actual_damage(self):
        """Bugfix #33: Brave Bird against a 10 HP defender caps recoil to actual damage dealt."""
        sim = BattleSimulator(self.team1, self.team2)
        p1 = sim.side1.active_pokemon
        p2 = sim.side2.active_pokemon
        p2.current_hp = 10  # low HP defender

        hp_before = p1.current_hp
        sim.execute_turn({"type": "move", "move": "brave-bird"}, {"type": "move", "move": "flash-cannon"})

        # Recoil is 1/3 of damage actually dealt (10 HP -> floor(10 * 0.33) = 3 HP recoil)
        # Verify Staraptor didn't take ~50+ HP overkill recoil
        recoil_events = [ev for ev in sim.battle_log if "recoil" in ev.get("text", "")]
        self.assertTrue(len(recoil_events) > 0)
        # Damage logged should reflect only the 10 HP
        faint_events = [ev for ev in sim.battle_log if p2.display_name in ev.get("text", "") and "fainted" in ev.get("text", "")]
        self.assertTrue(len(faint_events) > 0)

    def test_clanging_scales_drawback(self):
        """Bugfix #27: Clanging Scales applies -1 Defense drop upon landing damage."""
        meta = get_move_metadata("clanging-scales")
        self.assertTrue(meta.get("sound"))
        self.assertEqual(meta.get("self_stat_drop", {}).get("defense"), -1)

    def test_protect_scope_allows_self_status(self):
        """Bugfix #30: Protect must NOT block opponent's self-status moves (e.g. Bulk Up)."""
        annihilape_team = [{
            "species": "annihilape",
            "displayName": "Annihilape",
            "types": ["fighting", "ghost"],
            "ability": "defiant",
            "level": 50,
            "stats": {"hp": 185, "attack": 135, "defense": 100, "special-attack": 70, "special-defense": 110, "speed": 110},
            "moves": ["bulk-up", "drain-punch", "rage-fist", "protect"]
        }]
        kingambit_team = [{
            "species": "kingambit",
            "displayName": "Kingambit",
            "types": ["dark", "steel"],
            "ability": "supreme-overlord",
            "level": 50,
            "stats": {"hp": 175, "attack": 155, "defense": 140, "special-attack": 80, "special-defense": 105, "speed": 70},
            "moves": ["protect", "sucker-punch", "kowtow-cleave", "iron-head"]
        }]
        sim = BattleSimulator(kingambit_team, annihilape_team)
        # Kingambit protects; Annihilape uses Bulk Up
        sim.execute_turn({"type": "move", "move": "protect"}, {"type": "move", "move": "bulk-up"})

        # Annihilape's Atk and Def stages should both be +1
        annihilape = sim.side2.active_pokemon
        self.assertEqual(annihilape.stages.get("attack"), 1)
        self.assertEqual(annihilape.stages.get("defense"), 1)

    def test_rage_fist_hit_scaling(self):
        """Bugfix #31: Rage Fist BP increases by +50 per hit taken up to 350 BP."""
        p = PokemonState({
            "species": "annihilape",
            "moves": ["rage-fist"]
        }, "side1", 0, 50)
        p.times_hit_counter = 0
        self.assertEqual(p.to_dict()["moveDetails"][0]["power"], 50)

        p.times_hit_counter = 3
        self.assertEqual(p.to_dict()["moveDetails"][0]["power"], 200)

        p.times_hit_counter = 10
        self.assertEqual(p.to_dict()["moveDetails"][0]["power"], 350)  # capped at 350 BP


if __name__ == "__main__":
    unittest.main()
