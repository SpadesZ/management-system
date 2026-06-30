# File Path: backend/app/api/routers/lava.py
# Timestamp: 2026-05-26T00:00:00+08:00
# Version: v0.1

import os
from typing import Any

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DBSessionDep, require_roles
from app.core.audit import write_audit_log
from app.core.security import security_manager
from app.models.entities import LavaConnection, LavaRuntimeSetting, LavaTaskBinding, User
from app.models.enums import RoleCode
from app.schemas.lava import (
    LavaBindingTask,
    LavaBindingUpdate,
    LavaConnectionTestRequest,
    LavaConnectionUpdate,
    LavaFetchModelsRequest,
    LavaRuntimeCPUUpdate,
    LavaRuntimeWorkersUpdate,
)

router = APIRouter(prefix="/lava", tags=["lava"])

DISALLOWED_OPENROUTER_HINTS = (
    "deepseek",
    "moonshot",
    "kimi",
    "qwen",
    "chatglm",
    "glm",
    "baichuan",
    "internlm",
    "hunyuan",
    "doubao",
    "yi-",
)

# Only tasks that actually invoke an LLM and need model/route/prompt control should be bound in LAVA.
TASK_BINDING_DEFINITIONS = [
    {"task_id": "gateway_chat", "task_name": "聊天請求代理"},
    {"task_id": "approval_request_summarize", "task_name": "審批申請摘要"},
    {"task_id": "cost_anomaly_summarize", "task_name": "成本異常摘要"},
    {"task_id": "usage_policy_qa", "task_name": "用量政策問答"},
    {"task_id": "monthly_report_draft", "task_name": "月報草稿生成"},
    {"task_id": "token_saving_advice", "task_name": "Token 節省建議"},
]
TASK_BINDING_ORDER = [item["task_id"] for item in TASK_BINDING_DEFINITIONS]
TASK_BINDING_ALLOWED = set(TASK_BINDING_ORDER)
TASK_BINDING_NAME_MAP = {item["task_id"]: item["task_name"] for item in TASK_BINDING_DEFINITIONS}
TASK_BINDING_ORDER_MAP = {task_id: idx for idx, task_id in enumerate(TASK_BINDING_ORDER)}
LEGACY_TASK_ID_MAP = {
    "task_2a_chat": "gateway_chat",
    "task_7_qachat": "gateway_chat",
}


def _error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "message": message})


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _mask_secret(secret: str, show_last: int = 4) -> str:
    if not secret:
        return ""
    if len(secret) <= show_last:
        return "*" * len(secret)
    return "*" * (len(secret) - show_last) + secret[-show_last:]


def _encrypt_api_key_for_storage(api_key: str) -> tuple[str, bool]:
    raw = str(api_key or "").strip()
    if not raw:
        return "", False
    try:
        encrypted = security_manager.master_cipher.encrypt(raw.encode("utf-8")).decode("utf-8")
        return encrypted, True
    except Exception:
        return raw, False


def _decrypt_api_key_value(api_key_value: str | None, is_encrypted: bool) -> str:
    raw = str(api_key_value or "")
    if not raw:
        return ""
    if not is_encrypted:
        return raw

    try:
        plain = security_manager.master_cipher.decrypt(raw.encode("utf-8"))
        return plain.decode("utf-8")
    except InvalidToken:
        # Backward-compatible fallback: legacy rows might be plaintext with encrypted flag.
        if not raw.startswith("gAAAA"):
            return raw
        return ""
    except Exception:
        return ""


def _sanitize_connection_for_output(conn: LavaConnection) -> dict[str, Any]:
    plain_api_key = _decrypt_api_key_value(conn.api_key, bool(conn.is_encrypted))
    available_models = conn.available_models_json if isinstance(conn.available_models_json, list) else []

    return {
        "id": conn.id,
        "name": conn.name,
        "vendor": conn.vendor,
        "api_key": _mask_secret(plain_api_key),
        "is_encrypted": bool(conn.is_encrypted),
        "model_name": conn.model_name,
        "available_models": available_models,
        "status": conn.status,
        "created_at": conn.created_at,
        "updated_at": conn.updated_at,
    }


def _get_runtime_setting(db, key: str, default_value: str) -> str:
    row = db.get(LavaRuntimeSetting, key)
    if row is None:
        return default_value
    return str(row.value or default_value)


def _set_runtime_setting(db, key: str, value: str) -> None:
    row = db.get(LavaRuntimeSetting, key)
    if row is None:
        row = LavaRuntimeSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value


def _cpu_limit_info() -> dict[str, int]:
    logical = max(1, int(os.cpu_count() or 1))
    selected = str(os.environ.get("LAVA_CPU_CORES", "")).strip()
    if not selected:
        effective = logical
    else:
        try:
            effective = min(logical, max(1, int(selected)))
        except Exception:
            effective = logical
    return {"logical_cores": logical, "effective_cores": effective}


def _cpu_choices() -> list[dict[str, str]]:
    logical = max(1, int(os.cpu_count() or 1))
    choices = [{"value": "auto", "label": f"Auto (use all {logical} cores)"}]
    for i in range(1, logical + 1):
        choices.append({"value": str(i), "label": f"{i} cores"})
    return choices


def _normalize_cpu_cores(raw_value: Any) -> dict[str, Any]:
    logical = max(1, int(os.cpu_count() or 1))
    value = str(raw_value or "").strip().lower()
    if not value or value in {"auto", "default", "system"}:
        return {"ok": True, "mode": "auto", "value": ""}

    try:
        num = int(value)
    except Exception:
        return {"ok": False, "msg": "cpu_cores must be auto or a positive integer"}

    if num < 1 or num > logical:
        return {"ok": False, "msg": f"cpu_cores must be between 1 and {logical}"}

    return {"ok": True, "mode": "fixed", "value": str(num)}


def _worker_choices() -> list[dict[str, str]]:
    logical = max(1, int(os.cpu_count() or 1))
    return [{"value": str(i), "label": f"{i} worker"} for i in range(1, logical + 1)]


def _normalize_page_workers(raw_value: Any) -> dict[str, Any]:
    logical = max(1, int(os.cpu_count() or 1))
    value = str(raw_value or "").strip()
    if not value:
        return {"ok": False, "msg": "page_workers must be a positive integer"}

    try:
        num = int(value)
    except Exception:
        return {"ok": False, "msg": "page_workers must be a positive integer"}

    if num < 1 or num > logical:
        return {"ok": False, "msg": f"page_workers must be between 1 and {logical}"}

    return {"ok": True, "value": str(num)}


def _is_openrouter_free_model(model_item: dict[str, Any]) -> bool:
    model_id = _normalize_text((model_item or {}).get("id"))
    if not model_id:
        return False
    if ":free" in model_id or model_id.endswith("-free"):
        return True

    pricing = (model_item or {}).get("pricing") or {}
    prompt_price = _to_float_or_none(pricing.get("prompt"))
    completion_price = _to_float_or_none(pricing.get("completion"))
    if prompt_price is None or completion_price is None:
        return False

    return prompt_price <= 0.0 and completion_price <= 0.0


def _is_disallowed_openrouter_model(model_id: str) -> bool:
    text = _normalize_text(model_id)
    return any(hint in text for hint in DISALLOWED_OPENROUTER_HINTS)


def _is_nemotron_model(model_id: str) -> bool:
    return "nemotron" in _normalize_text(model_id)


def _is_openai_model(model_id: str) -> bool:
    text = _normalize_text(model_id)
    return text.startswith("openai/") or "gpt-" in text or "gpt-oss" in text


def _is_claude_model(model_id: str) -> bool:
    text = _normalize_text(model_id)
    return text.startswith("anthropic/") or "claude" in text


def _is_gemini_model(model_id: str) -> bool:
    text = _normalize_text(model_id)
    return text.startswith("google/") or "gemini" in text


def _is_llama_model(model_id: str) -> bool:
    return "llama" in _normalize_text(model_id)


def _get_nemotron_policy(db, conn_id: int | None = None) -> dict[str, Any]:
    conns = db.scalars(select(LavaConnection).order_by(LavaConnection.id.asc())).all()
    total_lines = len(conns)
    max_nemotron = total_lines // 2

    def _conn_is_nemotron(conn_row: LavaConnection) -> bool:
        return _normalize_text(conn_row.vendor) == "openrouter" and _is_nemotron_model(conn_row.model_name or "")

    nemotron_lines = sum(1 for c in conns if _conn_is_nemotron(c))

    target = None
    if conn_id is not None:
        for c in conns:
            if int(c.id) == int(conn_id):
                target = c
                break

    target_is_nemotron = bool(target and _conn_is_nemotron(target))
    projected_nemotron = nemotron_lines if target_is_nemotron else nemotron_lines + 1
    allow_nemotron = projected_nemotron <= max_nemotron

    return {
        "total_lines": total_lines,
        "nemotron_lines": nemotron_lines,
        "max_nemotron": max_nemotron,
        "target_is_nemotron": target_is_nemotron,
        "allow_nemotron": allow_nemotron,
        "projected_nemotron": projected_nemotron,
    }


def _rank_openrouter_free_models(model_items: list[dict[str, Any]], allow_nemotron: bool) -> list[str]:
    bucket_nemotron: list[str] = []
    bucket_openai: list[str] = []
    bucket_claude: list[str] = []
    bucket_gemini: list[str] = []
    bucket_llama: list[str] = []
    bucket_other: list[str] = []

    seen: set[str] = set()
    for item in model_items:
        model_id = str((item or {}).get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)

        if _is_disallowed_openrouter_model(model_id):
            continue
        if not _is_openrouter_free_model(item):
            continue

        if _is_nemotron_model(model_id):
            if allow_nemotron:
                bucket_nemotron.append(model_id)
            continue
        if _is_openai_model(model_id):
            bucket_openai.append(model_id)
            continue
        if _is_claude_model(model_id):
            bucket_claude.append(model_id)
            continue
        if _is_gemini_model(model_id):
            bucket_gemini.append(model_id)
            continue
        if _is_llama_model(model_id):
            bucket_llama.append(model_id)
            continue
        bucket_other.append(model_id)

    return (
        sorted(bucket_nemotron)
        + sorted(bucket_openai)
        + sorted(bucket_claude)
        + sorted(bucket_gemini)
        + sorted(bucket_llama)
        + sorted(bucket_other)
    )


def _extract_http_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        text = (response.text or "").strip()
        return text[:300] if text else f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        if isinstance(error, str):
            return error
        if payload.get("message"):
            return str(payload.get("message"))
    return str(payload)[:300]


def _openrouter_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    referer = str(os.environ.get("OPENROUTER_HTTP_REFERER") or "").strip()
    title = str(os.environ.get("OPENROUTER_X_TITLE") or "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def _fetch_openrouter_models_detail(api_key: str) -> list[dict[str, Any]]:
    base_url = str(os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    response = httpx.get(
        f"{base_url}/models",
        headers=_openrouter_headers(api_key),
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise ValueError(_extract_http_error_message(response))

    payload = response.json()
    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []
    return [m for m in models if isinstance(m, dict)]


def _fetch_openai_models(api_key: str) -> list[str]:
    base_url = str(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    response = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise ValueError(_extract_http_error_message(response))

    payload = response.json()
    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []

    model_ids = [str(item.get("id")) for item in models if isinstance(item, dict) and item.get("id")]
    return sorted(model_ids)


def _fetch_google_models(api_key: str) -> list[str]:
    base_url = str(os.environ.get("GOOGLE_GENAI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    response = httpx.get(
        f"{base_url}/models",
        params={"key": api_key},
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise ValueError(_extract_http_error_message(response))

    payload = response.json()
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []

    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if name.startswith("models/"):
            names.append(name.replace("models/", "", 1))
        else:
            names.append(name)
    return sorted(set(names))


def _fetch_models_by_vendor(vendor: str, api_key: str) -> list[str]:
    vendor_code = _normalize_text(vendor)
    if vendor_code == "openai":
        return _fetch_openai_models(api_key)
    if vendor_code == "google":
        return _fetch_google_models(api_key)
    raise ValueError(f"Vendor {vendor} does not support fetching models")


def _perform_openai_style_test(base_url: str, api_key: str, model_name: str, headers: dict[str, str] | None = None) -> tuple[bool, str]:
    merged_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if headers:
        merged_headers.update(headers)

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Hello, this is a system connection test. Please reply with 'OK'."}],
        "max_tokens": 24,
        "temperature": 0,
    }

    response = httpx.post(f"{base_url.rstrip('/')}/chat/completions", headers=merged_headers, json=payload, timeout=30.0)
    if response.status_code >= 400:
        return False, _extract_http_error_message(response)

    try:
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") if isinstance(first, dict) else {}
            content = message.get("content") if isinstance(message, dict) else ""
            return True, str(content or "")
        return True, "OK"
    except Exception:
        return True, "OK"


def _normalize_google_model_name(model_name: str) -> str:
    raw = str(model_name or "").strip()
    if raw.startswith("models/"):
        return raw
    if raw.startswith("google/"):
        raw = raw.split("/", 1)[1]
    return f"models/{raw}"


def _perform_google_test(api_key: str, model_name: str) -> tuple[bool, str]:
    base_url = str(os.environ.get("GOOGLE_GENAI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    model_path = _normalize_google_model_name(model_name)
    endpoint = f"{base_url}/{model_path}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Hello, this is a system connection test. Please reply with 'OK'.",
                    }
                ]
            }
        ]
    }

    response = httpx.post(endpoint, params={"key": api_key}, json=payload, timeout=30.0)
    if response.status_code >= 400:
        return False, _extract_http_error_message(response)

    try:
        data = response.json()
        candidates = data.get("candidates") if isinstance(data, dict) else None
        if isinstance(candidates, list) and candidates:
            first = candidates[0] if isinstance(candidates[0], dict) else {}
            content = first.get("content") if isinstance(first, dict) else {}
            parts = content.get("parts") if isinstance(content, dict) else []
            if isinstance(parts, list) and parts:
                part = parts[0] if isinstance(parts[0], dict) else {}
                return True, str(part.get("text") or "OK")
        return True, "OK"
    except Exception:
        return True, "OK"


def _test_vendor_connection(vendor: str, api_key: str, model_name: str) -> tuple[bool, str]:
    vendor_code = _normalize_text(vendor)
    if vendor_code == "openrouter":
        base_url = str(os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1")
        return _perform_openai_style_test(base_url, api_key, model_name, headers=_openrouter_headers(api_key))
    if vendor_code == "openai":
        base_url = str(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1")
        return _perform_openai_style_test(base_url, api_key, model_name)
    if vendor_code == "google":
        return _perform_google_test(api_key, model_name)
    return False, f"Unsupported vendor {vendor}"


def _ensure_default_task_bindings(db) -> bool:
    rows = db.scalars(select(LavaTaskBinding)).all()
    existing_map = {row.task_id: row for row in rows}
    changed = False

    migrated_seed: dict[str, dict[str, Any]] = {}
    for legacy_task_id, new_task_id in LEGACY_TASK_ID_MAP.items():
        legacy_row = existing_map.get(legacy_task_id)
        if legacy_row is None:
            continue
        if new_task_id in existing_map:
            continue
        migrated_seed[new_task_id] = {
            "connection_id": legacy_row.connection_id,
            "is_locked": bool(legacy_row.is_locked),
        }

    for row in rows:
        if row.task_id not in TASK_BINDING_ALLOWED:
            db.delete(row)
            changed = True

    for task_id in TASK_BINDING_ORDER:
        if task_id not in existing_map:
            seeded = migrated_seed.get(task_id)
            db.add(
                LavaTaskBinding(
                    task_id=task_id,
                    connection_id=seeded.get("connection_id") if seeded else None,
                    is_locked=seeded.get("is_locked") if seeded else False,
                )
            )
            changed = True

    return changed


@router.get("/connection/list")
def list_connections(db: DBSessionDep, _: CurrentUserDep) -> dict[str, Any]:
    conns = db.scalars(select(LavaConnection).order_by(LavaConnection.id.asc())).all()
    return {"success": True, "connections": [_sanitize_connection_for_output(c) for c in conns]}


@router.post("/connection/create")
def create_connection(
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    conn = LavaConnection(
        name="New Connection",
        vendor="openrouter",
        api_key="",
        is_encrypted=False,
        model_name="",
        available_models_json=[],
        status="draft",
    )
    db.add(conn)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_CONNECTION_CREATE",
        resource_type="lava_connections",
        resource_id=str(conn.id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"id": conn.id, "vendor": conn.vendor, "status": conn.status},
    )

    db.commit()
    db.refresh(conn)
    return {"success": True, "connection": _sanitize_connection_for_output(conn)}


@router.delete("/connection/{conn_id}")
def delete_connection(
    conn_id: int,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    conn = db.get(LavaConnection, conn_id)
    if conn is None:
        return _error_response("Connection not found", 404)

    bindings = db.scalars(select(LavaTaskBinding).where(LavaTaskBinding.connection_id == conn.id)).all()
    for binding in bindings:
        binding.connection_id = None
        binding.is_locked = False

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_CONNECTION_DELETE",
        resource_type="lava_connections",
        resource_id=str(conn.id),
        source="API",
        ip_address=None,
        before_json={"id": conn.id, "name": conn.name, "vendor": conn.vendor},
        after_json=None,
    )

    db.delete(conn)
    db.commit()
    return {"success": True, "message": f"Connection {conn_id} deleted."}


@router.post("/connection/update")
def update_connection(
    payload: LavaConnectionUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    conn = db.get(LavaConnection, payload.id)
    if conn is None:
        return _error_response("Connection not found", 404)

    vendor = str(payload.vendor or conn.vendor or "openrouter").strip() or "openrouter"
    model_name = str(payload.model_name if payload.model_name is not None else (conn.model_name or "")).strip()

    if _normalize_text(vendor) == "openrouter" and _is_nemotron_model(model_name):
        policy = _get_nemotron_policy(db, conn_id=conn.id)
        if not policy.get("allow_nemotron"):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Nemotron 線路比例不可超過一半，請改用 OpenAI/Claude/Gemini 免費模型。",
                    "policy": policy,
                },
            )

    before = {
        "name": conn.name,
        "vendor": conn.vendor,
        "model_name": conn.model_name,
        "status": conn.status,
    }

    if payload.name is not None and payload.name.strip():
        conn.name = payload.name.strip()
    conn.vendor = vendor
    conn.model_name = model_name
    conn.status = str(payload.status or conn.status or "draft").strip() or "draft"

    if payload.available_models is not None:
        conn.available_models_json = payload.available_models

    if payload.api_key is not None:
        raw_api_key = payload.api_key.strip()
        if not raw_api_key:
            conn.api_key = ""
            conn.is_encrypted = False
        else:
            stored_api_key, is_encrypted = _encrypt_api_key_for_storage(raw_api_key)
            conn.api_key = stored_api_key
            conn.is_encrypted = bool(is_encrypted)

    db.flush()
    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_CONNECTION_UPDATE",
        resource_type="lava_connections",
        resource_id=str(conn.id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json={"name": conn.name, "vendor": conn.vendor, "model_name": conn.model_name, "status": conn.status},
    )

    db.commit()
    return {"success": True}


@router.post("/connection/fetch-models")
def fetch_models(
    payload: LavaFetchModelsRequest,
    db: DBSessionDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    vendor = str(payload.vendor or "openrouter").strip() or "openrouter"
    conn = db.get(LavaConnection, payload.conn_id) if payload.conn_id is not None else None

    api_key = (payload.api_key or "").strip()
    if not api_key and conn is not None:
        api_key = _decrypt_api_key_value(conn.api_key, bool(conn.is_encrypted)).strip()
    if not api_key:
        return _error_response("API Key is required", 400)

    try:
        if _normalize_text(vendor) == "openrouter":
            detail_models = _fetch_openrouter_models_detail(api_key)
            policy = _get_nemotron_policy(db, conn_id=payload.conn_id)

            models: list[dict[str, Any]] = []
            for item in detail_models:
                model_id = str(item.get("id") or "").strip()
                if not model_id:
                    continue
                models.append(
                    {
                        "id": model_id,
                        "name": str(item.get("name") or model_id),
                        "is_free": _is_openrouter_free_model(item),
                    }
                )

            models.sort(key=lambda x: (0 if x.get("is_free") else 1, str(x.get("id") or "")))
            if not models:
                fallback = _rank_openrouter_free_models(detail_models, allow_nemotron=bool(policy.get("allow_nemotron")))
                models = [{"id": item, "name": item, "is_free": True} for item in fallback]

            if conn is not None:
                conn.available_models_json = models
                db.commit()

            return {"success": True, "models": models, "policy": policy}

        models = _fetch_models_by_vendor(vendor, api_key)
        if not models:
            return _error_response("找不到可用模型或 API Key 無效。", 400)

        if conn is not None:
            conn.available_models_json = models
            db.commit()

        return {"success": True, "models": models}
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except Exception:
        return _error_response("Fetch models failed", 500)


@router.post("/connection/test")
def test_connection(
    payload: LavaConnectionTestRequest,
    db: DBSessionDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    conn = db.get(LavaConnection, payload.conn_id) if payload.conn_id is not None else None

    vendor = str(payload.vendor or (conn.vendor if conn else "openrouter")).strip() or "openrouter"
    api_key = (payload.api_key or "").strip()
    if not api_key and conn is not None:
        api_key = _decrypt_api_key_value(conn.api_key, bool(conn.is_encrypted)).strip()

    model_name = str(payload.model_name or (conn.model_name if conn else "")).strip()

    if not api_key or not model_name:
        return _error_response("Missing API Key or Model Name", 400)

    ok, message = _test_vendor_connection(vendor, api_key, model_name)
    if ok:
        return {"success": True, "message": "Connection successful! API is active.", "reply": message}
    return _error_response(f"Test failed: {message}", 500)


@router.get("/binding/list")
def list_bindings(db: DBSessionDep, _: CurrentUserDep) -> dict[str, Any]:
    changed = _ensure_default_task_bindings(db)
    if changed:
        db.commit()

    bindings = db.scalars(select(LavaTaskBinding)).all()
    bindings = sorted(
        bindings,
        key=lambda row: (
            TASK_BINDING_ORDER_MAP.get(str(row.task_id or ""), 10_000),
            str(row.task_id or ""),
        ),
    )

    return {
        "success": True,
        "bindings": [
            {
                "task_id": row.task_id,
                "task_name": TASK_BINDING_NAME_MAP.get(str(row.task_id or ""), str(row.task_id or "")),
                "connection_id": row.connection_id,
                "is_locked": bool(row.is_locked),
            }
            for row in bindings
        ],
    }


@router.post("/binding/update")
def update_binding(
    payload: LavaBindingUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    if payload.task_id not in TASK_BINDING_ALLOWED:
        return _error_response("Unsupported task_id", 400)

    changed = _ensure_default_task_bindings(db)
    if changed:
        db.flush()

    binding = db.get(LavaTaskBinding, payload.task_id)
    if binding is None:
        binding = LavaTaskBinding(task_id=payload.task_id, connection_id=None, is_locked=False)
        db.add(binding)
        db.flush()

    if bool(binding.is_locked):
        return _error_response("Binding is locked", 400)

    if payload.connection_id is not None:
        conn = db.get(LavaConnection, payload.connection_id)
        if conn is None:
            return _error_response("Connection not found", 404)

    before = {"connection_id": binding.connection_id, "is_locked": bool(binding.is_locked)}
    binding.connection_id = payload.connection_id

    db.flush()
    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_BINDING_UPDATE",
        resource_type="lava_task_bindings",
        resource_id=str(binding.task_id),
        source="API",
        ip_address=None,
        before_json=before,
        after_json={"connection_id": binding.connection_id, "is_locked": bool(binding.is_locked)},
    )

    db.commit()
    return {"success": True}


@router.post("/binding/lock")
def lock_binding(
    payload: LavaBindingTask,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    if payload.task_id not in TASK_BINDING_ALLOWED:
        return _error_response("Unsupported task_id", 400)

    changed = _ensure_default_task_bindings(db)
    if changed:
        db.flush()

    binding = db.get(LavaTaskBinding, payload.task_id)
    if binding is None:
        binding = LavaTaskBinding(task_id=payload.task_id, connection_id=None, is_locked=False)
        db.add(binding)

    binding.is_locked = True

    db.flush()
    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_BINDING_LOCK",
        resource_type="lava_task_bindings",
        resource_id=str(binding.task_id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"is_locked": True},
    )

    db.commit()
    return {"success": True}


@router.post("/binding/unlock")
def unlock_binding(
    payload: LavaBindingTask,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    if payload.task_id not in TASK_BINDING_ALLOWED:
        return _error_response("Unsupported task_id", 400)

    changed = _ensure_default_task_bindings(db)
    if changed:
        db.flush()

    binding = db.get(LavaTaskBinding, payload.task_id)
    if binding is None:
        binding = LavaTaskBinding(task_id=payload.task_id, connection_id=None, is_locked=False)
        db.add(binding)

    binding.is_locked = False

    db.flush()
    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_BINDING_UNLOCK",
        resource_type="lava_task_bindings",
        resource_id=str(binding.task_id),
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"is_locked": False},
    )

    db.commit()
    return {"success": True}


@router.post("/binding/test")
def test_binding(payload: LavaBindingTask, db: DBSessionDep, _: CurrentUserDep) -> dict[str, Any]:
    binding = db.get(LavaTaskBinding, payload.task_id)
    if binding is None or binding.connection_id is None:
        return _error_response("Binding has no connection", 400)

    conn = db.get(LavaConnection, binding.connection_id)
    if conn is None:
        return _error_response("Connection not found", 404)

    api_key = _decrypt_api_key_value(conn.api_key, bool(conn.is_encrypted)).strip()
    model_name = str(conn.model_name or "").strip()
    if not api_key or not model_name:
        return _error_response("Bound connection has no API key or model", 400)

    ok, message = _test_vendor_connection(conn.vendor, api_key, model_name)
    if ok:
        preview = str(message or "").replace("\n", " ")[:50]
        return {"success": True, "message": f'Verified! LLM replied: "{preview}..."'}
    return _error_response(f"Test Failed: {message}", 500)


@router.get("/runtime/cpu")
def get_runtime_cpu(db: DBSessionDep, _: CurrentUserDep) -> dict[str, Any]:
    saved = str(_get_runtime_setting(db, "LAVA_CPU_CORES", "auto") or "auto").strip().lower()
    if saved in {"", "none"}:
        saved = "auto"

    current = str(os.environ.get("LAVA_CPU_CORES", "")).strip()
    selected = current if current else saved

    return {
        "ok": True,
        "choices": _cpu_choices(),
        "saved_value": saved,
        "selected_value": selected,
        "cpu_limit": _cpu_limit_info(),
    }


@router.post("/runtime/cpu")
def set_runtime_cpu(
    payload: LavaRuntimeCPUUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    normalized = _normalize_cpu_cores(payload.cpu_cores)
    if not normalized.get("ok"):
        return JSONResponse(status_code=400, content={"ok": False, "msg": normalized.get("msg", "invalid cpu_cores")})

    mode = normalized.get("mode")
    value = str(normalized.get("value") or "")

    if mode == "auto":
        os.environ.pop("LAVA_CPU_CORES", None)
        _set_runtime_setting(db, "LAVA_CPU_CORES", "auto")
        selected = "auto"
    else:
        os.environ["LAVA_CPU_CORES"] = value
        _set_runtime_setting(db, "LAVA_CPU_CORES", value)
        selected = value

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_RUNTIME_CPU_UPDATE",
        resource_type="lava_runtime_settings",
        resource_id="LAVA_CPU_CORES",
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"selected_value": selected},
    )

    db.commit()
    return {
        "ok": True,
        "msg": "CPU core setting updated",
        "selected_value": selected,
        "cpu_limit": _cpu_limit_info(),
    }


@router.get("/runtime/flowa_workers")
def get_runtime_flowa_workers(db: DBSessionDep, _: CurrentUserDep) -> dict[str, Any]:
    logical = max(1, int(os.cpu_count() or 1))

    saved = str(_get_runtime_setting(db, "LAVA_PAGE_WORKERS", "1") or "1").strip() or "1"
    current = str(os.environ.get("LAVA_PAGE_WORKERS", saved)).strip() or "1"

    try:
        requested = max(1, int(current))
    except Exception:
        requested = 1

    effective = min(requested, logical)
    return {
        "ok": True,
        "choices": _worker_choices(),
        "saved_value": saved,
        "selected_value": str(requested),
        "effective_workers": int(effective),
        "cpu_limit": _cpu_limit_info(),
    }


@router.post("/runtime/flowa_workers")
def set_runtime_flowa_workers(
    payload: LavaRuntimeWorkersUpdate,
    db: DBSessionDep,
    actor: User = Depends(require_roles(RoleCode.ADMIN.value, RoleCode.SECURITY.value)),
) -> dict[str, Any]:
    normalized = _normalize_page_workers(payload.page_workers)
    if not normalized.get("ok"):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "msg": normalized.get("msg", "invalid page_workers")},
        )

    logical = max(1, int(os.cpu_count() or 1))
    requested = max(1, int(normalized.get("value")))
    effective = min(requested, logical)

    os.environ["LAVA_PAGE_WORKERS"] = str(requested)
    os.environ["LAVA_EFFECTIVE_WORKERS"] = str(effective)

    _set_runtime_setting(db, "LAVA_PAGE_WORKERS", str(requested))
    _set_runtime_setting(db, "LAVA_EFFECTIVE_WORKERS", str(effective))

    write_audit_log(
        db,
        actor_user_id=actor.id,
        action="LAVA_RUNTIME_WORKERS_UPDATE",
        resource_type="lava_runtime_settings",
        resource_id="LAVA_PAGE_WORKERS",
        source="API",
        ip_address=None,
        before_json=None,
        after_json={"selected_value": str(requested), "effective_workers": int(effective)},
    )

    db.commit()
    return {
        "ok": True,
        "msg": "Flow A workers setting updated",
        "selected_value": str(requested),
        "effective_workers": int(effective),
        "cpu_limit": _cpu_limit_info(),
    }
