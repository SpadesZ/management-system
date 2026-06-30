# File Path: backend/tests/test_gateway_entitlement_live.py
# Timestamp: 2026-05-26T22:10:00+08:00
# Version: v0.1

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


class GatewayEntitlementLiveTests(unittest.TestCase):
    def test_01_gateway_entitlement_policy_denies_and_allows(self):
        admin_headers = _admin_headers()

        status, me_admin = _request("GET", "/me", headers=admin_headers)
        self.assertEqual(status, 200)
        admin_user_id = int(me_admin["id"])

        unique_suffix = int(time.time() * 1000)

        status, dept_resp = _request(
            "POST",
            "/departments",
            payload={
                "name": f"EntDept-{unique_suffix}",
                "monthly_budget_usd": "5000.000000",
                "status": "ACTIVE",
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        department_id = int(dept_resp["id"])

        user_email = f"ent_user_{unique_suffix}@example.com"
        user_password = "Passw0rd!"

        status, register_resp = _request(
            "POST",
            "/auth/register",
            payload={
                "name": "Gateway Entitlement User",
                "email": user_email,
                "password": user_password,
                "department_id": department_id,
            },
        )
        self.assertEqual(status, 200)
        user_id = int(register_resp["id"])

        provider_id = _openai_provider_id()

        status, model_resp = _request(
            "POST",
            "/models",
            payload={
                "provider_id": provider_id,
                "model_code": f"ent-model-{unique_suffix}",
                "display_name": "Entitlement Test Model",
                "context_window": 4096,
                "capabilities_json": {"chat": True},
                "status": "ACTIVE",
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        model_id = int(model_resp["id"])
        model_code = str(model_resp["model_code"])

        status, _ = _request(
            "POST",
            f"/models/{model_id}/prices",
            payload={
                "model_id": model_id,
                "input_price_per_1m": "1.000000",
                "output_price_per_1m": "2.000000",
                "currency": "USD",
                "effective_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)

        status, api_key_resp = _request(
            "POST",
            "/api-keys",
            payload={
                "provider_id": provider_id,
                "name": f"ent-key-{unique_suffix}",
                "plain_secret": f"ent-secret-{unique_suffix}",
                "owner_user_id": user_id,
                "department_id": department_id,
                "is_primary": True,
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        api_key_id = int(api_key_resp["id"])

        user_headers = _login_headers(user_email, user_password)

        entitlement_id = None
        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM api_key_entitlements")
                entitlement_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO api_key_entitlements
                    (id, api_key_id, subject_type, subject_id, allowed_models_json, status)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        entitlement_id,
                        api_key_id,
                        "USER",
                        admin_user_id,
                        json.dumps({}),
                        "ACTIVE",
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        status, denied_subject = _request(
            "POST",
            "/gateway/chat",
            payload={
                "request_id": f"ent-gw-{unique_suffix}-2",
                "idempotency_key": f"ent-gw-{unique_suffix}-2",
                "provider_code": "openai",
                "model_code": model_code,
                "message": "Should be denied by subject entitlement",
                "metadata_json": {"source": "test_gateway_entitlement_live"},
            },
            headers=user_headers,
            allowed_error_codes={403},
        )
        self.assertEqual(status, 403)
        denied_subject_detail = denied_subject.get("detail") or {}
        self.assertEqual(str(denied_subject_detail.get("error_code") or ""), "ENTITLEMENT_DENIED")

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE api_key_entitlements
                    SET subject_id = %s,
                        allowed_models_json = %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (user_id, json.dumps(["model-not-allowed"]), entitlement_id),
                )
            conn.commit()
        finally:
            conn.close()

        status, denied_model = _request(
            "POST",
            "/gateway/chat",
            payload={
                "request_id": f"ent-gw-{unique_suffix}-3",
                "idempotency_key": f"ent-gw-{unique_suffix}-3",
                "provider_code": "openai",
                "model_code": model_code,
                "message": "Should be denied by model policy",
                "metadata_json": {"source": "test_gateway_entitlement_live"},
            },
            headers=user_headers,
            allowed_error_codes={403},
        )
        self.assertEqual(status, 403)
        denied_model_detail = denied_model.get("detail") or {}
        self.assertEqual(str(denied_model_detail.get("error_code") or ""), "ENTITLEMENT_MODEL_NOT_ALLOWED")

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE api_key_entitlements
                    SET allowed_models_json = %s::jsonb,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps([model_code]), entitlement_id),
                )
            conn.commit()
        finally:
            conn.close()

        status, allowed_after_policy = _request(
            "POST",
            "/gateway/chat",
            payload={
                "request_id": f"ent-gw-{unique_suffix}-4",
                "idempotency_key": f"ent-gw-{unique_suffix}-4",
                "provider_code": "openai",
                "model_code": model_code,
                "message": "Should pass when entitlement subject/model are matched",
                "metadata_json": {"source": "test_gateway_entitlement_live"},
            },
            headers=user_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(str(allowed_after_policy.get("model") or ""), model_code)


if __name__ == "__main__":
    unittest.main()
