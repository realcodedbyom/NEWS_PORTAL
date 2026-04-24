"""
Auth HTTP controllers. Routes remain thin; logic is delegated to AuthService.
"""
from flask import request, g

from ..services.auth_service import AuthService
from ..utils.responses import success_response
from ..utils.validators import load_or_raise, RegisterSchema, LoginSchema


class AuthController:
    @staticmethod
    def register():
        data = load_or_raise(RegisterSchema(), request.get_json(silent=True))
        result = AuthService.register(data)
        return success_response(result, message="Registered successfully", status=201)

    @staticmethod
    def login():
        data = load_or_raise(LoginSchema(), request.get_json(silent=True))
        result = AuthService.login(data)
        return success_response(result, message="Logged in")

    @staticmethod
    def refresh(user_id):
        result = AuthService.refresh(user_id)
        return success_response(result)

    @staticmethod
    def logout():
        AuthService.logout()
        return success_response(message="Logged out")

    @staticmethod
    def me():
        return success_response(g.current_user.to_dict())
