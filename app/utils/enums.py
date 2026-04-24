"""
Central enums so state machines and category strings have
a single source of truth.
"""
from enum import Enum


class RoleName(str, Enum):
    WRITER = "writer"
    EDITOR = "editor"
    ADMIN = "admin"

    @classmethod
    def values(cls) -> list[str]:
        return [r.value for r in cls]


class PostStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"

    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]


class PostCategory(str, Enum):
    NEWS = "news"
    CULTURE = "culture"
    ACADEMICS = "academics"
    ANNOUNCEMENTS = "announcements"
    EVENTS = "events"
    RESEARCH = "research"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


# Allowed workflow transitions: who can do what, and to what.
# Keeping this in one place makes audits & changes trivial.
ALLOWED_TRANSITIONS: dict[PostStatus, dict[RoleName, list[PostStatus]]] = {
    PostStatus.DRAFT: {
        RoleName.WRITER: [PostStatus.REVIEW],
        RoleName.EDITOR: [PostStatus.REVIEW, PostStatus.APPROVED, PostStatus.REJECTED],
        RoleName.ADMIN: [PostStatus.REVIEW, PostStatus.APPROVED, PostStatus.REJECTED],
    },
    PostStatus.REVIEW: {
        RoleName.EDITOR: [PostStatus.APPROVED, PostStatus.REJECTED, PostStatus.DRAFT],
        RoleName.ADMIN: [PostStatus.APPROVED, PostStatus.REJECTED, PostStatus.DRAFT],
    },
    PostStatus.APPROVED: {
        RoleName.EDITOR: [PostStatus.READY_TO_PUBLISH, PostStatus.DRAFT],
        RoleName.ADMIN: [PostStatus.READY_TO_PUBLISH, PostStatus.PUBLISHED, PostStatus.DRAFT],
    },
    PostStatus.READY_TO_PUBLISH: {
        RoleName.ADMIN: [PostStatus.PUBLISHED, PostStatus.APPROVED],
    },
    PostStatus.PUBLISHED: {
        RoleName.ADMIN: [PostStatus.ARCHIVED],
    },
    PostStatus.REJECTED: {
        RoleName.WRITER: [PostStatus.DRAFT],
        RoleName.EDITOR: [PostStatus.DRAFT],
        RoleName.ADMIN: [PostStatus.DRAFT],
    },
    PostStatus.ARCHIVED: {
        RoleName.ADMIN: [PostStatus.DRAFT],
    },
}
