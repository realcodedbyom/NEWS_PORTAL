"""
User management controllers (admin-only).
"""
from bson.errors import InvalidId
from flask import request
from mongoengine import Q
from mongoengine.errors import ValidationError as MEValidationError

from ..models.user import User
from ..models.role import Role
from ..utils.exceptions import NotFound, BadRequest
from ..utils.pagination import get_page_params, paginate_query
from ..utils.responses import success_response, paginated_response


def _get_user_or_404(user_id) -> User:
    try:
        user = User.objects(id=user_id).first()
    except (MEValidationError, InvalidId):
        user = None
    if not user:
        raise NotFound("User not found")
    return user


class UserController:
    @staticmethod
    def list():
        params = get_page_params()
        q = User.objects.order_by("-created_at")
        search = request.args.get("q")
        if search:
            q = q.filter(Q(name__icontains=search) | Q(email__icontains=search))
        items, total = paginate_query(q, params)
        return paginated_response(
            [u.to_dict() for u in items], params.page, params.per_page, total
        )

    @staticmethod
    def set_active(user_id):
        user = _get_user_or_404(user_id)
        payload = request.get_json(silent=True) or {}
        if "is_active" not in payload:
            raise BadRequest("Missing 'is_active'")
        user.is_active = bool(payload["is_active"])
        user.save()
        return success_response(user.to_dict(), message="User updated")

    @staticmethod
    def set_roles(user_id):
        user = _get_user_or_404(user_id)
        payload = request.get_json(silent=True) or {}
        role_names = payload.get("roles", [])
        if not isinstance(role_names, list):
            raise BadRequest("'roles' must be a list")

        roles = list(Role.objects(name__in=role_names))
        if len(roles) != len(set(role_names)):
            raise BadRequest("One or more roles are invalid")

        user.roles = roles
        user.save()
        return success_response(user.to_dict(), message="Roles updated")
