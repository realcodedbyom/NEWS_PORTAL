"""
Post + PostVersion documents.

- PostStatus is stored as a string so the workflow state machine has a
  single source of truth.
- PostVersion is its own collection and snapshots title/content/etc.
  on every meaningful change.
"""
from datetime import datetime

from mongoengine import (
    CASCADE,
    Document,
    EmbeddedDocument,
    EmbeddedDocumentField,
    StringField,
    BooleanField,
    DateTimeField,
    IntField,
    ReferenceField,
    ListField,
)

from ..utils.enums import PostStatus, PostCategory
from .base import TimestampedDocument, ref_id as _ref_id


class StatusHistoryEntry(EmbeddedDocument):
    """One row in a Post's status_history log.

    Unlike PostVersion (which snapshots full content), this keeps a
    compact audit trail of workflow state changes for quick display.
    """
    status = StringField(required=True, max_length=30)
    changed_by = ReferenceField("User")
    changed_at = DateTimeField(default=datetime.utcnow, required=True)
    note = StringField(max_length=500)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "changed_by_id": str(self.changed_by.id) if self.changed_by else None,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
            "note": self.note,
        }


class ModerationNote(EmbeddedDocument):
    """Editor/admin feedback attached to a post during moderation."""
    author = ReferenceField("User")
    note = StringField(required=True, max_length=1000)
    created_at = DateTimeField(default=datetime.utcnow, required=True)

    def to_dict(self) -> dict:
        return {
            "author_id": str(self.author.id) if self.author else None,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Post(TimestampedDocument):
    # Content
    title = StringField(required=True, max_length=255)
    subtitle = StringField(max_length=255)
    slug = StringField(required=True, unique=True, max_length=255)
    excerpt = StringField(max_length=500)
    content = StringField(required=True)

    # Taxonomy
    category = StringField(
        required=True, default=PostCategory.NEWS.value, max_length=50
    )

    # Workflow
    status = StringField(
        required=True, default=PostStatus.DRAFT.value, max_length=30
    )
    status_note = StringField(max_length=500)

    # Flags
    is_featured = BooleanField(default=False, required=True)
    is_announcement = BooleanField(default=False, required=True)
    is_pinned = BooleanField(default=False, required=True)

    # Public submissions + moderation
    is_public_submission = BooleanField(default=False, required=True)
    moderation_notes = ListField(EmbeddedDocumentField(ModerationNote))
    status_history = ListField(EmbeddedDocumentField(StatusHistoryEntry))

    # Scheduling
    publish_at = DateTimeField()
    published_at = DateTimeField()
    expires_at = DateTimeField()

    # Metrics
    view_count = IntField(default=0, required=True)

    # Relationships
    author = ReferenceField("User")
    editor = ReferenceField("User")
    publisher = ReferenceField("User")
    featured_image = ReferenceField("Media")
    gallery = ListField(ReferenceField("Media"))
    tags = ListField(ReferenceField("Tag"))

    meta = {
        "collection": "posts",
        "indexes": [
            "status",
            "category",
            "is_featured",
            "is_pinned",
            "is_announcement",
            "is_public_submission",
            "publish_at",
            "expires_at",
            "-published_at",
            "-created_at",
            "author",
            ("status", "category"),
            ("status", "is_public_submission"),
        ],
    }

    # ---- raw reference ids (no dereference) ----

    @property
    def author_id(self):
        return _ref_id(self, "author")

    @property
    def editor_id(self):
        return _ref_id(self, "editor")

    @property
    def publisher_id(self):
        return _ref_id(self, "publisher")

    @property
    def featured_image_id(self):
        return _ref_id(self, "featured_image")

    # ---- helpers ----

    def is_published(self) -> bool:
        return self.status == PostStatus.PUBLISHED.value

    def to_dict(self, include_content: bool = True) -> dict:
        data = {
            "id": str(self.id),
            "title": self.title,
            "subtitle": self.subtitle,
            "slug": self.slug,
            "excerpt": self.excerpt,
            "category": self.category,
            "status": self.status,
            "status_note": self.status_note,
            "is_featured": bool(self.is_featured),
            "is_announcement": bool(self.is_announcement),
            "is_pinned": bool(self.is_pinned),
            "is_public_submission": bool(self.is_public_submission),
            "moderation_notes": [n.to_dict() for n in (self.moderation_notes or [])],
            "status_history": [h.to_dict() for h in (self.status_history or [])],
            "publish_at": self.publish_at.isoformat() if self.publish_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "view_count": int(self.view_count or 0),
            "author": self.author.to_dict() if self.author else None,
            "editor_id": self.editor_id,
            "publisher_id": self.publisher_id,
            "featured_image": self.featured_image.to_dict() if self.featured_image else None,
            "gallery": [m.to_dict() for m in (self.gallery or []) if m],
            "tags": [t.to_dict() for t in (self.tags or []) if t],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_content:
            data["content"] = self.content
        return data


class PostVersion(Document):
    """Immutable snapshot of a Post's content at a point in time."""
    post = ReferenceField("Post", required=True, reverse_delete_rule=CASCADE)
    version = IntField(required=True)

    title = StringField(required=True, max_length=255)
    subtitle = StringField(max_length=255)
    content = StringField(required=True)
    excerpt = StringField(max_length=500)
    category = StringField(required=True, max_length=50)
    status = StringField(required=True, max_length=30)

    changed_by = ReferenceField("User")
    change_note = StringField(max_length=500)
    created_at = DateTimeField(default=datetime.utcnow, required=True)

    meta = {
        "collection": "post_versions",
        "indexes": [
            "post",
            ("post", "version"),
            "-created_at",
        ],
    }

    @property
    def post_id(self):
        return _ref_id(self, "post")

    @property
    def changed_by_id(self):
        return _ref_id(self, "changed_by")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "post_id": self.post_id,
            "version": self.version,
            "title": self.title,
            "subtitle": self.subtitle,
            "excerpt": self.excerpt,
            "category": self.category,
            "status": self.status,
            "changed_by_id": self.changed_by_id,
            "change_note": self.change_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
