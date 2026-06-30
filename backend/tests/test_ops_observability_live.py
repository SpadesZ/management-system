# File Path: backend/tests/test_ops_observability_live.py
# Timestamp: 2026-05-26T22:30:00+08:00
# Version: v0.1

import json
import os
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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


def _login_headers(email: str, password: str) -> dict[str, str]:
    status, login_resp = _request(
        "POST",
        "/auth/login",
        payload={"email": email, "password": password},
    )
    if status != 200 or not login_resp.get("access_token"):
        raise AssertionError(f"Failed to login {email}: {status}, {login_resp}")
    return {"Authorization": f"Bearer {login_resp['access_token']}"}


def _admin_headers() -> dict[str, str]:
    return _login_headers("admin@example.com", "ChangeThisPassword!")


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


def _create_model_and_price(headers: dict[str, str], unique_suffix: int, provider_id: int) -> tuple[int, str, int]:
    status, model_resp = _request(
        "POST",
        "/models",
        payload={
            "provider_id": provider_id,
            "model_code": f"ops-model-{unique_suffix}",
            "display_name": "Ops Observability Model",
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
            "input_price_per_1m": "1.000000",
            "output_price_per_1m": "1.000000",
            "currency": "USD",
            "effective_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    if status != 200:
        raise AssertionError(f"Failed to create model price: {status}, {price_resp}")

    return model_id, model_code, int(price_resp["id"])


class OpsObservabilityLiveTests(unittest.TestCase):
    def test_01_ops_observability_endpoints(self):
        admin_headers = _admin_headers()

        status, me_resp = _request("GET", "/me", headers=admin_headers)
        self.assertEqual(status, 200)
        user_id = int(me_resp["id"])
        department_id = int(me_resp["department_id"])

        provider_id = _openai_provider_id()
        unique_suffix = int(time.time() * 1000)

        model_id, model_code, _ = _create_model_and_price(admin_headers, unique_suffix, provider_id)

        status, key_resp = _request(
            "POST",
            "/api-keys",
            payload={
                "provider_id": provider_id,
                "name": f"ops-key-{unique_suffix}",
                "plain_secret": f"ops-secret-{unique_suffix}",
                "owner_user_id": user_id,
                "department_id": department_id,
                "is_primary": True,
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        api_key_id = int(key_resp["id"])

        request_id = f"ops-req-{unique_suffix}"
        idempotency_key = f"ops-idem-{unique_suffix}"

        status, gateway_resp = _request(
            "POST",
            "/gateway/chat",
            payload={
                "request_id": request_id,
                "idempotency_key": idempotency_key,
                "provider_code": "openai",
                "model_code": model_code,
                "message": "Ops observability live test message",
                "metadata_json": {"source": "test_ops_observability_live"},
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(str(gateway_resp.get("request_id") or ""), request_id)

        now_utc = datetime.now(timezone.utc)
        window_start = now_utc - timedelta(hours=2)
        window_end = now_utc + timedelta(minutes=2)

        export_failed_message = f"ops export failed {unique_suffix}"
        aggregation_failed_message = f"ops aggregation failed {unique_suffix}"

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT setval('billing_imports_id_seq', GREATEST((SELECT COALESCE(MAX(id), 1) FROM billing_imports), 1), true)"
                )
                cur.execute(
                    "SELECT setval('billing_reconciliation_issues_id_seq', GREATEST((SELECT COALESCE(MAX(id), 1) FROM billing_reconciliation_issues), 1), true)"
                )
                cur.execute(
                    "SELECT setval('export_jobs_id_seq', GREATEST((SELECT COALESCE(MAX(id), 1) FROM export_jobs), 1), true)"
                )
                cur.execute(
                    "SELECT setval('aggregation_jobs_id_seq', GREATEST((SELECT COALESCE(MAX(id), 1) FROM aggregation_jobs), 1), true)"
                )

                cur.execute(
                    """
                    SELECT id, COALESCE(project_id, 0), provider_id, model_id, api_key_id, price_version_id
                    FROM usage_events
                    WHERE request_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (request_id,),
                )
                usage_row = cur.fetchone()
                self.assertIsNotNone(usage_row)
                usage_event_id = int(usage_row[0])
                project_id = None if int(usage_row[1]) == 0 else int(usage_row[1])
                provider_id_db = int(usage_row[2])
                model_id_db = int(usage_row[3])
                api_key_id_db = int(usage_row[4])
                price_version_id = int(usage_row[5])

                cur.execute(
                    """
                    SELECT id
                    FROM cost_ledger
                    WHERE request_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (request_id,),
                )
                ledger_row = cur.fetchone()
                self.assertIsNotNone(ledger_row)
                ledger_id = int(ledger_row[0])

                cur.execute(
                    "UPDATE cost_ledger SET settled_cost = %s, estimated_cost = %s WHERE id = %s",
                    ("2.500000", "2.500000", ledger_id),
                )
                cur.execute(
                    "UPDATE usage_events SET estimated_cost_usd = %s WHERE id = %s AND request_id = %s",
                    ("1.000000", usage_event_id, request_id),
                )

                for idx in range(2):
                    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM usage_events")
                    next_usage_id = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        INSERT INTO usage_events (
                            id, created_at, request_id, idempotency_key, user_id, department_id, project_id,
                            provider_id, model_id, api_key_id, price_version_id, request_type,
                            input_tokens, output_tokens, cached_input_tokens, reasoning_tokens, total_tokens,
                            estimated_cost_usd, latency_ms, status, error_code, prompt_hash, metadata_json
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, '{}'::jsonb
                        )
                        """,
                        (
                            next_usage_id,
                            now_utc - timedelta(minutes=idx + 1),
                            f"ops-failed-req-{unique_suffix}-{idx}",
                            f"ops-failed-idem-{unique_suffix}-{idx}",
                            user_id,
                            department_id,
                            project_id,
                            provider_id_db,
                            model_id_db,
                            api_key_id_db,
                            price_version_id,
                            "CHAT",
                            12,
                            0,
                            0,
                            0,
                            12,
                            "0.000000",
                            150,
                            "FAILED",
                            "SIMULATED_ERROR",
                            None,
                        ),
                    )

                cur.execute(
                    """
                    INSERT INTO billing_imports (
                        provider_id, period_start, period_end, source_file, status, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, '{}'::jsonb)
                    RETURNING id
                    """,
                    (
                        provider_id_db,
                        now_utc - timedelta(days=1),
                        now_utc,
                        f"ops-import-{unique_suffix}.csv",
                        "SUCCESS",
                    ),
                )
                billing_import_id = int(cur.fetchone()[0])

                cur.execute(
                    """
                    INSERT INTO billing_reconciliation_issues (
                        billing_import_id, request_id, ledger_id, expected_cost, actual_cost,
                        delta_cost, status, reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        billing_import_id,
                        request_id,
                        ledger_id,
                        "1.000000",
                        "2.500000",
                        "1.500000",
                        "PENDING",
                        "simulated mismatch for ops live test",
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO export_jobs (
                        requester_user_id, export_type, filters_json, status,
                        error_message, created_at, started_at, finished_at
                    )
                    VALUES (%s, %s, '{}'::jsonb, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        "COST_LEDGER",
                        "FAILED",
                        export_failed_message,
                        now_utc - timedelta(minutes=8),
                        now_utc - timedelta(minutes=7),
                        now_utc,
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO export_jobs (
                        requester_user_id, export_type, filters_json, status, created_at
                    )
                    VALUES (%s, %s, '{}'::jsonb, %s, %s)
                    """,
                    (
                        user_id,
                        "COST_LEDGER",
                        "PENDING",
                        now_utc - timedelta(minutes=25),
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO aggregation_jobs (
                        job_type, period_start, period_end, status, idempotency_key,
                        processed_rows, error_message, started_at, finished_at, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "SUMMARY_REBUILD",
                        now_utc - timedelta(days=1),
                        now_utc,
                        "FAILED",
                        f"ops-agg-failed-{unique_suffix}",
                        0,
                        aggregation_failed_message,
                        now_utc - timedelta(minutes=6),
                        now_utc,
                        now_utc - timedelta(minutes=7),
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO aggregation_jobs (
                        job_type, period_start, period_end, status, idempotency_key,
                        processed_rows, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "SUMMARY_REBUILD",
                        now_utc - timedelta(days=2),
                        now_utc - timedelta(days=1),
                        "PENDING",
                        f"ops-agg-pending-{unique_suffix}",
                        0,
                        now_utc - timedelta(minutes=40),
                    ),
                )

            conn.commit()
        finally:
            conn.close()

        accuracy_query = urllib.parse.urlencode(
            {
                "start_at": window_start.isoformat(),
                "end_at": window_end.isoformat(),
                "delta_threshold_usd": "0.100000",
            }
        )
        status, accuracy_resp = _request(
            "GET",
            f"/ops/billing-accuracy?{accuracy_query}",
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(int(accuracy_resp.get("mismatch_request_count") or 0), 1)
        self.assertGreaterEqual(int(accuracy_resp.get("reconciliation_issue_open_count") or 0), 1)
        delta_total = Decimal(str(accuracy_resp.get("delta_total_usd") or "0"))
        self.assertGreater(delta_total.copy_abs(), Decimal("0"))

        reconciliation_query = urllib.parse.urlencode(
            {
                "page": 1,
                "page_size": 50,
                "start_at": window_start.isoformat(),
                "end_at": window_end.isoformat(),
                "delta_threshold_usd": "0.100000",
            }
        )
        status, reconciliation_resp = _request(
            "GET",
            f"/ops/reconciliation/report?{reconciliation_query}",
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(int((reconciliation_resp.get("meta") or {}).get("total") or 0), 1)
        items = reconciliation_resp.get("items") or []
        self.assertTrue(any(str(item.get("request_id") or "") == request_id for item in items))

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM alerts
                    WHERE title IN ('Error budget burn HIGH', 'Error budget burn CRITICAL')
                      AND triggered_at >= %s
                      AND triggered_at < %s
                    """,
                    (window_start, window_end),
                )
            conn.commit()
        finally:
            conn.close()

        error_budget_query = urllib.parse.urlencode(
            {
                "start_at": window_start.isoformat(),
                "end_at": window_end.isoformat(),
                "error_budget_pct": "1.000000",
                "emit_alert": "true",
            }
        )
        status, error_budget_resp = _request(
            "GET",
            f"/ops/error-budget?{error_budget_query}",
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertIn(str(error_budget_resp.get("severity") or ""), {"HIGH", "CRITICAL"})
        self.assertTrue(bool(error_budget_resp.get("alert_emitted")))
        self.assertGreaterEqual(int(error_budget_resp.get("error_requests") or 0), 2)

        status, error_budget_resp_2 = _request(
            "GET",
            f"/ops/error-budget?{error_budget_query}",
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertFalse(bool(error_budget_resp_2.get("alert_emitted")))

        status, backlog_resp = _request("GET", "/ops/worker/backlog", headers=admin_headers)
        self.assertEqual(status, 200)
        queue_depth = backlog_resp.get("queue_depth") or {}
        self.assertGreaterEqual(int(queue_depth.get("failed_total") or 0), 2)

        dead_letters = backlog_resp.get("dead_letter_candidates") or []
        dead_letter_messages = [str(item.get("error_message") or "") for item in dead_letters]
        self.assertTrue(any(export_failed_message in msg for msg in dead_letter_messages))
        self.assertTrue(any(aggregation_failed_message in msg for msg in dead_letter_messages))

    def test_02_ops_contract_and_permission_matrix(self):
        admin_headers = _admin_headers()
        unique_suffix = int(time.time() * 1000)

        status, dept_resp = _request(
            "POST",
            "/departments",
            payload={
                "name": f"OpsPermDept-{unique_suffix}",
                "monthly_budget_usd": "1200.000000",
                "status": "ACTIVE",
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        department_id = int(dept_resp["id"])

        user_email = f"ops_perm_{unique_suffix}@example.com"
        user_password = "Passw0rd!"

        status, register_resp = _request(
            "POST",
            "/auth/register",
            payload={
                "name": "Ops Permission User",
                "email": user_email,
                "password": user_password,
                "department_id": department_id,
            },
        )
        self.assertEqual(status, 200)
        user_id = int(register_resp["id"])

        employee_headers = _login_headers(user_email, user_password)

        status, _ = _request(
            "GET",
            "/ops/worker/backlog",
            headers=employee_headers,
            allowed_error_codes={403},
        )
        self.assertEqual(status, 403)

        status, _ = _request(
            "GET",
            "/ops/worker/backlog",
            allowed_error_codes={401},
        )
        self.assertEqual(status, 401)

        status, _ = _request(
            "PATCH",
            f"/users/{user_id}",
            payload={"role": "FINANCE"},
            headers=admin_headers,
        )
        self.assertEqual(status, 200)

        finance_headers = _login_headers(user_email, user_password)

        status, backlog_resp = _request("GET", "/ops/worker/backlog", headers=finance_headers)
        self.assertEqual(status, 200)
        self.assertIsInstance(backlog_resp.get("queue_depth"), dict)

        status, _ = _request(
            "GET",
            "/ops/reconciliation/report?page=0",
            headers=admin_headers,
            allowed_error_codes={422},
        )
        self.assertEqual(status, 422)

        status, _ = _request(
            "GET",
            "/ops/error-budget?error_budget_pct=0",
            headers=admin_headers,
            allowed_error_codes={422},
        )
        self.assertEqual(status, 422)

        status, accuracy_resp = _request("GET", "/ops/billing-accuracy", headers=admin_headers)
        self.assertEqual(status, 200)
        self.assertIn("accuracy_ratio", accuracy_resp)
        self.assertIn("mismatch_request_count", accuracy_resp)

    def test_03_export_audit_stress_path(self):
        admin_headers = _admin_headers()
        unique_suffix = int(time.time() * 1000)
        stress_count = 20
        start_at = datetime.now(timezone.utc)

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT setval('export_jobs_id_seq', GREATEST((SELECT COALESCE(MAX(id), 1) FROM export_jobs), 1), true)"
                )
            conn.commit()
        finally:
            conn.close()

        for idx in range(stress_count):
            status, _ = _request(
                "POST",
                "/exports",
                payload={
                    "export_type": "COST_LEDGER",
                    "filters_json": {
                        "stress_id": str(unique_suffix),
                        "seq": idx,
                    },
                },
                headers=admin_headers,
            )
            self.assertEqual(status, 200)

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM export_jobs
                    WHERE export_type = %s
                      AND filters_json->>'stress_id' = %s
                    """,
                    ("COST_LEDGER", str(unique_suffix)),
                )
                export_job_count = int(cur.fetchone()[0])

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM audit_logs
                    WHERE action = 'EXPORT_CREATE'
                      AND resource_type = 'export_jobs'
                      AND created_at >= %s
                    """,
                    (start_at,),
                )
                audit_count = int(cur.fetchone()[0])
        finally:
            conn.close()

        self.assertGreaterEqual(export_job_count, stress_count)
        self.assertGreaterEqual(audit_count, stress_count)


if __name__ == "__main__":
    unittest.main()
