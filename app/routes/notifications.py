"""
Notification routes. All require auth.
"""
from flask import Blueprint

from ..controllers.notification_controller import NotificationController
from ..utils.decorators import auth_required

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("")
@auth_required
def list_notifications():
    return NotificationController.list()


@notifications_bp.get("/unread-count")
@auth_required
def unread_count():
    return NotificationController.unread_count()


@notifications_bp.patch("/<string:notification_id>/read")
@auth_required
def mark_read(notification_id: str):
    return NotificationController.mark_read(notification_id)


@notifications_bp.post("/read-all")
@auth_required
def mark_all_read():
    return NotificationController.mark_all_read()
