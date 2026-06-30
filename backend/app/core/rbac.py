# File Path: backend/app/core/rbac.py
# Timestamp: 2026-05-26T22:10:00+08:00
# Version: v0.1

from app.models.enums import RoleCode

ROLE_PERMISSION_CODE_MAP: dict[str, str] = {
    RoleCode.ADMIN.value: "role.admin",
    RoleCode.FINANCE.value: "role.finance",
    RoleCode.MANAGER.value: "role.manager",
    RoleCode.EMPLOYEE.value: "role.employee",
    RoleCode.AUDITOR.value: "role.auditor",
    RoleCode.SECURITY.value: "role.security",
}

ROLE_PERMISSION_NAME_MAP: dict[str, str] = {
    RoleCode.ADMIN.value: "Allow ADMIN role operations",
    RoleCode.FINANCE.value: "Allow FINANCE role operations",
    RoleCode.MANAGER.value: "Allow MANAGER role operations",
    RoleCode.EMPLOYEE.value: "Allow EMPLOYEE role operations",
    RoleCode.AUDITOR.value: "Allow AUDITOR role operations",
    RoleCode.SECURITY.value: "Allow SECURITY role operations",
}

ROLE_DEFAULT_GRANTS: dict[str, set[str]] = {
    role_code: {permission_code}
    for role_code, permission_code in ROLE_PERMISSION_CODE_MAP.items()
}


def normalize_role_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def permission_code_for_role(role_code: str | None) -> str | None:
    return ROLE_PERMISSION_CODE_MAP.get(normalize_role_code(role_code))


def default_permission_codes_for_role(role_code: str | None) -> set[str]:
    normalized = normalize_role_code(role_code)
    return set(ROLE_DEFAULT_GRANTS.get(normalized) or set())
