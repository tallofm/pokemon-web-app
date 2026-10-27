# tests/test_type_effectiveness.py
"""Unit tests for type effectiveness matrix and multi-type defense/offense calculators."""

import unittest
from fractions import Fraction
from utils.type_effectiveness import (
    mult_vs,
    calc_defense_buckets,
    calc_offense_buckets,
    TYPES,
)


class TestTypeEffectiveness(unittest.TestCase):
    """Verifies standard 18-type matrix relations, dual-type buckets, and special moves."""

    def test_single_type_interactions(self):
        self.assertEqual(mult_vs("water", "fire"), Fraction(2, 1))
        self.assertEqual(mult_vs("fire", "water"), Fraction(1, 2))
        self.assertEqual(mult_vs("electric", "ground"), Fraction(0, 1))
        self.assertEqual(mult_vs("ghost", "normal"), Fraction(0, 1))
        self.assertEqual(mult_vs("fairy", "dragon"), Fraction(2, 1))
        self.assertEqual(mult_vs("dragon", "fairy"), Fraction(0, 1))

    def test_dual_type_defense_buckets(self):
        # Swampert: Water / Ground -> 4x Grass, 0x Electric
        swampert_buckets = calc_defense_buckets(["water", "ground"])
        self.assertIn("grass", swampert_buckets["4x"])
        self.assertIn("electric", swampert_buckets["0x"])

        # Scizor: Bug / Steel -> 4x Fire, resistances to Grass, Ice, Psychic, etc.
        scizor_buckets = calc_defense_buckets(["bug", "steel"])
        self.assertIn("fire", scizor_buckets["4x"])
        self.assertIn("poison", scizor_buckets["0x"])

    def test_lru_cache_mult_vs(self):
        info_before = mult_vs.cache_info()
        for _ in range(100):
            mult_vs("ice", "dragon")
        info_after = mult_vs.cache_info()
        self.assertGreater(info_after.hits, info_before.hits)


if __name__ == "__main__":
    unittest.main()
