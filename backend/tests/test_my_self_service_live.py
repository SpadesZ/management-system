# File Path: backend/tests/test_my_self_service_live.py
# Timestamp: 2026-05-26T21:20:00+08:00
# Version: v0.1

import json
import os
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

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


class MySelfServiceLiveTests(unittest.TestCase):
    def test_01_my_assets_requests_outputs(self):
        headers = _admin_headers()

        status, me_resp = _request("GET", "/me", headers=headers)
        self.assertEqual(status, 200)
        user_id = int(me_resp["id"])
        department_id = int(me_resp["department_id"])

        unique_suffix = int(time.time() * 1000)

        status, account_resp = _request(
            "POST",
            "/ai-accounts",
            payload={
                "vendor": "openai",
                "product": "chatgpt-enterprise",
                "plan": f"my-self-{unique_suffix}",
                "seats": 1,
                "monthly_cost_usd": "49.000000",
                "renewal_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "owner_user_id": user_id,
                "status": "ACTIVE",
            },
            headers=headers,
        )
        self.assertEqual(status, 200)
        ai_account_id = int(account_resp["id"])

        status, purpose_resp = _request(
            "POST",
            "/usage-purposes",
            payload={
                "code": f"MY_SELF_{unique_suffix}",
                "name": "My Self Output",
                "description": "my endpoint live test",
                "status": "ACTIVE",
            },
            headers=headers,
        )
        self.assertEqual(status, 200)
        usage_purpose_id = int(purpose_resp["id"])

        status, output_resp = _request(
            "POST",
            "/work-outputs",
            payload={
                "usage_purpose_id": usage_purpose_id,
                "department_id": department_id,
                "ai_account_id": ai_account_id,
                "output_title": "My endpoint output",
                "output_summary": "Validate /my/outputs endpoint",
                "input_tokens": 100,
                "output_tokens": 40,
                "cost_usd": "0.120000",
                "value_usd": "0.650000",
                "currency": "USD",
                "metadata_json": {"source": "test_my_self_service_live"},
            },
            headers=headers,
        )
        self.assertEqual(status, 200)
        work_output_id = int(output_resp["id"])

        status, request_resp = _request(
            "POST",
            "/approval-requests",
            payload={
                "request_type": "AI_ACCOUNT_ACCESS",
                "target_type": "AI_ACCOUNT",
                "target_id": ai_account_id,
                "reason": "Validate /my/requests endpoint",
                "payload_json": {"ai_account_id": ai_account_id},
            },
            headers=headers,
        )
        self.assertEqual(status, 200)
        approval_request_id = int(request_resp["id"])

        status, my_assets_resp = _request(
            "GET",
            "/my/assets?page=1&page_size=200&sort_by=created_at&sort_order=desc",
            headers=headers,
        )
        self.assertEqual(status, 200)
        my_ai_account_ids = [int(item.get("id") or 0) for item in (my_assets_resp.get("ai_accounts") or [])]
        self.assertIn(ai_account_id, my_ai_account_ids)

        status, my_requests_resp = _request(
            "GET",
            "/my/requests?page=1&page_size=200&sort_by=id&sort_order=desc&status=PENDING",
            headers=headers,
        )
        self.assertEqual(status, 200)
        my_request_ids = [int(item.get("id") or 0) for item in (my_requests_resp.get("items") or [])]
        self.assertIn(approval_request_id, my_request_ids)

        status, my_outputs_resp = _request(
            "GET",
            "/my/outputs?page=1&page_size=200&sort_by=created_at&sort_order=desc&status=DRAFT",
            headers=headers,
        )
        self.assertEqual(status, 200)
        my_output_ids = [int(item.get("id") or 0) for item in (my_outputs_resp.get("items") or [])]
        self.assertIn(work_output_id, my_output_ids)


if __name__ == "__main__":
    unittest.main()
