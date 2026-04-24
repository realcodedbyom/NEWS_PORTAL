"""
Domain exceptions. Raise these from services; the global
error handler converts them into clean JSON responses.
"""
from typing import Any


class AppException(Exception):
    status_code: int = 400
    message: str = "Application error"

    def __init__(self, message: str | None = None, status_code: int | None = None, details: Any = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class BadRequest(AppException):
    status_code = 400
    message = "Bad request"


class Unauthorized(AppException):
    status_code = 401
    message = "Unauthorized"


class Forbidden(AppException):
    status_code = 403
    message = "Forbidden"


class NotFound(AppException):
    status_code = 404
    message = "Resource not found"


class Conflict(AppException):
    status_code = 409
    message = "Conflict"


class ValidationError(AppException):
    status_code = 422
    message = "Validation failed"


class WorkflowError(AppException):
    status_code = 409
    message = "Invalid workflow transition"
