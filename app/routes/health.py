from flask import Blueprint

from ..utils.responses import success_response

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    return success_response({"status": "ok"})
