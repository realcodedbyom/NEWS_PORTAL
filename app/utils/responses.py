"""
Uniform JSON response envelopes.

All API responses follow this shape so the frontend can rely on a
predictable contract:

    { "success": bool, "data": ..., "message": str | None, "meta": {...}? }
"""
from typing import Any
from flask import jsonify


def success_response(
    data: Any = None,
    message: str | None = None,
    status: int = 200,
    meta: dict | None = None,
):
    payload: dict[str, Any] = {"success": True, "data": data}
    if message:
        payload["message"] = message
    if meta:
        payload["meta"] = meta
    return jsonify(payload), status


def error_response(
    message: str,
    status: int = 400,
    details: Any = None,
):
    payload: dict[str, Any] = {"success": False, "message": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status


def paginated_response(items: list, page: int, per_page: int, total: int, message: str | None = None):
    pages = (total + per_page - 1) // per_page if per_page else 0
    return success_response(
        data=items,
        message=message,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
        },
    )
