# File Path: backend/tests/test_assistant_live.py
# Timestamp: 2026-05-26T00:00:00+08:00
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


def _admin_headers() -> dict[str, str]:
    login_payload = {
        "email": "admin@example.com",
        "password": "ChangeThisPassword!",
    }
    status, login_resp = _request("POST", "/auth/login", payload=login_payload)
    if status != 200 or not login_resp.get("access_token"):
        raise AssertionError(f"Failed to login admin: {status}, {login_resp}")
    return {"Authorization": f"Bearer {login_resp['access_token']}"}


class AssistantLiveTests(unittest.TestCase):
    def test_01_blocked_high_risk_command(self):
        headers = _admin_headers()
        payload = {
            "message": "幫我核准這筆審批並直接停用那把 key",
            "context_type": "auto",
            "session_id": f"assist-{int(time.time() * 1000)}",
        }

        status, resp = _request("POST", "/assistant/chat", payload=payload, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(resp.get("risk_level"), "BLOCKED")
        self.assertIsInstance(resp.get("answer"), str)
        self.assertGreater(len(str(resp.get("trace_id") or "")), 8)

    def test_02_policy_question_response_shape(self):
        headers = _admin_headers()
        payload = {
            "message": "公司政策允不允許使用高價模型？",
            "context_type": "policy",
            "session_id": f"assist-{int(time.time() * 1000)}",
        }

        status, resp = _request("POST", "/assistant/chat", payload=payload, headers=headers)
        self.assertEqual(status, 200)

        task_ids = resp.get("task_ids") or []
        self.assertIsInstance(task_ids, list)
        self.assertIn("usage_policy_qa", task_ids)
        self.assertEqual(resp.get("primary_task_id"), "usage_policy_qa")

        sources = resp.get("sources") or []
        self.assertIsInstance(sources, list)
        self.assertGreaterEqual(len(sources), 1)

        source_keys = {str(item.get("source_key") or "") for item in sources if isinstance(item, dict)}
        self.assertIn("policy.snippets", source_keys)

        self.assertIsInstance(resp.get("suggested_actions"), list)
        self.assertGreater(len(str(resp.get("trace_id") or "")), 8)


if __name__ == "__main__":
    unittest.main()
