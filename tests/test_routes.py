# tests/test_routes.py
"""Unit tests for Flask routes, API endpoints, and ActiveBattleStore."""

import unittest
from app import app, ActiveBattleStore


class TestRoutes(unittest.TestCase):
    """Verifies all core HTTP routes and API endpoints return status 200 OK."""

    def setUp(self):
        self.client = app.test_client()

    def test_core_pages(self):
        routes = [
            "/",
            "/pokedex",
            "/movedex",
            "/abilitydex",
            "/itemdex",
            "/type_tool",
            "/teambuilder",
            "/simulator",
            "/guide",
            "/developer",
        ]
        for r in routes:
            with self.subTest(route=r):
                res = self.client.get(r)
                self.assertEqual(res.status_code, 200, f"Route {r} failed with status {res.status_code}")

    def test_api_favorites(self):
        res = self.client.get("/api/favorites")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("favorites"), list)

    def test_api_teambuilder_legal_pokemon(self):
        res = self.client.get("/api/legal_pokemon")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreater(data.get("count", 0), 100)
        self.assertIsInstance(data.get("pokemon"), list)

    def test_active_battle_store_bounded_eviction(self):
        store = ActiveBattleStore(max_size=3)

        class DummyBattle:
            def __init__(self, idx, is_finished=False):
                self.idx = idx
                self.is_finished = is_finished

        # Add 3 battles
        store["b1"] = DummyBattle(1, is_finished=True)
        store["b2"] = DummyBattle(2, is_finished=False)
        store["b3"] = DummyBattle(3, is_finished=False)
        self.assertEqual(len(store), 3)

        # Adding a 4th should evict b1 (finished)
        store["b4"] = DummyBattle(4, is_finished=False)
        self.assertEqual(len(store), 3)
        self.assertNotIn("b1", store)
        self.assertIn("b4", store)


if __name__ == "__main__":
    unittest.main()
