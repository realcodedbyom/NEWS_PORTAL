"""
Analytics HTTP controllers.
"""
from flask import request

from ..services.analytics_service import AnalyticsService
from ..utils.responses import success_response


class AnalyticsController:
    @staticmethod
    def summary():
        return success_response(AnalyticsService.dashboard_summary())

    @staticmethod
    def top_posts():
        limit = min(int(request.args.get("limit", 10)), 50)
        days = request.args.get("days", type=int, default=30)
        return success_response(AnalyticsService.top_posts(limit=limit, days=days))
