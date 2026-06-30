# File Path: backend/tests/test_rbac_role_permissions_live.py
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


class RBACRolePermissionLiveTests(unittest.TestCase):
    def test_01_role_permission_mapping_is_enforced(self):
        admin_headers = _admin_headers()

        status, options_resp = _request("GET", "/auth/register/options")
        self.assertEqual(status, 200)
        departments = options_resp.get("departments") or []
        self.assertGreaterEqual(len(departments), 1)
        department_id = int(departments[0]["id"])

        unique_suffix = int(time.time() * 1000)
        user_email = f"rbac_{unique_suffix}@example.com"
        user_password = "Passw0rd!"

        status, register_resp = _request(
            "POST",
            "/auth/register",
            payload={
                "name": "RBAC Live User",
                "email": user_email,
                "password": user_password,
                "department_id": department_id,
            },
        )
        self.assertEqual(status, 200)
        user_id = int(register_resp["id"])

        employee_headers = _login_headers(user_email, user_password)

        status, _ = _request(
            "POST",
            "/usage-purposes",
            payload={
                "code": f"RBAC_EMP_{unique_suffix}",
                "name": "RBAC Employee Deny",
                "status": "ACTIVE",
            },
            headers=employee_headers,
            allowed_error_codes={403},
        )
        self.assertEqual(status, 403)

        status, patched_user = _request(
            "PATCH",
            f"/users/{user_id}",
            payload={"role": "FINANCE"},
            headers=admin_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(str(patched_user.get("role") or ""), "FINANCE")

        finance_headers = _login_headers(user_email, user_password)

        status, _ = _request(
            "POST",
            "/usage-purposes",
            payload={
                "code": f"RBAC_FIN_{unique_suffix}",
                "name": "RBAC Finance Allow",
                "status": "ACTIVE",
            },
            headers=finance_headers,
        )
        self.assertEqual(status, 200)

        deleted_count = 0
        role_id = None
        permission_id = None

        conn = _postgres_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.id, p.id
                    FROM roles r
                    JOIN permissions p ON p.code = %s
                    WHERE r.code = %s
                    """,
                    ("role.finance", "FINANCE"),
                )
                pair = cur.fetchone()
                self.assertIsNotNone(pair)
                role_id = int(pair[0])
                permission_id = int(pair[1])

                cur.execute(
                    """
                    DELETE FROM role_permissions
                    WHERE role_id = %s AND permission_id = %s
                    """,
                    (role_id, permission_id),
                )
                deleted_count = cur.rowcount
            conn.commit()
        finally:
            conn.close()

        self.assertGreaterEqual(deleted_count, 1)

        try:
            status, _ = _request(
                "POST",
                "/usage-purposes",
                payload={
                    "code": f"RBAC_DENY_{unique_suffix}",
                    "name": "RBAC Permission Missing",
                    "status": "ACTIVE",
                },
                headers=finance_headers,
                allowed_error_codes={403},
            )
            self.assertEqual(status, 403)
        finally:
            if role_id is not None and permission_id is not None:
                restore_conn = _postgres_connection()
                try:
                    with restore_conn.cursor() as cur:
                        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM role_permissions")
                        next_id = int(cur.fetchone()[0])
                        cur.execute(
                            """
                            INSERT INTO role_permissions (id, role_id, permission_id)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (role_id, permission_id) DO NOTHING
                            """,
                            (next_id, role_id, permission_id),
                        )
                    restore_conn.commit()
                finally:
                    restore_conn.close()


if __name__ == "__main__":
    unittest.main()
