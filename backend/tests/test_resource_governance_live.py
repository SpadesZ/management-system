# File Path: backend/tests/test_resource_governance_live.py
# Timestamp: 2026-05-26T21:00:00+08:00
# Version: v0.2

import json
import os
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
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


class ResourceGovernanceLiveTests(unittest.TestCase):
    def test_01_contract_usage_and_limit_flow(self):
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

        owner_user_id = int(admin_user["id"])
        department_id = int(admin_user["department_id"])

        account_payload = {
            "vendor": "openai",
            "product": "chatgpt-enterprise",
            "plan": f"phase1-{int(time.time() * 1000)}",
            "seats": 5,
            "monthly_cost_usd": "200.000000",
            "renewal_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "owner_user_id": owner_user_id,
            "status": "ACTIVE",
        }
        status, account_resp = _request("POST", "/ai-accounts", payload=account_payload, headers=headers)
        self.assertEqual(status, 200)
        ai_account_id = int(account_resp["id"])

        contract_payload = {
            "ai_account_id": ai_account_id,
            "billing_cycle": "YEARLY",
            "yearly_fee_usd": "1200.000000",
            "currency": "USD",
            "start_date": date.today().isoformat(),
            "auto_renew": True,
            "payment_method": "CORP_CARD",
            "status": "ACTIVE",
        }
        status, contract_resp = _request("POST", "/asset-contracts", payload=contract_payload, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(contract_resp.get("ai_account_id"), ai_account_id)
        self.assertEqual(_decimal_value(contract_resp.get("monthly_amortized_usd")), Decimal("100.000000"))

        usage_payload = {
            "ai_account_id": ai_account_id,
            "department_id": department_id,
            "event_source": "MANUAL_IMPORT",
            "external_event_id": f"ai-{int(time.time() * 1000)}",
            "input_tokens": 1200,
            "output_tokens": 300,
            "estimated_cost_usd": "3.500000",
            "currency": "USD",
            "metadata_json": {"source": "live-test"},
        }
        status, usage_resp = _request("POST", "/resource-usage-events", payload=usage_payload, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(usage_resp.get("ai_account_id"), ai_account_id)
        self.assertEqual(int(usage_resp.get("total_tokens") or 0), 1500)

        status, limit_list_resp = _request("GET", "/resource-limits", headers=headers)
        self.assertEqual(status, 200)
        items = limit_list_resp.get("items") or []
        target = None
        for item in items:
            if int(item.get("ai_account_id") or 0) == ai_account_id:
                target = item
                break

        self.assertIsNotNone(target)
        self.assertGreaterEqual(int(target.get("tokens_month") or 0), 1500)

        limit_state_id = int(target["id"])
        status, patched = _request(
            "PATCH",
            f"/resource-limits/{limit_state_id}",
            payload={"limit_month": 1000},
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(int(patched.get("limit_month") or 0), 1000)
        self.assertGreaterEqual(_decimal_value(patched.get("utilization_pct")), Decimal("100"))

    def test_02_ai_account_paid_saas_lifecycle(self):
        headers = _admin_headers()

        status, users_resp = _request("GET", "/users?page=1&page_size=200", headers=headers)
        self.assertEqual(status, 200)
        user_items = users_resp.get("items") or []
        self.assertGreaterEqual(len(user_items), 1)

        owner_user = None
        for item in user_items:
            if str(item.get("email") or "").lower() == "admin@example.com":
                owner_user = item
                break
        if owner_user is None:
            owner_user = user_items[0]

        owner_user_id = int(owner_user["id"])
        unique_suffix = int(time.time() * 1000)

        account_payload = {
            "vendor": "openai",
            "product": "chatgpt-enterprise",
            "plan": f"lifecycle-{unique_suffix}",
            "seats": 2,
            "monthly_cost_usd": "99.000000",
            "renewal_date": (datetime.now(timezone.utc) + timedelta(days=45)).isoformat(),
            "owner_user_id": owner_user_id,
            "status": "ACTIVE",
        }
        status, account_resp = _request("POST", "/ai-accounts", payload=account_payload, headers=headers)
        self.assertEqual(status, 200)
        ai_account_id = int(account_resp["id"])

        credential_name = f"primary-{unique_suffix}"
        credential_payload = {
            "credential_name": credential_name,
            "credential_type": "PASSWORD",
            "plain_secret": f"Secret-{unique_suffix}!",
        }
        status, credential_resp = _request(
            "POST",
            f"/ai-accounts/{ai_account_id}/credentials",
            payload=credential_payload,
            headers=headers,
        )
        self.assertEqual(status, 200)
        credential_id = int(credential_resp["id"])
        self.assertEqual(str(credential_resp.get("credential_name") or ""), credential_name)
        self.assertIn("****", str(credential_resp.get("masked_secret") or ""))

        status, credentials_list = _request(
            "GET",
            f"/ai-accounts/{ai_account_id}/credentials?page=1&page_size=200&sort_by=created_at&sort_order=desc",
            headers=headers,
        )
        self.assertEqual(status, 200)
        credential_ids = [int(item.get("id") or 0) for item in (credentials_list.get("items") or [])]
        self.assertIn(credential_id, credential_ids)

        status, rotated_resp = _request(
            "POST",
            f"/ai-accounts/{ai_account_id}/credentials/{credential_id}/rotate",
            payload={"new_plain_secret": f"Rotated-{unique_suffix}!"},
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertIsNotNone(rotated_resp.get("last_rotated_at"))

        status, disabled_resp = _request(
            "POST",
            f"/ai-accounts/{ai_account_id}/credentials/{credential_id}/disable",
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(str(disabled_resp.get("status") or ""), "DISABLED")

        status, grant_resp = _request(
            "POST",
            f"/ai-accounts/{ai_account_id}/access-grants",
            payload={"user_id": owner_user_id, "grant_reason": "phase2 lifecycle grant"},
            headers=headers,
        )
        self.assertEqual(status, 200)
        grant_id = int(grant_resp["id"])
        self.assertEqual(str(grant_resp.get("status") or ""), "ACTIVE")

        status, grants_list = _request(
            "GET",
            f"/ai-accounts/{ai_account_id}/access-grants?page=1&page_size=200&sort_by=granted_at&sort_order=desc",
            headers=headers,
        )
        self.assertEqual(status, 200)
        active_grant_ids = [int(item.get("id") or 0) for item in (grants_list.get("items") or [])]
        self.assertIn(grant_id, active_grant_ids)

        status, revoke_resp = _request(
            "POST",
            f"/ai-accounts/{ai_account_id}/access-grants/{grant_id}/revoke",
            payload={"revoke_reason": "phase2 lifecycle revoke"},
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(str(revoke_resp.get("status") or ""), "REVOKED")

        status, legacy_assign_resp = _request(
            "POST",
            f"/ai-accounts/{ai_account_id}/assign",
            payload={"user_id": owner_user_id},
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertIsInstance(legacy_assign_resp.get("assignment_id"), int)

        status, legacy_revoke_resp = _request(
            "POST",
            f"/ai-accounts/{ai_account_id}/revoke",
            payload={"user_id": owner_user_id},
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertIsInstance(legacy_revoke_resp.get("assignment_id"), int)

        status, history_resp = _request(
            "GET",
            f"/ai-accounts/{ai_account_id}/history?page=1&page_size=200&sort_by=event_time&sort_order=asc",
            headers=headers,
        )
        self.assertEqual(status, 200)
        event_types = {str(item.get("event_type") or "") for item in (history_resp.get("items") or [])}
        self.assertTrue(
            {
                "ACCOUNT_CREATE",
                "CREDENTIAL_CREATE",
                "CREDENTIAL_ROTATE",
                "CREDENTIAL_DISABLE",
                "ACCESS_GRANT",
                "ACCESS_REVOKE",
            }.issubset(event_types)
        )


if __name__ == "__main__":
    unittest.main()
