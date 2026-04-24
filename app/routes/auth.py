"""
Auth routes. Thin wiring only — see AuthController for logic.
"""
from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..controllers.auth_controller import AuthController
from ..utils.decorators import auth_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    return AuthController.register()


@auth_bp.post("/login")
def login():
    return AuthController.login()


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    return AuthController.refresh(user_id)


@auth_bp.post("/logout")
@jwt_required()
def logout():
    return AuthController.logout()


@auth_bp.get("/me")
@auth_required
def me():
    return AuthController.me()
