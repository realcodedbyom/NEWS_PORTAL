"""
Media library. Files live on disk/S3; DB stores metadata so they can
be reused across posts.
"""
from mongoengine import (
    StringField,
    LongField,
    IntField,
    ReferenceField,
)

from ..utils.enums import MediaType
from .base import TimestampedDocument, ref_id as _ref_id


class Media(TimestampedDocument):
    filename = StringField(required=True, max_length=255)
    original_name = StringField(required=True, max_length=255)
    url = StringField(required=True, max_length=500)
    mime_type = StringField(required=True, max_length=100)
    size_bytes = LongField(required=True)
    media_type = StringField(
        required=True, default=MediaType.IMAGE.value, max_length=20
    )
    width = IntField()
    height = IntField()
    alt_text = StringField(max_length=255)
    caption = StringField(max_length=500)

    uploaded_by = ReferenceField("User")

    meta = {
        "collection": "media",
        "indexes": ["-created_at", "media_type"],
    }

    @property
    def uploaded_by_id(self):
        return _ref_id(self, "uploaded_by")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "filename": self.filename,
            "original_name": self.original_name,
            "url": self.url,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "width": self.width,
            "height": self.height,
            "alt_text": self.alt_text,
            "caption": self.caption,
            "uploaded_by_id": self.uploaded_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
