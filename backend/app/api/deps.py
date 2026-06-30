# File Path: backend/app/api/deps.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AUTH_UNAUTHORIZED, SCOPE_FORBIDDEN
from app.core.rbac import permission_code_for_role
from app.core.security import security_manager
from app.db.session import get_db_session
from app.models.entities import Permission, Role, RolePermission, User
from app.schemas.common import PaginationQuery

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DBSessionDep = Annotated[Session, Depends(get_db_session)]


def get_current_user(db: DBSessionDep, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    try:
        payload = security_manager.decode_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": AUTH_UNAUTHORIZED.code,
                "message": AUTH_UNAUTHORIZED.message,
                "retryable": AUTH_UNAUTHORIZED.retryable,
            },
        ) from exc

    user = db.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": AUTH_UNAUTHORIZED.code,
                "message": AUTH_UNAUTHORIZED.message,
                "retryable": AUTH_UNAUTHORIZED.retryable,
            },
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def _forbidden_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error_code": SCOPE_FORBIDDEN.code,
            "message": SCOPE_FORBIDDEN.message,
            "retryable": SCOPE_FORBIDDEN.retryable,
        },
    )


def _load_role_permission_codes(db: Session, role_code: str) -> set[str]:
    normalized_role = str(role_code or "").strip().upper()
    if not normalized_role:
        return set()

    stmt = (
        select(Permission.code)
        .select_from(Role)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Role.code == normalized_role)
    )
    return {str(code) for code in db.scalars(stmt).all() if code}


def require_roles(*allowed_roles: str):
    allowed_role_set = {str(role or "").strip().upper() for role in allowed_roles if str(role or "").strip()}
    required_permission_codes = {
        code
        for code in (permission_code_for_role(role_code) for role_code in allowed_role_set)
        if code is not None
    }

    def _checker(current_user: CurrentUserDep, db: DBSessionDep) -> User:
        if not required_permission_codes:
            raise _forbidden_exception()

        granted_permission_codes = _load_role_permission_codes(db, current_user.role)
        if granted_permission_codes.isdisjoint(required_permission_codes):
            raise _forbidden_exception()
        return current_user

    return _checker


def get_pagination_query(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    sort_by: str = Query(default="id"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    start_at: str | None = Query(default=None),
    end_at: str | None = Query(default=None),
    timezone: str = Query(default="UTC"),
) -> PaginationQuery:
    return PaginationQuery(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        start_at=start_at,
        end_at=end_at,
        timezone=timezone,
    )
