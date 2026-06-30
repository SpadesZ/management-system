# File Path: backend/app/services/scope_filter.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from dataclasses import dataclass

from sqlalchemy import Select, text
from sqlalchemy.orm import Session

from app.models.entities import User
from app.models.enums import RoleCode


@dataclass
class ScopeContext:
    user_id: int
    role: str
    department_id: int


def get_scope_context(user: User) -> ScopeContext:
    return ScopeContext(user_id=user.id, role=user.role, department_id=user.department_id)


def get_descendant_department_ids(db: Session, root_department_id: int) -> list[int]:
    sql = text(
        """
        WITH RECURSIVE department_tree AS (
            SELECT id, parent_id FROM departments WHERE id = :root_id
            UNION ALL
            SELECT d.id, d.parent_id
            FROM departments d
            JOIN department_tree dt ON d.parent_id = dt.id
        )
        SELECT id FROM department_tree
        """
    )
    rows = db.execute(sql, {"root_id": root_department_id}).fetchall()
    return [int(row[0]) for row in rows]


def allowed_department_ids(db: Session, context: ScopeContext) -> list[int] | None:
    role = context.role
    if role in {RoleCode.ADMIN.value, RoleCode.FINANCE.value, RoleCode.SECURITY.value}:
        return None
    if role == RoleCode.MANAGER.value:
        return get_descendant_department_ids(db, context.department_id)
    return [context.department_id]


def apply_department_scope(query: Select, department_column, allowed_ids: list[int] | None) -> Select:
    if allowed_ids is None:
        return query
    if not allowed_ids:
        return query.where(text("1=0"))
    return query.where(department_column.in_(allowed_ids))


def ensure_resource_scope(resource_department_id: int | None, allowed_ids: list[int] | None) -> bool:
    if allowed_ids is None:
        return True
    if resource_department_id is None:
        return False
    return resource_department_id in allowed_ids
