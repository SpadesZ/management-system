# File Path: backend/tests/test_gateway_idempotency_live.py
# Timestamp: 2026-05-26T22:30:00+08:00
# Version: v0.1

import concurrent.futures
import json
import os
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2

BASE_URL = os.getenv("BASE_URL", "http://localhost:18001").rstrip("/")


def _request(
    method: str,
    path: str,
    payload: dict | None = None,
    headers: dict | None = None,
    allowed_error_codes: set[int] | None = None,
):
    body = None
    req_headers: dict[str, str] = {}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=req_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        content = exc.read().decode("utf-8")
        try:
            parsed = json.loads(content) if content else {}
        except json.JSONDecodeError:
            parsed = {"raw": content}

        if allowed_error_codes and exc.code in allowed_error_codes:
            return exc.code, parsed

        raise AssertionError(f"HTTP {exc.code} {path}: {parsed}") from exc


def _admin_headers() -> dict[str, str]:
    status, login_resp = _request(
        "POST",
        "/auth/login",
        payload={"email": "admin@example.com", "password": "ChangeThisPassword!"},
    )
    if status != 200 or not login_resp.get("access_token"):
        raise AssertionError(f"Failed to login admin: {status}, {login_resp}")
    return {"Authorization": f"Bearer {login_resp['access_token']}"}


def _postgres_connection():
    host = os.getenv("POSTGRES_HOST", "localhost")
    if host in {"postgres", "db", "postgresql"}:
        host = "localhost"

    return psycopg2.connect(
        host=host,
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "llm_finops"),
        user=os.getenv("POSTGRES_USER", "llm_finops"),
        password=os.getenv("POSTGRES_PASSWORD", "llm_finops"),
    )


def _openai_provider_id() -> int:
    conn = _postgres_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM providers WHERE code = %s LIMIT 1", ("openai",))
            row = cur.fetchone()
            if row is None:
                raise AssertionError("OpenAI provider not found")
            return int(row[0])
    finally:
        conn.close()


def _create_model_and_price(headers: dict[str, str], unique_suffix: int, provider_id: int) -> str:
    status, model_resp = _request(
        "POST",
        "/models",
        payload={
            "provider_id": provider_id,
            "model_code": f"idem-model-{unique_suffix}",
            "display_name": "Idempotency Test Model",
            "context_window": 4096,
            "capabilities_json": {"chat": True},
            "status": "ACTIVE",
        },
        headers=headers,
    )
    if status != 200:
        raise AssertionError(f"Failed to create model: {status}, {model_resp}")

    model_id = int(model_resp["id"])
    model_code = str(model_resp["model_code"])

    status, price_resp = _request(
        "POST",
        f"/models/{model_id}/prices",
        payload={
            "model_id": model_id,
            "input_price_per_1m": "1.100000",
            "output_price_per_1m": "2.200000",
            "currency": "USD",
            "effective_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    if status != 200:
        raise AssertionError(f"Failed to create model price: {status}, {price_resp}")

    return model_code


class GatewayIdempotencyLiveTests(unittest.TestCase):
    def test_01_gateway_request_id_and_idempotency_replay(self):
        headers = _admin_headers()

        status, me_resp = _request("GET", "/me", headers=headers)
        self.assertEqual(status, 200)
        user_id = int(me_resp["id"])
        department_id = int(me_resp["department_id"])

        provider_id = _openai_provider_id()
        unique_suffix = int(time.time() * 1000)

        model_code = _create_model_and_price(headers, unique_suffix, provider_id)

        status, key_resp = _request(
            "POST",
            "/api-keys",
            payload={
                "provider_id": provider_id,
                "name": f"idem-key-{unique_suffix}",
                "plain_secret": f"idem-secret-{unique_suffix}",
                "owner_user_id": user_id,
                "department_id": department_id,
                "is_primary": True,
            },
            headers=headers,
        )
        self.assertEqual(status, 200)

        request_id_1 = f"idem-req-{unique_suffix}-1"
        idempotency_key_1 = f"idem-key-{unique_suffix}-1"

        payload_1 = {
            "request_id": request_id_1,
            "idempotency_key": idempotency_key_1,
            "provider_code": "openai",
            "model_code": model_code,
            "message": "Verify gateway idempotent replay behavior",
            "metadata_json": {"source": "test_gateway_idempotency_live"},
        }

        status, first_resp = _request("POST", "/gateway/chat", payload=payload_1, headers=headers)
        self.assertEqual(status, 200)
        self.assertFalse(bool(first_resp.get("idempotent_replay")))

        status, replay_same_request = _request("POST", "/gateway/chat", payload=payload_1, headers=headers)
        self.assertEqual(status, 200)
        self.assertTrue(bool(replay_same_request.get("idempotent_replay")))

        payload_same_idempotency = {
            "request_id": f"idem-req-{unique_suffix}-2",
            "idempotency_key": idempotency_key_1,
            "provider_code": "openai",
            "model_code": model_code,
            "message": "Replay by idempotency key",
            "metadata_json": {"source": "test_gateway_idempotency_live"},
        }
        status, replay_same_key = _request("POST", "/gateway/chat", payload=payload_same_idempotency, headers=headers)
        self.assertEqual(status, 200)
        self.assertTrue(bool(replay_same_key.get("idempotent_replay")))
        self.assertEqual(str(replay_same_key.get("request_id") or ""), request_id_1)

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM usage_event_request_keys WHERE request_id = %s", (request_id_1,))
                usage_event_key_count = int(cur.fetchone()[0])

                cur.execute("SELECT COUNT(*) FROM usage_events WHERE request_id = %s", (request_id_1,))
                usage_event_count = int(cur.fetchone()[0])

                cur.execute("SELECT COUNT(*) FROM cost_ledger WHERE request_id = %s", (request_id_1,))
                ledger_request_count = int(cur.fetchone()[0])

                cur.execute(
                    "SELECT COUNT(*) FROM cost_ledger WHERE idempotency_key = %s AND user_id = %s",
                    (idempotency_key_1, user_id),
                )
                ledger_idempotency_count = int(cur.fetchone()[0])

                cur.execute("SELECT COUNT(*) FROM budget_reservations WHERE request_id = %s", (request_id_1,))
                reservation_count = int(cur.fetchone()[0])

                cur.execute("SELECT status FROM budget_reservations WHERE request_id = %s", (request_id_1,))
                reservation_status = str(cur.fetchone()[0])
        finally:
            conn.close()

        self.assertEqual(usage_event_key_count, 1)
        self.assertEqual(usage_event_count, 1)
        self.assertEqual(ledger_request_count, 1)
        self.assertEqual(ledger_idempotency_count, 1)
        self.assertEqual(reservation_count, 1)
        self.assertEqual(reservation_status, "SETTLED")

    def test_02_concurrent_same_request_results_single_write(self):
        headers = _admin_headers()

        status, me_resp = _request("GET", "/me", headers=headers)
        self.assertEqual(status, 200)
        user_id = int(me_resp["id"])
        department_id = int(me_resp["department_id"])

        provider_id = _openai_provider_id()
        unique_suffix = int(time.time() * 1000)

        model_code = _create_model_and_price(headers, unique_suffix, provider_id)

        status, _ = _request(
            "POST",
            "/api-keys",
            payload={
                "provider_id": provider_id,
                "name": f"idem-race-key-{unique_suffix}",
                "plain_secret": f"idem-race-secret-{unique_suffix}",
                "owner_user_id": user_id,
                "department_id": department_id,
                "is_primary": True,
            },
            headers=headers,
        )
        self.assertEqual(status, 200)

        request_id = f"idem-race-req-{unique_suffix}"
        idempotency_key = f"idem-race-key-{unique_suffix}"
        payload = {
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "provider_code": "openai",
            "model_code": model_code,
            "message": "Concurrent request idempotency race test",
            "metadata_json": {"source": "test_gateway_idempotency_live"},
        }

        def _send_once():
            status_code, data = _request("POST", "/gateway/chat", payload=payload, headers=headers, allowed_error_codes={409})
            return status_code, data

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_send_once) for _ in range(2)]
            outcomes = [future.result() for future in futures]

        status_codes = sorted(int(item[0]) for item in outcomes)
        self.assertIn(status_codes[0], {200, 409})
        self.assertIn(status_codes[1], {200, 409})

        success_count = sum(1 for status_code, _ in outcomes if int(status_code) == 200)
        self.assertGreaterEqual(success_count, 1)

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM usage_events WHERE request_id = %s", (request_id,))
                usage_event_count = int(cur.fetchone()[0])

                cur.execute("SELECT COUNT(*) FROM cost_ledger WHERE request_id = %s", (request_id,))
                ledger_count = int(cur.fetchone()[0])

                cur.execute("SELECT COUNT(*) FROM budget_reservations WHERE request_id = %s", (request_id,))
                reservation_count = int(cur.fetchone()[0])
        finally:
            conn.close()

        self.assertEqual(usage_event_count, 1)
        self.assertEqual(ledger_count, 1)
        self.assertEqual(reservation_count, 1)


if __name__ == "__main__":
    unittest.main()
