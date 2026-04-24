"""
Auth service: register, login, refresh, logout, me.
"""
from datetime import datetime

from bson.errors import InvalidId
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
)
from mongoengine.errors import ValidationError as MEValidationError

from ..extensions import revoked_tokens
from ..models.user import User
from ..models.role import Role
from ..utils.enums import RoleName
from ..utils.exceptions import Conflict, Unauthorized, BadRequest


class AuthService:
    # ---------- Register ----------
    @staticmethod
    def register(data: dict) -> dict:
        email = data["email"].lower().strip()
        if User.objects(email=email).first():
            raise Conflict("Email is already registered")

        user = User(name=data["name"].strip(), email=email)
        user.set_password(data["password"])

        # Default new users to Writer. Admin-only endpoint can elevate them.
        role_name = data.get("role", RoleName.WRITER.value)
        role = Role.objects(name=role_name).first()
        if not role:
            raise BadRequest(f"Unknown role: {role_name}")
        user.roles.append(role)
        user.save()

        tokens = AuthService._issue_tokens(user)
        return {"user": user.to_dict(), **tokens}

    # ---------- Login ----------
    @staticmethod
    def login(data: dict) -> dict:
        email = data["email"].lower().strip()
        user = User.objects(email=email).first()
        if not user or not user.verify_password(data["password"]):
            raise Unauthorized("Invalid credentials")
        if not user.is_active:
            raise Unauthorized("Account is disabled")

        user.last_login_at = datetime.utcnow()
        user.save()

        tokens = AuthService._issue_tokens(user)
        return {"user": user.to_dict(), **tokens}

    # ---------- Refresh ----------
    @staticmethod
    def refresh(user_id) -> dict:
        try:
            user = User.objects(id=user_id).first()
        except (MEValidationError, InvalidId):
            user = None
        if not user or not user.is_active:
            raise Unauthorized("User not found or inactive")
        return {
            "access_token": create_access_token(
                identity=str(user.id),
                additional_claims={"roles": user.role_names()},
            )
        }

    # ---------- Logout ----------
    @staticmethod
    def logout() -> None:
        """Revoke the currently-presented token by adding its JTI to the blocklist."""
        jti = get_jwt().get("jti")
        if jti:
            revoked_tokens.add(jti)

    # ---------- Helpers ----------
    @staticmethod
    def _issue_tokens(user: User) -> dict:
        claims = {"roles": user.role_names(), "email": user.email}
        return {
            "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
            "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
        }
