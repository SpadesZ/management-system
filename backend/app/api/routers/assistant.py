# File Path: backend/app/api/routers/assistant.py
# Timestamp: 2026-05-26T12:00:00+08:00
# Version: v0.2

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import asc, desc, func, select

from app.api.deps import CurrentUserDep, DBSessionDep, get_pagination_query
from app.core.audit import write_audit_log
from app.models.entities import AssistantConversation, AssistantMessage, User
from app.models.enums import RoleCode
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantConversationRead,
    AssistantMessageRead,
)
from app.schemas.common import PaginationMeta, PaginationQuery
from app.core.security import security_manager
from app.services.assistant import (
    AssistantConfigError,
    AssistantInputError,
    AssistantProviderError,
    append_assistant_message,
    build_blocked_answer,
    build_context_bundle,
    build_suggested_actions,
    detect_risk_level,
    get_or_create_assistant_conversation,
    generate_assistant_answer,
    hash_message,
    normalize_session_id,
    route_tasks,
    summarize_answer,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(payload: AssistantChatRequest, db: DBSessionDep, current_user: CurrentUserDep) -> AssistantChatResponse:
    trace_id = security_manager.generate_trace_id()
    session_id = normalize_session_id(payload.session_id, trace_id)

    conversation = get_or_create_assistant_conversation(
        db,
        current_user,
        session_id=session_id,
        context_type=payload.context_type,
        context_id=payload.context_id,
    )

    risk_level, blocked_reason = detect_risk_level(payload.message)
    task_ids = route_tasks(payload.message, payload.context_type)
    primary_task_id = task_ids[0]

    append_assistant_message(
        db,
        conversation=conversation,
        role="USER",
        content=payload.message,
        message_hash_value=hash_message(payload.message),
        task_ids=task_ids,
        sources=[],
        risk_level=risk_level,
        trace_id=trace_id,
        metadata_json={
            "context_type": payload.context_type,
            "context_id": payload.context_id,
        },
    )

    context_bundle = {}
    sources = []
    llm_error: str | None = None

    if risk_level == "BLOCKED":
        answer = build_blocked_answer(blocked_reason)
    else:
        try:
            context_bundle, sources = build_context_bundle(
                db,
                current_user,
                payload.context_type,
                payload.context_id,
            )
        except AssistantInputError as exc:
            llm_error = str(exc)
            risk_level = "MEDIUM"

        if llm_error is not None:
            answer = f"目前無法取得完整上下文：{llm_error}"
        else:
            try:
                answer = await generate_assistant_answer(
                    db,
                    primary_task_id,
                    task_ids,
                    payload.message,
                    context_bundle,
                )
            except AssistantConfigError as exc:
                llm_error = str(exc)
                risk_level = "MEDIUM"
                answer = f"目前無法完成此任務：{llm_error}"
            except AssistantProviderError as exc:
                llm_error = str(exc)
                risk_level = "HIGH"
                answer = f"模型服務暫時無法回應：{llm_error}"

    suggested_actions = build_suggested_actions(task_ids, risk_level, llm_error)

    response = AssistantChatResponse(
        answer=answer,
        primary_task_id=primary_task_id,
        task_ids=task_ids,
        sources=sources,
        risk_level=risk_level,  # type: ignore[arg-type]
        suggested_actions=suggested_actions,
        trace_id=trace_id,
        conversation_id=conversation.id,
    )

    append_assistant_message(
        db,
        conversation=conversation,
        role="ASSISTANT",
        content=response.answer,
        message_hash_value=hash_message(response.answer),
        task_ids=response.task_ids,
        sources=response.sources,
        risk_level=response.risk_level,
        trace_id=trace_id,
        metadata_json={
            "primary_task_id": response.primary_task_id,
            "llm_error": llm_error or "",
        },
    )

    write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="ASSISTANT_CHAT",
        resource_type="assistant_chat",
        resource_id=trace_id,
        source="API",
        ip_address=None,
        before_json=None,
        after_json={
            "primary_task_id": response.primary_task_id,
            "task_ids": response.task_ids,
            "risk_level": response.risk_level,
        },
        metadata_json={
            "session_id": session_id,
            "conversation_id": conversation.id,
            "trace_id": trace_id,
            "context_type": payload.context_type,
            "context_id": payload.context_id,
            "primary_task_id": response.primary_task_id,
            "task_ids": response.task_ids,
            "sources": [item.model_dump(mode="json") for item in response.sources],
            "risk_level": response.risk_level,
            "suggested_actions": [item.model_dump(mode="json") for item in response.suggested_actions],
            "message_hash": hash_message(payload.message),
            "answer_summary": summarize_answer(response.answer),
            "llm_error": llm_error or "",
        },
    )
    db.commit()
    return response


def _assert_conversation_access(current_user: User, conversation: AssistantConversation) -> None:
    if int(conversation.user_id) == int(current_user.id):
        return

    privileged_roles = {
        RoleCode.ADMIN.value,
        RoleCode.FINANCE.value,
        RoleCode.SECURITY.value,
    }
    if current_user.role not in privileged_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this conversation")


@router.get("/conversations", response_model=dict)
def list_assistant_conversations(
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    stmt = select(AssistantConversation)

    privileged_roles = {
        RoleCode.ADMIN.value,
        RoleCode.FINANCE.value,
        RoleCode.SECURITY.value,
    }
    if current_user.role not in privileged_roles:
        stmt = stmt.where(AssistantConversation.user_id == current_user.id)

    if pagination.start_at is not None:
        stmt = stmt.where(AssistantConversation.last_message_at >= pagination.start_at)
    if pagination.end_at is not None:
        stmt = stmt.where(AssistantConversation.last_message_at <= pagination.end_at)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if pagination.sort_by == "last_message_at":
        order_column = AssistantConversation.last_message_at
    else:
        order_column = AssistantConversation.id

    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [AssistantConversationRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }


@router.get("/conversations/{conversation_id}/messages", response_model=dict)
def list_assistant_messages(
    conversation_id: int,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    pagination: PaginationQuery = Depends(get_pagination_query),
) -> dict:
    conversation = db.get(AssistantConversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    _assert_conversation_access(current_user, conversation)

    stmt = select(AssistantMessage).where(AssistantMessage.conversation_id == conversation_id)
    if pagination.start_at is not None:
        stmt = stmt.where(AssistantMessage.created_at >= pagination.start_at)
    if pagination.end_at is not None:
        stmt = stmt.where(AssistantMessage.created_at <= pagination.end_at)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if pagination.sort_by == "created_at":
        order_column = AssistantMessage.created_at
    else:
        order_column = AssistantMessage.id

    ordering = asc(order_column) if pagination.sort_order == "asc" else desc(order_column)

    rows = db.scalars(
        stmt.order_by(ordering)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    ).all()

    return {
        "items": [AssistantMessageRead.model_validate(row).model_dump(mode="json") for row in rows],
        "meta": PaginationMeta(page=pagination.page, page_size=pagination.page_size, total=int(total)).model_dump(),
    }
