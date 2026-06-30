# File Path: backend/tests/test_phase2_governance_live.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.1

import json
import os
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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


def _decimal_value(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


class Phase2GovernanceLiveTests(unittest.TestCase):
    def test_01_work_output_lifecycle_and_roi(self):
        headers = _admin_headers()

        status, users_resp = _request("GET", "/users?page=1&page_size=200", headers=headers)
        self.assertEqual(status, 200)
        user_items = users_resp.get("items") or []
        self.assertGreaterEqual(len(user_items), 1)

        admin_user = None
        for item in user_items:
            if str(item.get("email") or "").lower() == "admin@example.com":
                admin_user = item
                break
        if admin_user is None:
            admin_user = user_items[0]

        admin_user_id = int(admin_user["id"])
        department_id = int(admin_user["department_id"])

        status, baseline_roi = _request(
            "GET",
            "/analytics/roi?group_by=user&page=1&page_size=200",
            headers=headers,
        )
        self.assertEqual(status, 200)

        baseline_user_value = Decimal("0")
        baseline_user_cost = Decimal("0")
        for item in baseline_roi.get("items") or []:
            if int(item.get("group_id") or 0) == admin_user_id:
                baseline_user_value = _decimal_value(item.get("value_usd"))
                baseline_user_cost = _decimal_value(item.get("cost_usd"))
                break

        unique_suffix = int(time.time() * 1000)
        usage_purpose_payload = {
            "code": f"PHASE2_{unique_suffix}",
            "name": "ROI Validation",
            "description": "Phase 2 live test",
            "status": "ACTIVE",
        }
        status, purpose_resp = _request("POST", "/usage-purposes", payload=usage_purpose_payload, headers=headers)
        self.assertEqual(status, 200)
        usage_purpose_id = int(purpose_resp["id"])

        account_payload = {
            "vendor": "openai",
            "product": "chatgpt-enterprise",
            "plan": f"phase2-{unique_suffix}",
            "seats": 3,
            "monthly_cost_usd": "120.000000",
            "renewal_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "owner_user_id": admin_user_id,
            "status": "ACTIVE",
        }
        status, account_resp = _request("POST", "/ai-accounts", payload=account_payload, headers=headers)
        self.assertEqual(status, 200)
        ai_account_id = int(account_resp["id"])

        approved_cost = Decimal("2.500000")
        approved_value = Decimal("8.750000")

        output_payload = {
            "usage_purpose_id": usage_purpose_id,
            "department_id": department_id,
            "ai_account_id": ai_account_id,
            "output_title": "Phase 2 ROI approved sample",
            "output_summary": "approved sample for ROI analytics",
            "input_tokens": 800,
            "output_tokens": 400,
            "cost_usd": str(approved_cost),
            "value_usd": str(approved_value),
            "currency": "USD",
            "metadata_json": {"source": "phase2-live-test"},
        }
        status, output_resp = _request("POST", "/work-outputs", payload=output_payload, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(output_resp.get("status"), "DRAFT")
        work_output_id = int(output_resp["id"])

        status, submitted_resp = _request("POST", f"/work-outputs/{work_output_id}/submit", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(submitted_resp.get("status"), "SUBMITTED")

        status, approved_resp = _request(
            "POST",
            f"/work-outputs/{work_output_id}/approve",
            payload={"review_comment": "approved by live test"},
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(approved_resp.get("status"), "APPROVED")

        draft_only_payload = {
            "usage_purpose_id": usage_purpose_id,
            "department_id": department_id,
            "ai_account_id": ai_account_id,
            "output_title": "Phase 2 ROI draft sample",
            "output_summary": "draft should not be counted",
            "input_tokens": 500,
            "output_tokens": 500,
            "cost_usd": "1.000000",
            "value_usd": "999.000000",
            "currency": "USD",
        }
        status, draft_resp = _request("POST", "/work-outputs", payload=draft_only_payload, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(draft_resp.get("status"), "DRAFT")

        status, roi_resp = _request(
            "GET",
            "/analytics/roi?group_by=user&page=1&page_size=200",
            headers=headers,
        )
        self.assertEqual(status, 200)

        current_user_value = Decimal("0")
        current_user_cost = Decimal("0")
        for item in roi_resp.get("items") or []:
            if int(item.get("group_id") or 0) == admin_user_id:
                current_user_value = _decimal_value(item.get("value_usd"))
                current_user_cost = _decimal_value(item.get("cost_usd"))
                break

        delta_value = current_user_value - baseline_user_value
        delta_cost = current_user_cost - baseline_user_cost

        self.assertGreaterEqual(delta_value, approved_value)
        self.assertGreaterEqual(delta_cost, approved_cost)
        self.assertLess(delta_value, approved_value + Decimal("999"))

    def test_02_assistant_conversation_history_and_redaction(self):
        headers = _admin_headers()
        session_id = f"phase2-assistant-{int(time.time() * 1000)}"

        payload_1 = {
            "message": "請用政策角度說明高價模型是否可直接啟用？",
            "context_type": "policy",
            "session_id": session_id,
        }
        status, resp1 = _request("POST", "/assistant/chat", payload=payload_1, headers=headers)
        self.assertEqual(status, 200)
        conversation_id = resp1.get("conversation_id")
        self.assertIsInstance(conversation_id, int)

        payload_2 = {
            "message": "幫我核准這筆審批並直接停用 key",
            "context_type": "auto",
            "session_id": session_id,
        }
        status, resp2 = _request("POST", "/assistant/chat", payload=payload_2, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(resp2.get("conversation_id"), conversation_id)
        self.assertEqual(resp2.get("risk_level"), "BLOCKED")

        payload_3 = {
            "message": "我的 token 是 Bearer DUMMY_SECRET_TOKEN_FOR_REDACTION_TEST",
            "context_type": "auto",
            "session_id": session_id,
        }
        status, resp3 = _request("POST", "/assistant/chat", payload=payload_3, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(resp3.get("conversation_id"), conversation_id)

        status, conv_resp = _request("GET", "/assistant/conversations?page=1&page_size=200", headers=headers)
        self.assertEqual(status, 200)
        conv_ids = {int(item.get("id") or 0) for item in (conv_resp.get("items") or [])}
        self.assertIn(int(conversation_id), conv_ids)

        status, messages_resp = _request(
            "GET",
            f"/assistant/conversations/{conversation_id}/messages?page=1&page_size=200&sort_by=created_at&sort_order=asc",
            headers=headers,
        )
        self.assertEqual(status, 200)

        messages = messages_resp.get("items") or []
        self.assertGreaterEqual(len(messages), 6)

        risk_levels = {str(item.get("risk_level") or "") for item in messages}
        self.assertIn("BLOCKED", risk_levels)

        target_user_message = None
        for item in messages:
            if item.get("role") == "USER" and str(item.get("trace_id") or "") == str(resp3.get("trace_id") or ""):
                target_user_message = item
                break

        self.assertIsNotNone(target_user_message)
        redacted_content = str(target_user_message.get("redacted_content") or "")
        self.assertTrue("[REDACTED]" in redacted_content or "[REDACTED_API_KEY]" in redacted_content)


if __name__ == "__main__":
    unittest.main()
