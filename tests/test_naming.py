# tests/test_naming.py
"""Unit tests for naming and humanization utilities with LRU caching."""

import unittest
from utils.naming import humanize_name, capitalize_word


class TestNaming(unittest.TestCase):
    """Verifies canonical Camel Case formatting and special edge case mapping."""

    def test_exact_matches(self):
        self.assertEqual(humanize_name("ho-oh"), "Ho-Oh")
        self.assertEqual(humanize_name("porygon-z"), "Porygon-Z")
        self.assertEqual(humanize_name("type-null"), "Type: Null")
        self.assertEqual(humanize_name("ting-lu"), "Ting-Lu")
        self.assertEqual(humanize_name("chien-pao"), "Chien-Pao")
        self.assertEqual(humanize_name("farfetchd"), "Farfetch'd")

    def test_mega_and_gmax(self):
        self.assertEqual(humanize_name("charizard-mega-x"), "Mega Charizard X")
        self.assertEqual(humanize_name("charizard-mega-y"), "Mega Charizard Y")
        self.assertEqual(humanize_name("mewtwo-mega-x"), "Mega Mewtwo X")
        self.assertEqual(humanize_name("lucario-mega"), "Mega Lucario")
        self.assertEqual(humanize_name("gengar-gmax"), "Gigantamax Gengar")

    def test_regional_forms(self):
        self.assertEqual(humanize_name("raichu-alola"), "Raichu (Alola)")
        self.assertEqual(humanize_name("weezing-galar"), "Weezing (Galar)")
        self.assertEqual(humanize_name("arcanine-hisui"), "Arcanine (Hisui)")
        self.assertEqual(humanize_name("wooper-paldea"), "Wooper (Paldea)")

    def test_paradox_pokemon(self):
        self.assertEqual(humanize_name("iron-valiant"), "Iron Valiant")
        self.assertEqual(humanize_name("flutter-mane"), "Flutter Mane")
        self.assertEqual(humanize_name("roaring-moon"), "Roaring Moon")
        self.assertEqual(humanize_name("great-tusk"), "Great Tusk")

    def test_items_and_moves(self):
        self.assertEqual(humanize_name("choice-scarf", category="item"), "Choice Scarf")
        self.assertEqual(humanize_name("heavy-duty-boots", category="item"), "Heavy-Duty Boots")
        self.assertEqual(humanize_name("freeze-dry", category="move"), "Freeze-Dry")
        self.assertEqual(humanize_name("u-turn", category="move"), "U-Turn")

    def test_empty_or_none(self):
        self.assertEqual(humanize_name(None), "")
        self.assertEqual(humanize_name(""), "")

    def test_lru_cache_efficiency(self):
        info_before = humanize_name.cache_info()
        for _ in range(50):
            humanize_name("tapu-koko")
        info_after = humanize_name.cache_info()
        self.assertGreater(info_after.hits, info_before.hits)


if __name__ == "__main__":
    unittest.main()
