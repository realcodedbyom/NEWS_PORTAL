"""
User management routes (admin-only).
"""
from flask import Blueprint

from ..controllers.user_controller import UserController
from ..utils.decorators import admin_required

users_bp = Blueprint("users", __name__)


@users_bp.get("")
@admin_required
def list_users():
    return UserController.list()


@users_bp.patch("/<string:user_id>/active")
@admin_required
def set_active(user_id: str):
    return UserController.set_active(user_id)


@users_bp.patch("/<string:user_id>/roles")
@admin_required
def set_roles(user_id: str):
    return UserController.set_roles(user_id)
