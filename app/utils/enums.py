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
    REVIEW = "review"                      # legacy synonym for IN_REVIEW
    PENDING_REVIEW = "pending_review"      # public submission awaiting triage
    IN_REVIEW = "in_review"                # editor is actively reviewing
    CHANGES_REQUIRED = "changes_required"
    APPROVED = "approved"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    REJECTED = "rejected"                  # legacy internal reject
    REJECTED_PUBLIC = "rejected_public"    # public submission rejected
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


class NotificationType(str, Enum):
    SUBMISSION_RECEIVED = "submission_received"
    NEW_SUBMISSION = "new_submission"            # sent to editors when a writer/public submits
    CHANGES_REQUIRED = "changes_required"
    APPROVED = "approved"                        # editor approved -> admin notified
    READY_FOR_PUBLISH = "ready_for_publish"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"

    @classmethod
    def values(cls) -> list[str]:
        return [n.value for n in cls]


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
        RoleName.EDITOR: [PostStatus.READY_TO_PUBLISH, PostStatus.DRAFT, PostStatus.IN_REVIEW],
        RoleName.ADMIN: [PostStatus.READY_TO_PUBLISH, PostStatus.PUBLISHED, PostStatus.DRAFT, PostStatus.IN_REVIEW],
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


# --- Additions for public submissions + new internal flow ---
# Writers can submit drafts straight into the new IN_REVIEW state
# (the old REVIEW target is retained above for backward compatibility).
ALLOWED_TRANSITIONS[PostStatus.DRAFT][RoleName.WRITER].append(PostStatus.IN_REVIEW)
ALLOWED_TRANSITIONS[PostStatus.DRAFT][RoleName.EDITOR].append(PostStatus.IN_REVIEW)
ALLOWED_TRANSITIONS[PostStatus.DRAFT][RoleName.ADMIN].append(PostStatus.IN_REVIEW)

# Public submissions land in PENDING_REVIEW and must be triaged by an editor/admin.
ALLOWED_TRANSITIONS[PostStatus.PENDING_REVIEW] = {
    RoleName.EDITOR: [PostStatus.IN_REVIEW, PostStatus.REJECTED_PUBLIC],
    RoleName.ADMIN: [PostStatus.IN_REVIEW, PostStatus.REJECTED_PUBLIC, PostStatus.APPROVED],
}

# Full set of editor/admin options from the active review state.
ALLOWED_TRANSITIONS[PostStatus.IN_REVIEW] = {
    RoleName.EDITOR: [
        PostStatus.APPROVED,
        PostStatus.REJECTED,
        PostStatus.REJECTED_PUBLIC,
        PostStatus.CHANGES_REQUIRED,
        PostStatus.DRAFT,
    ],
    RoleName.ADMIN: [
        PostStatus.APPROVED,
        PostStatus.REJECTED,
        PostStatus.REJECTED_PUBLIC,
        PostStatus.CHANGES_REQUIRED,
        PostStatus.DRAFT,
    ],
}

# Writer receives "changes required" feedback and can either resubmit or keep iterating.
ALLOWED_TRANSITIONS[PostStatus.CHANGES_REQUIRED] = {
    RoleName.WRITER: [PostStatus.DRAFT, PostStatus.IN_REVIEW],
    RoleName.EDITOR: [PostStatus.IN_REVIEW, PostStatus.DRAFT],
    RoleName.ADMIN: [PostStatus.IN_REVIEW, PostStatus.DRAFT],
}

# Rejected public submissions are terminal except for admin archive/revive.
ALLOWED_TRANSITIONS[PostStatus.REJECTED_PUBLIC] = {
    RoleName.ADMIN: [PostStatus.ARCHIVED, PostStatus.DRAFT],
}
