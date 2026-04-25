"""
Notification HTTP controllers.
"""
from bson.errors import InvalidId
from flask import request, g
from mongoengine.errors import ValidationError as MEValidationError

from ..models.notification import Notification
from ..services.notification_service import NotificationService
from ..utils.exceptions import NotFound
from ..utils.pagination import get_page_params, paginate_query
from ..utils.responses import success_response


def _get_notification_or_404(notification_id) -> Notification:
    try:
        n = Notification.objects(id=notification_id).first()
    except (MEValidationError, InvalidId):
        n = None
    if not n:
        raise NotFound("Notification not found")
    return n


class NotificationController:
    @staticmethod
    def list():
        params = get_page_params()
        unread_only = (request.args.get("unread") or "").lower() in ("1", "true", "yes")
        q = NotificationService.list_for(g.current_user, unread_only=unread_only)
        items, total = paginate_query(q, params)
        pages = (total + params.per_page - 1) // params.per_page if params.per_page else 0
        return success_response(
            data=[n.to_dict() for n in items],
            meta={
                "page": params.page,
                "per_page": params.per_page,
                "total": total,
                "pages": pages,
                "has_next": params.page < pages,
                "has_prev": params.page > 1,
                "unread_count": NotificationService.unread_count(g.current_user),
            },
        )

    @staticmethod
    def unread_count():
        return success_response({"unread": NotificationService.unread_count(g.current_user)})

    @staticmethod
    def mark_read(notification_id: str):
        n = _get_notification_or_404(notification_id)
        n = NotificationService.mark_read(n, g.current_user)
        return success_response(n.to_dict(), message="Marked as read")

    @staticmethod
    def mark_all_read():
        count = NotificationService.mark_all_read(g.current_user)
        return success_response({"updated": int(count or 0)}, message="All notifications marked as read")
