"""
Shared base document for all MongoEngine-backed models.
"""
from datetime import datetime

from mongoengine import Document, DateTimeField


class TimestampedDocument(Document):
    """Abstract base Document with created_at and updated_at fields.

    Subclasses automatically get timestamp tracking; updated_at is
    refreshed on every `.save()`.
    """
    meta = {"abstract": True}

    created_at = DateTimeField(default=datetime.utcnow, required=True)
    updated_at = DateTimeField(default=datetime.utcnow, required=True)

    def save(self, *args, **kwargs):
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        return super().save(*args, **kwargs)


# Backward-compat alias for older imports.
TimestampMixin = TimestampedDocument


def ref_id(doc, field_name):
    """Return the stored ObjectId (as str hex) for a ReferenceField without triggering dereference.

    MongoEngine's default attribute access eagerly fetches referenced
    documents. When you only need the id, reading it from `_data` avoids
    the round-trip.
    """
    raw = doc._data.get(field_name)
    if raw is None:
        return None
    if hasattr(raw, "pk"):
        return str(raw.pk)
    if hasattr(raw, "id"):
        return str(raw.id)
    return str(raw)
