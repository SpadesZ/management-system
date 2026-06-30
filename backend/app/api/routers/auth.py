# File Path: backend/app/api/routers/auth.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DBSessionDep
from app.core.audit import write_audit_log
from app.core.errors import AUTH_INVALID_CREDENTIALS
from app.core.security import security_manager
from app.models.entities import Department, User
from app.models.enums import RoleCode
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RegisterDepartmentOption,
    RegisterOptionsResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)

router = APIRouter(tags=["auth"])


def _generate_employee_no(seed: str) -> str:
    raw = "".join(ch for ch in str(seed or "").upper() if ch.isalnum())
    prefix = raw[:10] if raw else "USER"
    return f"REG{prefix}{uuid4().hex[:6].upper()}"[:64]


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DBSessionDep) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email, User.status == "ACTIVE"))
    if user is None or not security_manager.verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": AUTH_INVALID_CREDENTIALS.code,
                "message": AUTH_INVALID_CREDENTIALS.message,
                "retryable": AUTH_INVALID_CREDENTIALS.retryable,
            },
        )

    access_token = security_manager.create_access_token(
        subject=str(user.id),
        additional_claims={"role": user.role, "department_id": user.department_id},
    )
    return TokenResponse(access_token=access_token)


@router.get("/auth/register/options", response_model=RegisterOptionsResponse)
def register_options(db: DBSessionDep) -> RegisterOptionsResponse:
    rows = db.scalars(select(Department).where(Department.status == "ACTIVE").order_by(Department.id.asc())).all()
    return RegisterOptionsResponse(
        departments=[RegisterDepartmentOption(id=dept.id, name=dept.name) for dept in rows]
    )


@router.post("/auth/register", response_model=RegisterResponse)
def register(payload: RegisterRequest, db: DBSessionDep) -> RegisterResponse:
    existing_email = db.scalar(select(User).where(User.email == payload.email))
    if existing_email is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is too long")

    department: Department | None
    if payload.department_id is not None:
        department = db.get(Department, payload.department_id)
        if department is None or department.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department_id")
    else:
        department = db.scalar(select(Department).where(Department.status == "ACTIVE").order_by(Department.id.asc()))
        if department is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active department available")

    employee_no = str(payload.employee_no or "").strip()
    if employee_no:
        exists_employee = db.scalar(select(User).where(User.employee_no == employee_no))
        if exists_employee is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee number already exists")
    else:
        for _ in range(10):
            candidate = _generate_employee_no(payload.email)
            if db.scalar(select(User).where(User.employee_no == candidate)) is None:
                employee_no = candidate
                break
        if not employee_no:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate employee number")

    user = User(
        employee_no=employee_no,
        name=payload.name,
        email=payload.email,
        password_hash=security_manager.hash_password(payload.password),
        department_id=department.id,
        manager_id=None,
        role=RoleCode.EMPLOYEE.value,
        status="ACTIVE",
    )
    db.add(user)
    db.flush()

    write_audit_log(
        db,
        actor_user_id=None,
        action="USER_REGISTER",
        resource_type="users",
        resource_id=str(user.id),
        source="PUBLIC_REGISTER",
        ip_address=None,
        before_json=None,
        after_json={"email": user.email, "role": user.role, "department_id": user.department_id},
    )

    db.commit()
    db.refresh(user)
    return RegisterResponse(
        id=user.id,
        employee_no=user.employee_no,
        name=user.name,
        email=user.email,
        department_id=user.department_id,
        role=user.role,
        status=user.status,
    )


@router.get("/me", response_model=MeResponse)
def get_me(current_user: CurrentUserDep) -> MeResponse:
    return MeResponse.model_validate(current_user)
