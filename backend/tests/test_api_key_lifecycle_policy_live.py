# File Path: backend/tests/test_api_key_lifecycle_policy_live.py
# Timestamp: 2026-05-26T22:10:00+08:00
# Version: v0.1

import json
import os
import time
import unittest
import urllib.error
import urllib.request

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
        with urllib.request.urlopen(request, timeout=25) as response:
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


class APIKeyLifecyclePolicyLiveTests(unittest.TestCase):
    def test_01_api_key_lifecycle_policy(self):
        admin_headers = _admin_headers()
        provider_id = _openai_provider_id()
        unique_suffix = int(time.time() * 1000)

        status, dept_resp = _request(
            "POST",
            "/departments",
            payload={
                "name": f"KeyPolicyDept-{unique_suffix}",
                "monthly_budget_usd": "3000.000000",
                "status": "ACTIVE",
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        department_id = int(dept_resp["id"])

        user_email = f"key_policy_{unique_suffix}@example.com"
        user_password = "Passw0rd!"

        status, register_resp = _request(
            "POST",
            "/auth/register",
            payload={
                "name": "Key Policy User",
                "email": user_email,
                "password": user_password,
                "department_id": department_id,
            },
        )
        self.assertEqual(status, 200)
        owner_user_id = int(register_resp["id"])

        status, key1_resp = _request(
            "POST",
            "/api-keys",
            payload={
                "provider_id": provider_id,
                "name": f"key-policy-primary-{unique_suffix}",
                "plain_secret": f"primary-secret-{unique_suffix}",
                "owner_user_id": owner_user_id,
                "department_id": department_id,
                "is_primary": True,
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        key1_id = int(key1_resp["id"])

        status, _ = _request(
            "POST",
            f"/api-keys/{key1_id}/rotate",
            payload={"new_plain_secret": f"rotated-secret-{unique_suffix}"},
            headers=admin_headers,
            allowed_error_codes={422},
        )
        self.assertEqual(status, 422)

        status, rotated_resp = _request(
            "POST",
            f"/api-keys/{key1_id}/rotate",
            payload={
                "new_plain_secret": f"rotated-secret-{unique_suffix}",
                "reason": "Quarterly rotation policy",
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertIsNotNone(rotated_resp.get("last_rotated_at"))

        status, _ = _request(
            "POST",
            f"/api-keys/{key1_id}/disable",
            payload={"reason": "Retire compromised key"},
            headers=admin_headers,
            allowed_error_codes={409},
        )
        self.assertEqual(status, 409)

        status, key2_resp = _request(
            "POST",
            "/api-keys",
            payload={
                "provider_id": provider_id,
                "name": f"key-policy-backup-{unique_suffix}",
                "plain_secret": f"backup-secret-{unique_suffix}",
                "owner_user_id": owner_user_id,
                "department_id": department_id,
                "is_primary": False,
            },
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        key2_id = int(key2_resp["id"])

        status, disabled_resp = _request(
            "POST",
            f"/api-keys/{key1_id}/disable",
            payload={"reason": "Switch to backup key"},
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(str(disabled_resp.get("status") or ""), "DISABLED")

        status, list_resp = _request("GET", "/api-keys?page=1&page_size=200&sort_by=id&sort_order=asc", headers=admin_headers)
        self.assertEqual(status, 200)
        items = list_resp.get("items") or []

        key2_item = None
        for item in items:
            if int(item.get("id") or 0) == key2_id:
                key2_item = item
                break

        self.assertIsNotNone(key2_item)
        self.assertTrue(bool(key2_item.get("is_primary")))


if __name__ == "__main__":
    unittest.main()
