"""
Analytics: per-view log. Aggregate on read; keep writes cheap.
"""
from datetime import datetime

from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    ReferenceField,
)


class PostView(Document):
    post = ReferenceField("Post", required=True)
    user = ReferenceField("User")
    ip_hash = StringField(max_length=64)
    user_agent = StringField(max_length=500)
    referrer = StringField(max_length=500)
    viewed_at = DateTimeField(default=datetime.utcnow, required=True)

    meta = {
        "collection": "post_views",
        "indexes": [
            "post",
            "-viewed_at",
        ],
    }
