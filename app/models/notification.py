"""
Notifications are sent to users on workflow events (submissions,
approvals, rejections, publish, etc.). Stored in Mongo; reads are
per-user, newest first, with an unread flag.
"""
from mongoengine import (
    NULLIFY,
    StringField,
    BooleanField,
    ReferenceField,
)

from .base import TimestampedDocument, ref_id as _ref_id


class Notification(TimestampedDocument):
    user = ReferenceField("User", required=True)
    type = StringField(required=True, max_length=40)
    message = StringField(required=True, max_length=500)
    post = ReferenceField("Post", reverse_delete_rule=NULLIFY)
    is_read = BooleanField(default=False, required=True)

    meta = {
        "collection": "notifications",
        "indexes": [
            "user",
            "-created_at",
            "is_read",
            ("user", "is_read"),
            ("user", "-created_at"),
        ],
    }

    @property
    def user_id(self):
        return _ref_id(self, "user")

    @property
    def post_id(self):
        return _ref_id(self, "post")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "type": self.type,
            "message": self.message,
            "post_id": self.post_id,
            "is_read": bool(self.is_read),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
