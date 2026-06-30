# File Path: backend/tests/test_smoke_live.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

import json
import os
import time
import unittest
import urllib.error
import urllib.request

BASE_URL = os.getenv("BASE_URL", "http://localhost:18001").rstrip("/")


def _request(method: str, path: str, payload: dict | None = None, headers: dict | None = None):
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
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        content = exc.read().decode("utf-8")
        try:
            parsed = json.loads(content) if content else {}
        except json.JSONDecodeError:
            parsed = {"raw": content}
        raise AssertionError(f"HTTP {exc.code} {path}: {parsed}") from exc


class SmokeLiveTests(unittest.TestCase):
    def test_01_healthz(self):
        status, payload = _request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(payload.get("status"), "ok")

    def test_02_register_options(self):
        status, payload = _request("GET", "/auth/register/options")
        self.assertEqual(status, 200)
        self.assertIsInstance(payload.get("departments"), list)
        self.assertGreaterEqual(len(payload.get("departments")), 1)

    def test_03_register_then_login(self):
        _, options_payload = _request("GET", "/auth/register/options")
        departments = options_payload.get("departments") or []
        self.assertGreaterEqual(len(departments), 1)

        email = f"smoke_{int(time.time() * 1000)}@example.com"
        register_payload = {
            "name": "Smoke Register User",
            "email": email,
            "password": "Passw0rd!",
            "department_id": int(departments[0]["id"]),
        }

        status, register_resp = _request("POST", "/auth/register", payload=register_payload)
        self.assertEqual(status, 200)
        self.assertEqual(register_resp.get("email"), email)
        self.assertEqual(register_resp.get("status"), "ACTIVE")

        login_payload = {
            "email": email,
            "password": "Passw0rd!",
        }
        status, login_resp = _request("POST", "/auth/login", payload=login_payload)
        self.assertEqual(status, 200)
        token = str(login_resp.get("access_token") or "")
        self.assertGreater(len(token), 20)

    def test_04_me(self):
        status, login_resp = _request(
            "POST",
            "/auth/login",
            payload={"email": "admin@example.com", "password": "ChangeThisPassword!"},
        )
        self.assertEqual(status, 200)
        token = str(login_resp.get("access_token") or "")
        self.assertGreater(len(token), 20)

        status, me_resp = _request("GET", "/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(status, 200)
        self.assertEqual(str(me_resp.get("email") or "").lower(), "admin@example.com")
        self.assertEqual(str(me_resp.get("status") or ""), "ACTIVE")


if __name__ == "__main__":
    unittest.main()
