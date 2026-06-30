# File Path: backend/app/db/seed.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rbac import ROLE_PERMISSION_CODE_MAP, ROLE_PERMISSION_NAME_MAP, default_permission_codes_for_role
from app.core.security import security_manager
from app.models.entities import Department, Permission, Provider, Role, RolePermission, User
from app.models.enums import ResourceStatus, RoleCode


def seed_base_data(db: Session) -> None:
    settings = get_settings()

    admin_dept = db.scalar(select(Department).where(Department.name == "Platform"))
    if admin_dept is None:
        admin_dept = Department(name="Platform", monthly_budget_usd=Decimal("100000"), status=ResourceStatus.ACTIVE.value)
        db.add(admin_dept)
        db.flush()

    existing_admin = db.scalar(select(User).where(User.email == settings.default_admin_email))
    if existing_admin is None:
        admin = User(
            employee_no="ADMIN0001",
            name=settings.default_admin_name,
            email=settings.default_admin_email,
            password_hash=security_manager.hash_password(settings.default_admin_password),
            department_id=admin_dept.id,
            role=RoleCode.ADMIN.value,
            status=ResourceStatus.ACTIVE.value,
        )
        db.add(admin)

    roles_by_code: dict[str, Role] = {}
    for role_code in RoleCode:
        role = db.scalar(select(Role).where(Role.code == role_code.value))
        if role is None:
            role = Role(code=role_code.value, name=role_code.value.title())
            db.add(role)
            db.flush()
        roles_by_code[role_code.value] = role

    permissions_by_code: dict[str, Permission] = {}
    for role_code, permission_code in ROLE_PERMISSION_CODE_MAP.items():
        permission = db.scalar(select(Permission).where(Permission.code == permission_code))
        if permission is None:
            permission = Permission(
                code=permission_code,
                name=ROLE_PERMISSION_NAME_MAP.get(role_code, permission_code),
            )
            db.add(permission)
            db.flush()
        permissions_by_code[permission_code] = permission

    for role_code in RoleCode:
        role = roles_by_code.get(role_code.value)
        if role is None:
            continue

        for permission_code in default_permission_codes_for_role(role_code.value):
            permission = permissions_by_code.get(permission_code)
            if permission is None:
                continue

            existing_link = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                )
            )
            if existing_link is None:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))

    provider_defaults = [
        ("openai", "OpenAI", "https://api.openai.com/v1"),
        ("anthropic", "Anthropic", "https://api.anthropic.com/v1"),
        ("google", "Google Gemini", "https://generativelanguage.googleapis.com"),
        ("azure_openai", "Azure OpenAI", "https://example-resource.openai.azure.com"),
    ]
    for code, name, base_url in provider_defaults:
        provider = db.scalar(select(Provider).where(Provider.code == code))
        if provider is None:
            db.add(Provider(code=code, name=name, base_url=base_url, status=ResourceStatus.ACTIVE.value))

    db.commit()
