"""
Reusable decorators for auth & role checks.

Usage:
    @posts_bp.post("")
    @roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
    def create_post():
        ...
"""
from functools import wraps
from typing import Callable

from bson import ObjectId
from bson.errors import InvalidId
from flask import g
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt

from .enums import RoleName
from .exceptions import Forbidden, Unauthorized


def _load_current_user():
    """Fetch the user tied to the JWT and cache on `flask.g`."""
    if getattr(g, "current_user", None) is not None:
        return g.current_user

    # Local import avoids circular dependency at module load time.
    from ..models.user import User

    user_id = get_jwt_identity()
    if not user_id:
        raise Unauthorized("Invalid identity")

    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        raise Unauthorized("Invalid identity")

    user = User.objects(id=oid).first()
    if not user or not user.is_active:
        raise Unauthorized("User inactive or deleted")

    g.current_user = user
    g.jwt_claims = get_jwt()
    return user


def auth_required(fn: Callable):
    """Require a valid JWT and load the user onto `g.current_user`."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        _load_current_user()
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*roles: RoleName):
    """Require the authenticated user to have at least one of the given roles."""
    allowed = {r.value if isinstance(r, RoleName) else r for r in roles}

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = _load_current_user()
            user_roles = {r.name for r in (user.roles or []) if r}
            if not user_roles.intersection(allowed):
                raise Forbidden(
                    f"Requires role(s): {', '.join(sorted(allowed))}"
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(fn: Callable):
    return roles_required(RoleName.ADMIN)(fn)
