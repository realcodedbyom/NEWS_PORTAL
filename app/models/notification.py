"""
Notifications are sent to users on workflow events (submissions,
approvals, rejections, publish, etc.). Stored in Mongo; reads are
per-user, newest first, with an unread flag.
"""
from bson import DBRef
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

    @property
    def safe_post(self):
        """Return the linked Post, or None if the ref is stale/deleted.

        MongoEngine's reverse_delete_rule=NULLIFY covers future deletions,
        but this guards against orphan DBRefs left over from historical
        deletes or direct Mongo writes. Two failure modes are handled:

        1. Lazy dereference raises (rare, depends on MongoEngine version).
        2. Lazy dereference silently returns a bare ``bson.DBRef`` when the
           target document has been hard-deleted outside the ORM — in this
           case no exception fires, so we must type-check the result.

        Any template that touches ``notification.post`` should use this
        accessor instead so a stale ref never 500s the page.
        """
        try:
            post = self.post
        except Exception:
            return None
        if post is None or isinstance(post, DBRef):
            return None
        return post

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
