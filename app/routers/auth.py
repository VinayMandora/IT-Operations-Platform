"""Local demonstration authentication and administrator user management."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Asset, Ticket, User
from app.schemas import LoginIn, UserCreate, UserEdit
from app.security import (COOKIE_NAME, SESSION_AGE_SECONDS, cookie_secure, create_session,
                          current_user, hash_password, require_roles, verify_password)
from app.services.helpdesk_service import log_event

router = APIRouter(prefix='/api/auth', tags=['authentication'])
users_router = APIRouter(prefix='/api/users', tags=['user administration'])


def public_user(user: User) -> dict:
    return {'id': user.id, 'username': user.username, 'full_name': user.full_name,
            'email': user.email, 'role': user.role, 'is_active': user.is_active}


@router.post('/login')
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    if not user or not user.is_active or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, 'Invalid username or password')
    token, csrf = create_session(user)
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_AGE_SECONDS,
                        httponly=True, secure=cookie_secure(), samesite='lax', path='/')
    return {'user': public_user(user), 'csrf_token': csrf}


@router.post('/logout')
def logout(response: Response, _user: User = Depends(current_user)):
    response.delete_cookie(COOKIE_NAME, path='/')
    return {'logged_out': True}


@router.get('/me')
def me(user: User = Depends(current_user)):
    # CSRF token is provided to same-origin browser JavaScript, never to third-party origins.
    # The browser sends it as X-CSRF-Token on write requests.
    return public_user(user)


@users_router.get('')
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_roles('Admin'))):
    return {'items': [public_user(x) for x in db.scalars(select(User).order_by(User.id))]}


@users_router.post('', status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_roles('Admin'))):
    user = User(username=body.username.lower(), full_name=body.full_name, email=body.email.lower(),
                role=body.role, password_hash=hash_password(body.password), is_active=True)
    try:
        db.add(user)
        db.flush()
        log_event(db, 'USER_CREATED', admin, user_id=user.id, role=user.role)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Username or email already exists') from exc
    db.refresh(user)
    return public_user(user)


@users_router.patch('/{user_id}')
def edit_user(user_id: int, body: UserEdit, db: Session = Depends(get_db),
              admin: User = Depends(require_roles('Admin'))):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, 'User not found')
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, 'Supply one or more fields to change')
    if ('role' in changes or changes.get('is_active') is False) and target.id == admin.id:
        raise HTTPException(409, 'Cannot change your own admin role or disable your own account')
    if target.role == 'Admin' and (changes.get('is_active') is False or (changes.get('role') and changes['role'] != 'Admin')):
        active_admins = db.scalar(select(func.count()).select_from(User).where(User.role=='Admin', User.is_active==True))
        if target.is_active and active_admins <= 1:
            raise HTTPException(409, 'Cannot remove the last active admin')
    if changes.get('role') and changes['role'] != target.role:
        if db.scalar(select(func.count()).select_from(Asset).where(Asset.assigned_employee_id==target.id)):
            raise HTTPException(409, 'Return this user\'s devices before changing role')
        if db.scalar(select(func.count()).select_from(Ticket).where(Ticket.assigned_technician_id==target.id, Ticket.status.notin_(['Resolved','Closed']))):
            raise HTTPException(409, 'Resolve or reassign assigned tickets before changing role')
    if 'password' in changes:
        changes['password_hash'] = hash_password(changes.pop('password'))
    if 'email' in changes:
        changes['email'] = changes['email'].lower()
    for field, value in changes.items():
        setattr(target, field, value)
    try:
        log_event(db, 'USER_UPDATED', admin, user_id=target.id,
                  changed_fields=sorted(changes.keys()))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Email address already in use') from exc
    db.refresh(target)
    return public_user(target)
