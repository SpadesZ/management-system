# File Path: backend/app/services/assistant.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.2

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import security_manager
from app.models.entities import (
    ApprovalRequest,
    Alert,
    AssistantConversation,
    AssistantMessage,
    CostLedger,
    LavaConnection,
    LavaTaskBinding,
    UsageEvent,
    User,
)
from app.models.enums import RoleCode
from app.schemas.assistant import AssistantAction, AssistantSource
from app.services.scope_filter import allowed_department_ids, apply_department_scope, get_scope_context

TASK_BINDING_ALLOWED: set[str] = {
    "gateway_chat",
    "approval_request_summarize",
    "cost_anomaly_summarize",
    "usage_policy_qa",
    "monthly_report_draft",
    "token_saving_advice",
}

BLOCKED_INTENT_HINTS: tuple[str, ...] = (
    "幫我核准",
    "幫我批准",
    "approve this",
    "approve request",
    "幫我拒絕",
    "reject this",
    "停用 key",
    "disable key",
    "刪除 key",
    "delete key",
    "解密 key",
    "decrypt key",
    "調高預算",
    "increase budget",
    "raise budget",
    "修改預算上限",
)

HIGH_RISK_HINTS: tuple[str, ...] = (
    "明文 key",
    "export secret",
    "匯出密鑰",
    "繞過審批",
    "bypass approval",
    "root token",
)

MEDIUM_RISK_HINTS: tuple[str, ...] = (
    "成本",
    "預算",
    "approval",
    "審批",
    "policy",
    "政策",
    "anomaly",
    "異常",
)

POLICY_SNIPPETS: list[dict[str, str]] = [
    {
        "id": "policy-readonly-001",
        "title": "助理只讀原則",
        "content": "Ask FinOps 僅提供查詢、摘要與建議，不可直接執行核准、拒絕、停用、刪除或預算調整。",
    },
    {
        "id": "policy-approval-001",
        "title": "審批責任分離",
        "content": "審批請求需由有權限的人員於審批流程中人工決策，LLM 僅可提供摘要與風險提示。",
    },
    {
        "id": "policy-secret-001",
        "title": "敏感資料保護",
        "content": "系統不得回傳明文 API Key 或任何可用來重建密鑰的資訊。",
    },
    {
        "id": "policy-budget-001",
        "title": "預算變更流程",
        "content": "預算或配額變更必須走正式申請與審批流程，不可由對話直接變更。",
    },
    {
        "id": "policy-model-001",
        "title": "模型使用治理",
        "content": "高成本模型使用需符合部門策略與成本治理規範，異常使用需提供說明與優化計畫。",
    },
]

SESSION_ID_PREFIX = "assistant-session"
EXPIRED_REDACTION_PLACEHOLDER = "[REDACTED_EXPIRED]"

SENSITIVE_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)bearer\s+[a-z0-9._\-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)sk-[a-z0-9]{12,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([\"']?)[^\s,\"']+\2"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(token\s*[:=]\s*)([\"']?)[^\s,\"']+\2"), r"\1[REDACTED]"),
)


class AssistantError(Exception):
    pass


class AssistantInputError(AssistantError):
    pass


class AssistantConfigError(AssistantError):
    pass


class AssistantProviderError(AssistantError):
    pass


@dataclass
class BoundConnection:
    task_id: str
    connection_id: int
    vendor: str
    model_name: str
    api_key: str


def hash_message(message: str) -> str:
    return sha256(str(message or "").encode("utf-8")).hexdigest()


def summarize_answer(answer: str, limit: int = 300) -> str:
    return str(answer or "").replace("\n", " ").strip()[:limit]


def normalize_session_id(session_id: str | None, trace_id: str) -> str:
    candidate = str(session_id or "").strip()
    if candidate:
        return candidate[:128]
    return f"{SESSION_ID_PREFIX}-{trace_id}"[:128]


def redact_sensitive_text(text: str) -> str:
    redacted = str(text or "")
    for pattern, replacement in SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted[:6000]


def _parse_linked_approval_request_id(context_type: str, context_id: str | None) -> int | None:
    if _normalize_text(context_type) != "approval_request":
        return None
    if context_id is None or str(context_id).strip() == "":
        return None
    try:
        return int(str(context_id).strip())
    except Exception:
        return None


def get_or_create_assistant_conversation(
    db: Session,
    current_user: User,
    *,
    session_id: str,
    context_type: str,
    context_id: str | None,
) -> AssistantConversation:
    conversation = db.scalar(
        select(AssistantConversation).where(
            AssistantConversation.user_id == current_user.id,
            AssistantConversation.session_id == session_id,
        )
    )

    linked_approval_request_id = _parse_linked_approval_request_id(context_type, context_id)

    if conversation is None:
        conversation = AssistantConversation(
            user_id=current_user.id,
            session_id=session_id,
            intent=_normalize_text(context_type) or "auto",
            status="OPEN",
            linked_approval_request_id=linked_approval_request_id,
            last_message_at=datetime.now(UTC),
            metadata_json={},
        )
        db.add(conversation)
        db.flush()
        return conversation

    if conversation.status == "CLOSED":
        conversation.status = "OPEN"
        conversation.closed_at = None
    if linked_approval_request_id is not None and conversation.linked_approval_request_id is None:
        conversation.linked_approval_request_id = linked_approval_request_id
    conversation.last_message_at = datetime.now(UTC)
    db.flush()
    return conversation


def append_assistant_message(
    db: Session,
    *,
    conversation: AssistantConversation,
    role: str,
    content: str,
    message_hash_value: str,
    task_ids: list[str] | None = None,
    sources: list[AssistantSource] | None = None,
    risk_level: str | None = None,
    trace_id: str | None = None,
    metadata_json: dict | None = None,
) -> AssistantMessage:
    source_payload: list[dict] = []
    for item in sources or []:
        source_payload.append(item.model_dump(mode="json"))

    entity = AssistantMessage(
        conversation_id=conversation.id,
        role=str(role).upper(),
        redacted_content=redact_sensitive_text(content),
        message_hash=message_hash_value,
        task_ids_json=list(task_ids or []),
        sources_json=source_payload,
        risk_level=risk_level,
        trace_id=trace_id,
        metadata_json=metadata_json or {},
    )
    db.add(entity)

    conversation.last_message_at = datetime.now(UTC)
    if risk_level is not None:
        conversation.last_risk_level = risk_level

    db.flush()
    return entity


def cleanup_expired_assistant_messages(
    db: Session,
    *,
    now: datetime | None = None,
    retention_days: int = 180,
) -> int:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)

    cutoff = current - timedelta(days=max(1, int(retention_days)))

    candidates = db.scalars(
        select(AssistantMessage).where(
            AssistantMessage.created_at < cutoff,
            AssistantMessage.redacted_content != EXPIRED_REDACTION_PLACEHOLDER,
        )
    ).all()

    if not candidates:
        return 0

    for message in candidates:
        message.redacted_content = EXPIRED_REDACTION_PLACEHOLDER
        metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
        metadata["retention_redacted_at"] = current.isoformat()
        message.metadata_json = metadata

    db.flush()
    return len(candidates)


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def detect_risk_level(message: str) -> tuple[str, str | None]:
    text = _normalize_text(message)
    if any(hint in text for hint in BLOCKED_INTENT_HINTS):
        return "BLOCKED", "此請求涉及高風險狀態變更，系統僅提供只讀建議。"

    if any(hint in text for hint in HIGH_RISK_HINTS):
        return "HIGH", None

    if any(hint in text for hint in MEDIUM_RISK_HINTS):
        return "MEDIUM", None

    return "LOW", None


def route_tasks(message: str, context_type: str) -> list[str]:
    text = _normalize_text(message)
    context_code = _normalize_text(context_type) or "auto"
    tasks: list[str] = []

    def add_task(task_id: str) -> None:
        if task_id in TASK_BINDING_ALLOWED and task_id not in tasks:
            tasks.append(task_id)

    if context_code == "approval_request":
        add_task("approval_request_summarize")
    if context_code == "policy":
        add_task("usage_policy_qa")
    if context_code in {"costs", "usage", "alerts"}:
        add_task("cost_anomaly_summarize")

    approval_hints = ("approval", "審批", "審核", "申請摘要")
    policy_hints = ("policy", "政策", "允不允許", "可不可以", "是否可以", "規範")
    anomaly_hints = ("異常", "anomaly", "變高", "飆高", "spike", "為什麼")
    saving_hints = ("節省", "省 token", "省token", "優化", "optimize", "saving")
    monthly_hints = ("月報", "monthly report", "本月報告", "草稿")

    if any(hint in text for hint in approval_hints):
        add_task("approval_request_summarize")

    if any(hint in text for hint in policy_hints):
        add_task("usage_policy_qa")

    if any(hint in text for hint in anomaly_hints):
        add_task("cost_anomaly_summarize")

    if any(hint in text for hint in saving_hints):
        add_task("token_saving_advice")

    if any(hint in text for hint in monthly_hints):
        add_task("monthly_report_draft")

    if "cost_anomaly_summarize" in tasks and "token_saving_advice" not in tasks:
        add_task("token_saving_advice")

    if not tasks:
        add_task("gateway_chat")

    return tasks


def _month_range() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    return start, now


def _to_decimal_text(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    return str(Decimal(str(value)))


def _build_cost_summary(db: Session, allowed_ids: list[int] | None) -> dict[str, Any]:
    start_at, end_at = _month_range()

    summary_stmt = select(
        func.count(CostLedger.id),
        func.coalesce(func.sum(CostLedger.input_tokens + CostLedger.output_tokens), 0),
        func.coalesce(func.sum(CostLedger.settled_cost), 0),
    ).where(CostLedger.created_at >= start_at, CostLedger.created_at <= end_at)

    if allowed_ids is not None:
        summary_stmt = summary_stmt.where(CostLedger.department_id.in_(allowed_ids))

    summary_row = db.execute(summary_stmt).one()

    top_model_stmt = (
        select(CostLedger.model_id, func.coalesce(func.sum(CostLedger.settled_cost), 0).label("total_cost"))
        .where(CostLedger.created_at >= start_at, CostLedger.created_at <= end_at)
        .group_by(CostLedger.model_id)
        .order_by(desc(func.coalesce(func.sum(CostLedger.settled_cost), 0)))
        .limit(3)
    )
    if allowed_ids is not None:
        top_model_stmt = top_model_stmt.where(CostLedger.department_id.in_(allowed_ids))

    top_department_stmt = (
        select(CostLedger.department_id, func.coalesce(func.sum(CostLedger.settled_cost), 0).label("total_cost"))
        .where(CostLedger.created_at >= start_at, CostLedger.created_at <= end_at)
        .group_by(CostLedger.department_id)
        .order_by(desc(func.coalesce(func.sum(CostLedger.settled_cost), 0)))
        .limit(3)
    )
    if allowed_ids is not None:
        top_department_stmt = top_department_stmt.where(CostLedger.department_id.in_(allowed_ids))

    top_models = [
        {"model_id": int(row[0]), "total_cost_usd": _to_decimal_text(row[1])}
        for row in db.execute(top_model_stmt).all()
    ]
    top_departments = [
        {"department_id": int(row[0]), "total_cost_usd": _to_decimal_text(row[1])}
        for row in db.execute(top_department_stmt).all()
    ]

    return {
        "range_start": start_at.isoformat(),
        "range_end": end_at.isoformat(),
        "request_count": int(summary_row[0] or 0),
        "total_tokens": int(summary_row[1] or 0),
        "total_cost_usd": _to_decimal_text(summary_row[2]),
        "top_models": top_models,
        "top_departments": top_departments,
    }


def _build_usage_snapshot(db: Session, allowed_ids: list[int] | None) -> list[dict[str, Any]]:
    start_at, end_at = _month_range()

    stmt = select(
        UsageEvent.request_id,
        UsageEvent.created_at,
        UsageEvent.total_tokens,
        UsageEvent.estimated_cost_usd,
        UsageEvent.status,
        UsageEvent.model_id,
        UsageEvent.department_id,
    ).where(UsageEvent.created_at >= start_at, UsageEvent.created_at <= end_at)

    stmt = apply_department_scope(stmt, UsageEvent.department_id, allowed_ids)
    stmt = stmt.order_by(desc(UsageEvent.created_at)).limit(8)

    rows = db.execute(stmt).all()
    return [
        {
            "request_id": str(row[0]),
            "created_at": row[1].isoformat() if row[1] else None,
            "total_tokens": int(row[2] or 0),
            "estimated_cost_usd": _to_decimal_text(row[3]),
            "status": str(row[4] or ""),
            "model_id": int(row[5] or 0),
            "department_id": int(row[6] or 0),
        }
        for row in rows
    ]


def _build_alert_snapshot(db: Session, allowed_ids: list[int] | None) -> list[dict[str, Any]]:
    stmt = (
        select(Alert.id, Alert.severity, Alert.title, Alert.scope_type, Alert.scope_id, Alert.triggered_at)
        .where(Alert.status.in_(["OPEN", "ACKNOWLEDGED"]))
        .order_by(desc(Alert.triggered_at))
        .limit(8)
    )

    if allowed_ids is not None:
        stmt = stmt.where(
            or_(
                Alert.scope_type.is_(None),
                and_(Alert.scope_type == "DEPARTMENT", Alert.scope_id.in_(allowed_ids)),
            )
        )

    rows = db.execute(stmt).all()
    return [
        {
            "id": int(row[0]),
            "severity": str(row[1] or ""),
            "title": str(row[2] or ""),
            "scope_type": str(row[3] or ""),
            "scope_id": int(row[4]) if row[4] is not None else None,
            "triggered_at": row[5].isoformat() if row[5] else None,
        }
        for row in rows
    ]


def _build_approval_context(db: Session, current_user: User, context_id: str | None) -> dict[str, Any] | None:
    if context_id is None or str(context_id).strip() == "":
        return None

    try:
        approval_id = int(str(context_id).strip())
    except Exception as exc:
        raise AssistantInputError("context_id 必須是可解析的審批單號") from exc

    approval = db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise AssistantInputError("找不到指定的審批申請")

    privileged_roles = {RoleCode.ADMIN.value, RoleCode.MANAGER.value, RoleCode.FINANCE.value}
    if current_user.role not in privileged_roles and int(approval.requester_id) != int(current_user.id):
        raise AssistantInputError("目前無權限查看此審批申請")

    return {
        "id": int(approval.id),
        "requester_id": int(approval.requester_id),
        "request_type": str(approval.request_type or ""),
        "target_type": str(approval.target_type or ""),
        "target_id": int(approval.target_id) if approval.target_id is not None else None,
        "reason": str(approval.reason or ""),
        "status": str(approval.status or ""),
        "submitted_at": approval.submitted_at.isoformat() if approval.submitted_at else None,
        "resolved_at": approval.resolved_at.isoformat() if approval.resolved_at else None,
        "payload_json": approval.payload_json if isinstance(approval.payload_json, dict) else {},
    }


def build_context_bundle(
    db: Session,
    current_user: User,
    context_type: str,
    context_id: str | None,
) -> tuple[dict[str, Any], list[AssistantSource]]:
    context_code = _normalize_text(context_type) or "auto"
    context = get_scope_context(current_user)
    allowed_ids = allowed_department_ids(db, context)

    bundle: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "context_type": context_code,
        "user_scope": {
            "user_id": int(current_user.id),
            "role": str(current_user.role),
            "department_id": int(current_user.department_id),
            "allowed_department_ids": allowed_ids if allowed_ids is not None else "ALL",
        },
    }

    sources: list[AssistantSource] = []

    costs_summary = _build_cost_summary(db, allowed_ids)
    bundle["costs_summary"] = costs_summary
    sources.append(
        AssistantSource(
            source_key="costs.summary",
            source_label="當月成本彙總",
            source_id=costs_summary.get("range_start"),
            scope_checked=True,
        )
    )

    usage_snapshot = _build_usage_snapshot(db, allowed_ids)
    bundle["usage_snapshot"] = usage_snapshot
    sources.append(
        AssistantSource(
            source_key="usage_events.recent",
            source_label="近期用量事件",
            source_id=str(len(usage_snapshot)),
            scope_checked=True,
        )
    )

    alerts = _build_alert_snapshot(db, allowed_ids)
    bundle["alerts"] = alerts
    sources.append(
        AssistantSource(
            source_key="alerts.open",
            source_label="告警中心（OPEN/ACKNOWLEDGED）",
            source_id=str(len(alerts)),
            scope_checked=True,
        )
    )

    if context_code in {"auto", "policy"}:
        bundle["policy_snippets"] = POLICY_SNIPPETS
        sources.append(
            AssistantSource(
                source_key="policy.snippets",
                source_label="治理政策片段",
                source_id=str(len(POLICY_SNIPPETS)),
                scope_checked=True,
            )
        )

    approval_context = None
    if context_code in {"auto", "approval_request"} and context_id is not None:
        approval_context = _build_approval_context(db, current_user, context_id)

    if approval_context is not None:
        bundle["approval_request"] = approval_context
        sources.append(
            AssistantSource(
                source_key="approval_requests.detail",
                source_label="審批申請內容",
                source_id=str(approval_context.get("id")),
                scope_checked=True,
            )
        )

    return bundle, sources


def build_blocked_answer(blocked_reason: str | None) -> str:
    reason = (blocked_reason or "此請求涉及高風險狀態變更").rstrip("。.!！")
    return (
        f"{reason}。Ask FinOps 僅提供只讀分析與建議。\n"
        "請改走人工流程：\n"
        "1. 於 Approvals 建立或處理正式申請。\n"
        "2. 由具權限人員核准/拒絕。\n"
        "3. 將助理建議作為審批參考，而非直接執行。"
    )


def _build_task_instruction(primary_task_id: str) -> str:
    instruction_map = {
        "gateway_chat": "提供 FinOps 問答，並附可操作的治理建議。",
        "approval_request_summarize": "請輸出審批摘要：背景、風險、待確認事項，不得替代核准/拒絕。",
        "cost_anomaly_summarize": "請分析成本異常：時間區段、可能原因、影響範圍、建議查核清單。",
        "usage_policy_qa": "請引用政策片段回答，若政策不足請明確說明不確定性。",
        "monthly_report_draft": "請產出可複製的月報草稿：摘要、數據重點、風險、下月建議。",
        "token_saving_advice": "請提供可執行的 token 節省建議，並標示預期影響。",
    }
    return instruction_map.get(primary_task_id, instruction_map["gateway_chat"])


def _build_prompt(primary_task_id: str, task_ids: list[str], message: str, context_bundle: dict[str, Any]) -> tuple[str, str]:
    context_json = json.dumps(context_bundle, ensure_ascii=False, default=str)
    if len(context_json) > 12000:
        context_json = context_json[:12000]

    system_prompt = (
        "你是 Ask FinOps 助理。"
        "你只能做只讀分析與建議，不可執行任何狀態變更。"
        "不得提供明文密鑰、解密資訊、核准/拒絕/停用/刪除/改預算的直接操作指令。"
        f"目前主要任務：{primary_task_id}；關聯任務：{', '.join(task_ids)}。"
        f"任務指示：{_build_task_instruction(primary_task_id)}"
    )

    user_prompt = (
        "請依照以下提問與上下文回答，回答格式需清楚分段：\n"
        "- 重點結論\n"
        "- 依據（引用上下文）\n"
        "- 建議下一步（只讀/流程建議）\n\n"
        f"使用者問題：{message}\n\n"
        f"上下文(JSON)：{context_json}"
    )

    return system_prompt, user_prompt


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
        if not raw.startswith("gAAAA"):
            return raw
        return ""
    except Exception:
        return ""


def _resolve_bound_connection(db: Session, task_id: str) -> BoundConnection:
    binding = db.get(LavaTaskBinding, task_id)
    if binding is None or binding.connection_id is None:
        raise AssistantConfigError(f"{task_id} 尚未綁定可用 Connection，請先至 LAVA Setup 完成綁定。")

    conn = db.get(LavaConnection, binding.connection_id)
    if conn is None:
        raise AssistantConfigError(f"{task_id} 綁定的 Connection 不存在，請重新設定。")

    if _normalize_text(conn.status) == "disabled":
        raise AssistantConfigError(f"{task_id} 綁定的 Connection 已停用，請更換可用線路。")

    model_name = str(conn.model_name or "").strip()
    if not model_name:
        raise AssistantConfigError(f"{task_id} 綁定的 Connection 尚未設定模型。")

    api_key = _decrypt_api_key_value(conn.api_key, bool(conn.is_encrypted)).strip()
    if not api_key:
        raise AssistantConfigError(f"{task_id} 綁定的 Connection 尚未設定 API Key。")

    return BoundConnection(
        task_id=task_id,
        connection_id=int(conn.id),
        vendor=str(conn.vendor or "").strip(),
        model_name=model_name,
        api_key=api_key,
    )


def _normalize_google_model_name(model_name: str) -> str:
    raw = str(model_name or "").strip()
    if raw.startswith("models/"):
        return raw
    if raw.startswith("google/"):
        raw = raw.split("/", 1)[1]
    return f"models/{raw}"


async def _call_openai_style_completion(
    *,
    base_url: str,
    model_name: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    extra_headers: dict[str, str] | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1000,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)

    if response.status_code >= 400:
        raise AssistantProviderError(_extract_http_error_message(response))

    data = response.json()
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            text_parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "\n".join(part for part in text_parts if part).strip()
        return str(content or "").strip()

    raise AssistantProviderError("模型服務未回傳可解析的內容")


async def _call_google_completion(
    *,
    model_name: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    base_url = str(os.environ.get("GOOGLE_GENAI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    model_path = _normalize_google_model_name(model_name)
    endpoint = f"{base_url}/{model_path}:generateContent"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{system_prompt}\n\n{user_prompt}",
                    }
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(endpoint, params={"key": api_key}, json=payload)

    if response.status_code >= 400:
        raise AssistantProviderError(_extract_http_error_message(response))

    data = response.json()
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if isinstance(candidates, list) and candidates:
        first = candidates[0] if isinstance(candidates[0], dict) else {}
        content = first.get("content") if isinstance(first, dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        if isinstance(parts, list):
            texts = [str(part.get("text") or "") for part in parts if isinstance(part, dict)]
            text = "\n".join(item for item in texts if item).strip()
            if text:
                return text

    raise AssistantProviderError("Google 模型服務未回傳可解析的內容")


def _build_mock_answer(primary_task_id: str, message: str, context_bundle: dict[str, Any]) -> str:
    costs = context_bundle.get("costs_summary") if isinstance(context_bundle.get("costs_summary"), dict) else {}
    total_tokens = int(costs.get("total_tokens") or 0)
    total_cost = str(costs.get("total_cost_usd") or "0")

    if primary_task_id == "monthly_report_draft":
        return (
            "# 本月 LLM 成本月報（草稿）\n"
            f"- 本月總 Token：{total_tokens}\n"
            f"- 本月總成本（USD）：{total_cost}\n"
            "- 主要風險：成本集中於少數模型與部門，建議持續追蹤異常峰值。\n"
            "- 下月建議：強化高成本請求審查、推動 prompt 精簡與快取策略。"
        )

    if primary_task_id == "approval_request_summarize":
        approval = context_bundle.get("approval_request") if isinstance(context_bundle.get("approval_request"), dict) else {}
        if approval:
            return (
                "審批摘要：\n"
                f"- 申請類型：{approval.get('request_type')}\n"
                f"- 目標：{approval.get('target_type')}#{approval.get('target_id')}\n"
                f"- 現況：{approval.get('status')}\n"
                f"- 申請原因：{approval.get('reason')}\n"
                "- 建議：先檢查成本與權限影響，再由有權限人員人工決策。"
            )
        return "目前沒有可用的審批上下文，請指定 context_type=approval_request 並提供 context_id。"

    if primary_task_id == "cost_anomaly_summarize":
        return (
            "成本異常解釋（Mock）：\n"
            f"- 本月總 Token：{total_tokens}\n"
            f"- 本月總成本（USD）：{total_cost}\n"
            "- 可能原因：單次長上下文請求、熱門模型集中使用、尖峰時段重試。\n"
            "- 建議查核：先從 Usage Events 檢查高 token 請求與錯誤重試比率。"
        )

    if primary_task_id == "usage_policy_qa":
        return (
            "政策回覆（Mock）：\n"
            "- Ask FinOps 僅提供只讀分析，不執行狀態變更。\n"
            "- 高成本模型是否可用，需符合部門治理策略與審批要求。\n"
            "- 若需例外使用，請走正式審批流程並保留稽核記錄。"
        )

    if primary_task_id == "token_saving_advice":
        return (
            "Token 節省建議（Mock）：\n"
            "1. Prompt 模板化並移除冗長前置描述。\n"
            "2. 將長對話摘要後再續問，降低上下文重送成本。\n"
            "3. 將高成本模型留給必要場景，其餘改用低成本模型。\n"
            "4. 對重複查詢導入快取，避免重複呼叫。"
        )

    return (
        "Ask FinOps（Mock）已收到你的問題。\n"
        f"- 問題：{message}\n"
        f"- 目前可見本月成本（USD）：{total_cost}\n"
        "- 若要更精準分析，請提供 context_type/context_id。"
    )


async def generate_assistant_answer(
    db: Session,
    primary_task_id: str,
    task_ids: list[str],
    message: str,
    context_bundle: dict[str, Any],
) -> str:
    if primary_task_id not in TASK_BINDING_ALLOWED:
        raise AssistantConfigError(f"Unsupported task_id: {primary_task_id}")

    connection = _resolve_bound_connection(db, primary_task_id)
    settings = get_settings()

    if bool(settings.gateway_mock_provider):
        return _build_mock_answer(primary_task_id, message, context_bundle)

    system_prompt, user_prompt = _build_prompt(primary_task_id, task_ids, message, context_bundle)

    vendor = _normalize_text(connection.vendor)
    if vendor == "openrouter":
        base_url = str(os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1")
        headers = _openrouter_headers(connection.api_key)
        return await _call_openai_style_completion(
            base_url=base_url,
            model_name=connection.model_name,
            api_key=connection.api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_headers=headers,
        )

    if vendor == "openai":
        base_url = str(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1")
        return await _call_openai_style_completion(
            base_url=base_url,
            model_name=connection.model_name,
            api_key=connection.api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    if vendor == "google":
        return await _call_google_completion(
            model_name=connection.model_name,
            api_key=connection.api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    raise AssistantConfigError(f"不支援的 Connection vendor: {connection.vendor}")


def build_suggested_actions(task_ids: list[str], risk_level: str, llm_error: str | None = None) -> list[AssistantAction]:
    actions: list[AssistantAction] = []
    seen: set[tuple[str, str | None]] = set()

    def add(action_type: str, label: str, target: str | None = None) -> None:
        key = (action_type, target)
        if key in seen:
            return
        seen.add(key)
        actions.append(AssistantAction(action_type=action_type, label=label, target=target))

    if risk_level == "BLOCKED":
        add("navigate", "前往審批中心走人工流程", "/approvals")
        add("draft", "建立待辦文字草稿", "todo")
        return actions

    if llm_error:
        add("navigate", "前往 LAVA Setup 檢查任務綁定", "/lava-setup")

    if "approval_request_summarize" in task_ids:
        add("navigate", "前往 Approvals 檢視審批單", "/approvals")
    if "cost_anomaly_summarize" in task_ids:
        add("navigate", "前往 Costs 追蹤異常成本", "/costs")
        add("navigate", "前往 Usage Events 檢查高 Token 請求", "/usage-events")
    if "token_saving_advice" in task_ids:
        add("navigate", "前往 Usage Events 進行優化追蹤", "/usage-events")
    if "monthly_report_draft" in task_ids:
        add("copy", "複製月報草稿", "copy_report")
        add("navigate", "前往 Exports 建立匯出任務", "/exports")
    if "usage_policy_qa" in task_ids:
        add("navigate", "前往 Dashboard 查看治理概況", "/dashboard")

    add("draft", "建立待查事項草稿", "todo")
    return actions
