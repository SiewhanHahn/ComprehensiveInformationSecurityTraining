from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import ROLE_ADMIN, CurrentUser, require_roles
from ..models import Role, User, UserRole
from ..schemas import UserCreate, UserOut, UserPage, UserPasswordReset, UserRolesUpdate, UserStatusUpdate
from ..security import hash_password
from ..services.audit import audit_context

router = APIRouter(prefix="/users")
admin_required = require_roles(ROLE_ADMIN)


def _lock_admin(db: Session, current: CurrentUser) -> Role:
    admin = db.scalar(select(Role).where(Role.code == ROLE_ADMIN).with_for_update())
    # Locking reads bypass MySQL's earlier authentication snapshot after a concurrent revocation.
    actor = db.execute(select(User.is_active).where(User.id == current.id).with_for_update()).scalar_one_or_none()
    membership = db.scalar(select(UserRole.user_id).where(
        UserRole.user_id == current.id, UserRole.role_id == admin.id,
    ).with_for_update())
    if not actor or membership is None:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return admin


def _target(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    if user is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return user


def _roles(db: Session, codes: set[str]) -> dict[str, Role]:
    # 角色代码已由 schema 限定；参考数据缺行属于部署/数据问题，整体失败而不是静默少授权
    roles = {role.code: role for role in db.scalars(select(Role).where(Role.code.in_(codes))).all()}
    if set(roles) != codes:
        raise HTTPException(status_code=503, detail="DEPENDENCY_UNAVAILABLE")
    return roles


def _out(db: Session, user: User) -> UserOut:
    roles = db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(
        UserRole.user_id == user.id,
    ).order_by(Role.code).with_for_update()).all()
    return UserOut(id=user.id, username=user.username, display_name=user.display_name,
                   is_active=user.is_active, roles=roles)


def _audit(db: Session, current: CurrentUser, request: Request, user_id: int, action: str, reason: str | None = None):
    audit_context(request, db, current).record(
        action, resource_type="USER", resource_id=str(user_id), reason=reason, actor_role=ROLE_ADMIN,
    )


def _require_other_admin(db: Session, admin: Role, user_id: int):
    others = db.scalars(select(User.id).join(UserRole, UserRole.user_id == User.id).where(
        UserRole.role_id == admin.id, User.is_active.is_(True), User.id != user_id,
    ).with_for_update()).all()
    if not others:
        raise HTTPException(status_code=409, detail="LAST_ADMIN_REQUIRED")


@router.get("", response_model=UserPage)
def list_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               current: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(User))
    users = db.scalars(select(User).options(selectinload(User.roles)).order_by(User.id)
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return UserPage(items=[UserOut(id=u.id, username=u.username, display_name=u.display_name,
                                  is_active=u.is_active, roles=sorted(r.code for r in u.roles)) for u in users],
                    total=total, page=page, page_size=page_size)


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, request: Request, current: CurrentUser = Depends(admin_required),
                db: Session = Depends(get_db)):
    password_hash = hash_password(payload.password)
    _lock_admin(db, current)
    if db.scalar(select(User.id).where(User.username == payload.username).with_for_update()) is not None:
        raise HTTPException(status_code=409, detail="USERNAME_EXISTS")
    user = User(username=payload.username, display_name=payload.display_name, password_hash=password_hash, is_active=True)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "args", (None,))[0] == 1062:
            raise HTTPException(status_code=409, detail="USERNAME_EXISTS") from exc
        raise
    roles = _roles(db, set(payload.roles))
    for role in roles.values():
        db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=current.id))
    _audit(db, current, request, user.id, "USER_CREATE", "roles=" + ",".join(payload.roles))
    db.flush()
    result = _out(db, user)
    db.commit()
    return result


@router.patch("/{user_id}/status", response_model=UserOut)
def update_status(user_id: int, payload: UserStatusUpdate, request: Request,
                  current: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    admin = _lock_admin(db, current)
    user = _target(db, user_id)
    if not payload.is_active and user_id == current.id:
        raise HTTPException(status_code=409, detail="SELF_DISABLE_FORBIDDEN")
    if user.is_active != payload.is_active:
        if not payload.is_active:
            _require_other_admin(db, admin, user_id)
        user.is_active = payload.is_active
        _audit(db, current, request, user_id, "USER_STATUS_CHANGE", f"is_active={payload.is_active}")
    result = _out(db, user)
    db.commit()
    return result


@router.put("/{user_id}/roles", response_model=UserOut)
def update_roles(user_id: int, payload: UserRolesUpdate, request: Request,
                 current: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    admin = _lock_admin(db, current)
    user = _target(db, user_id)
    if user_id == current.id and ROLE_ADMIN not in payload.roles:
        raise HTTPException(status_code=409, detail="SELF_ADMIN_REMOVAL_FORBIDDEN")
    existing = db.execute(select(UserRole.role_id, Role.code).join(Role, Role.id == UserRole.role_id)
                          .where(UserRole.user_id == user_id).with_for_update()).all()
    old = {code for _, code in existing}
    new = set(payload.roles)
    if old != new:
        roles = _roles(db, new)
        if ROLE_ADMIN in old and ROLE_ADMIN not in new and user.is_active:
            _require_other_admin(db, admin, user_id)
        removed = [role_id for role_id, code in existing if code not in new]
        if removed:
            db.execute(delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id.in_(removed)))
        for code in sorted(new - old):
            db.add(UserRole(user_id=user_id, role_id=roles[code].id, granted_by=current.id))
        _audit(db, current, request, user_id, "USER_ROLES_CHANGE",
               "roles=" + ",".join(sorted(old)) + " -> " + ",".join(sorted(new)))
    db.flush()
    result = _out(db, user)
    db.commit()
    return result


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: int, payload: UserPasswordReset, request: Request,
                   current: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    password_hash = hash_password(payload.password)
    _lock_admin(db, current)
    user = _target(db, user_id)
    user.password_hash = password_hash
    user.failed_login_count = 0
    user.locked_until = None
    _audit(db, current, request, user_id, "USER_PASSWORD_RESET")
    db.commit()
    return Response(status_code=204)
