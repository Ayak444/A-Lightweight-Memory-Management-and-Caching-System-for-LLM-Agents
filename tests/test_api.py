from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from memlite.api import main


class APITests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_path = Path(directory.name) / "api.db"
        patcher = patch.object(main, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_memory_roundtrip_empty_filter_and_supersession(self) -> None:
        response = self.client.post(
            "/v1/memories",
            json={
                "memory_type": "semantic",
                "scope_id": "demo",
                "content": "Project DB SQLite",
            },
        )
        self.assertEqual(response.status_code, 200)
        memory_id = response.json()["id"]
        empty = self.client.post(
            "/v1/retrieval/query",
            json={
                "query": "Project DB",
                "scope_id": "demo",
                "memory_types": [],
            },
        )
        self.assertEqual(empty.json()["selected_memory_ids"], [])
        update = self.client.patch(
            f"/v1/memories/{memory_id}", json={"content": "Project DB MySQL"}
        )
        self.assertEqual(update.status_code, 200)
        memories = self.client.get("/v1/memories", params={"scope_id": "demo"}).json()
        self.assertEqual([item["content"] for item in memories], ["Project DB MySQL"])
        self.assertEqual(self.client.delete(f"/v1/memories/{update.json()['id']}").status_code, 200)

    def test_cache_context_rejection_never_returns_old_answer(self) -> None:
        stored = self.client.post(
            "/v1/cache/store",
            json={
                "query": "What DB?",
                "response": "SQLite",
                "scope_id": "demo",
                "model_id": "model-a",
            },
        )
        self.assertEqual(stored.status_code, 200)
        hit = self.client.post(
            "/v1/cache/lookup",
            params={
                "query": "What DB?",
                "scope_id": "demo",
                "model_id": "model-a",
            },
        )
        self.assertTrue(hit.json()["hit"])
        rejected = self.client.post(
            "/v1/cache/lookup",
            params={
                "query": "What DB?",
                "scope_id": "demo",
                "model_id": "model-b",
            },
        ).json()
        self.assertFalse(rejected["hit"])
        self.assertNotIn("response", rejected)
        stats = self.client.get("/v1/cache")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["total"], 1)

    def test_invalid_type_and_ttl_return_client_errors(self) -> None:
        self.assertEqual(
            self.client.get(
                "/v1/memories",
                params={
                    "scope_id": "demo",
                    "memory_type": "unknown",
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/v1/cache/store",
                json={
                    "query": "Q",
                    "response": "A",
                    "scope_id": "demo",
                    "ttl_seconds": -1,
                },
            ).status_code,
            422,
        )

    def test_rate_limit_keeps_health_available(self) -> None:
        with patch.object(main, "RATE_LIMIT_REQUESTS", 1):
            self.assertEqual(self.client.get("/v1/cache").status_code, 200)
            self.assertEqual(self.client.get("/v1/cache").status_code, 429)
            self.assertEqual(self.client.get("/health").status_code, 200)

    def test_token_budget_cap(self) -> None:
        with patch.object(main, "TOKEN_BUDGET_CAP", 10):
            # 10 tokens limit
            # Reset first
            self.client.post("/v1/budget/budget-demo/reset")
            # This should be ~3 tokens
            response = self.client.post(
                "/v1/retrieval/query",
                json={"query": "Hello world", "scope_id": "budget-demo"},
            )
            self.assertEqual(response.status_code, 200)

            # Check budget
            budget = self.client.get("/v1/budget/budget-demo").json()
            self.assertTrue(budget["used"] > 0)
            self.assertEqual(budget["cap"], 10)

            # Exceed budget (very long query)
            long_query = "x " * 50
            exceeded = self.client.post(
                "/v1/retrieval/query",
                json={"query": long_query, "scope_id": "budget-demo"},
            )
            self.assertEqual(exceeded.status_code, 429)
            self.assertIn("Token budget exceeded", exceeded.json()["detail"])

            # Reset budget
            reset = self.client.post("/v1/budget/budget-demo/reset")
            self.assertEqual(reset.status_code, 200)

            # Try again, should work
            again = self.client.post(
                "/v1/retrieval/query",
                json={"query": "Short again", "scope_id": "budget-demo"},
            )
            self.assertEqual(again.status_code, 200)

    def test_invalid_query_does_not_consume_budget(self) -> None:
        with patch.object(main, "TOKEN_BUDGET_CAP", 1):
            invalid = self.client.post(
                "/v1/retrieval/query", json={"scope_id": "invalid", "query": " "}
            )
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(self.client.get("/v1/budget/invalid").json()["used"], 0)
            valid = self.client.post(
                "/v1/retrieval/query", json={"scope_id": "invalid", "query": "x"}
            )
            self.assertEqual(valid.status_code, 200)
            self.assertEqual(self.client.get("/v1/budget/invalid").json()["used"], 1)

    def test_failed_cache_store_refunds_reservation(self) -> None:
        invalid = self.client.post(
            "/v1/cache/store", json={"scope_id": "refund", "query": "valid", "response": " "}
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.client.get("/v1/budget/refund").json()["used"], 0)
        self.assertEqual(self.client.get("/v1/cache").json()["total"], 0)

    def test_backend_exception_refunds_and_over_limit_reservation_does_not_charge(self) -> None:
        with patch.object(main.get_engine(), "retrieve", side_effect=ValueError("backend error")):
            response = self.client.post(
                "/v1/retrieval/query", json={"scope_id": "failure", "query": "x"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/v1/budget/failure").json()["used"], 0)
        with patch.object(main, "TOKEN_BUDGET_CAP", 1):
            response = self.client.post(
                "/v1/retrieval/query", json={"scope_id": "failure", "query": "too long"}
            )
        self.assertEqual(response.status_code, 429)
        budget = self.client.get("/v1/budget/failure").json()
        self.assertEqual(budget["used"], 0)
        self.assertEqual(budget["kind"], "estimated_input_tokens")
        self.assertFalse(budget["persistent"])

    def test_failed_cache_lookup_does_not_charge(self) -> None:
        with patch.object(main.get_engine(), "cache_lookup", side_effect=ValueError("invalid")):
            response = self.client.post(
                "/v1/cache/lookup", params={"scope_id": "lookup-failure", "query": "x"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/v1/budget/lookup-failure").json()["used"], 0)
