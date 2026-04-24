"""
Analytics routes (editor/admin only).
"""
from flask import Blueprint

from ..controllers.analytics_controller import AnalyticsController
from ..utils.decorators import roles_required
from ..utils.enums import RoleName

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.get("/summary")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def summary():
    return AnalyticsController.summary()


@analytics_bp.get("/top-posts")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def top_posts():
    return AnalyticsController.top_posts()
