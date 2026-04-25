"""
Notification service.

Sends per-user notifications on workflow events and exposes a single
`dispatch_status_change` hook that PostService calls whenever a post
transitions state. Also handles listing / mark-as-read for the API.
"""
from __future__ import annotations

import logging
from typing import Iterable

from ..models.notification import Notification
from ..models.post import Post
from ..models.role import Role
from ..models.user import User
from ..utils.enums import NotificationType, PostStatus, RoleName
from ..utils.exceptions import Forbidden


logger = logging.getLogger(__name__)


class NotificationService:
    # ---------- Low-level writes ----------
    @staticmethod
    def notify(
        user: User | None,
        type_: str,
        message: str,
        post: Post | None = None,
    ) -> Notification | None:
        """Persist a single notification for `user`. Silently skipped if user is None."""
        if user is None:
            return None
        notification = Notification(
            user=user,
            type=type_,
            message=message,
            post=post,
        )
        notification.save()
        return notification

    @staticmethod
    def notify_many(
        users: Iterable[User],
        type_: str,
        message: str,
        post: Post | None = None,
    ) -> int:
        count = 0
        for u in users:
            if NotificationService.notify(u, type_, message, post=post):
                count += 1
        return count

    @staticmethod
    def notify_role(
        role_name: str,
        type_: str,
        message: str,
        post: Post | None = None,
        exclude: Iterable[User] | None = None,
    ) -> int:
        """Notify every active user who holds `role_name`, minus anyone in `exclude`."""
        role = Role.objects(name=role_name).first()
        if not role:
            return 0
        excluded_ids = {str(u.id) for u in (exclude or []) if u}
        recipients = [
            u for u in User.objects(roles=role, is_active=True)
            if str(u.id) not in excluded_ids
        ]
        return NotificationService.notify_many(recipients, type_, message, post=post)

    # ---------- Reads ----------
    @staticmethod
    def list_for(user: User, *, unread_only: bool = False):
        q = Notification.objects(user=user)
        if unread_only:
            q = q.filter(is_read=False)
        return q.order_by("-created_at")

    @staticmethod
    def unread_count(user: User) -> int:
        return Notification.objects(user=user, is_read=False).count()

    @staticmethod
    def mark_read(notification: Notification, user: User) -> Notification:
        if str(notification.user_id) != str(user.id):
            raise Forbidden("Cannot modify another user's notification")
        if not notification.is_read:
            notification.is_read = True
            notification.save()
        return notification

    @staticmethod
    def mark_all_read(user: User) -> int:
        return Notification.objects(user=user, is_read=False).update(set__is_read=True)

    # ---------- Event dispatch ----------
    @staticmethod
    def dispatch_status_change(
        post: Post,
        new_status: str,
        actor: User | None,
    ) -> None:
        """Fire the appropriate notifications for a status transition.

        Safe to call from any flow (manual transition, public submit,
        scheduler). Any failure is logged but never re-raised — a notify
        failure must not abort the underlying workflow.
        """
        try:
            NotificationService._dispatch(post, new_status, actor)
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "Notification dispatch failed for post=%s status=%s",
                getattr(post, "id", None),
                new_status,
            )

    @staticmethod
    def _dispatch(post: Post, new_status: str, actor: User | None) -> None:
        author = post.author
        title = (post.title or "Untitled")[:80]
        is_public = bool(post.is_public_submission)
        author_name = author.name if author else "Unknown"

        if new_status == PostStatus.PENDING_REVIEW.value:
            # Public submission just received.
            NotificationService.notify(
                author,
                NotificationType.SUBMISSION_RECEIVED.value,
                f"Your submission '{title}' has been received and is pending review.",
                post=post,
            )
            NotificationService.notify_role(
                RoleName.EDITOR.value,
                NotificationType.NEW_SUBMISSION.value,
                f"New public submission: '{title}' by {author_name}",
                post=post,
                exclude=[author] if author else None,
            )
            return

        if new_status in (PostStatus.REVIEW.value, PostStatus.IN_REVIEW.value):
            # Editor review started. Tell the editors queue + tell the writer if public.
            if is_public:
                NotificationService.notify(
                    author,
                    NotificationType.SUBMISSION_RECEIVED.value,
                    f"Your submission '{title}' is now being reviewed.",
                    post=post,
                )
            NotificationService.notify_role(
                RoleName.EDITOR.value,
                NotificationType.NEW_SUBMISSION.value,
                f"'{title}' submitted for review by {author_name}",
                post=post,
                exclude=[author] if author else None,
            )
            return

        if new_status == PostStatus.CHANGES_REQUIRED.value:
            NotificationService.notify(
                author,
                NotificationType.CHANGES_REQUIRED.value,
                f"Changes required on '{title}'. Please review moderator notes.",
                post=post,
            )
            return

        if new_status == PostStatus.APPROVED.value:
            NotificationService.notify(
                author,
                NotificationType.APPROVED.value,
                f"Your post '{title}' has been approved.",
                post=post,
            )
            NotificationService.notify_role(
                RoleName.ADMIN.value,
                NotificationType.APPROVED.value,
                f"'{title}' approved by {actor.name if actor else 'editor'} and awaiting final action.",
                post=post,
                exclude=[actor] if actor else None,
            )
            return

        if new_status == PostStatus.READY_TO_PUBLISH.value:
            NotificationService.notify_role(
                RoleName.ADMIN.value,
                NotificationType.READY_FOR_PUBLISH.value,
                f"'{title}' is ready to publish.",
                post=post,
                exclude=[actor] if actor else None,
            )
            return

        if new_status == PostStatus.PUBLISHED.value:
            NotificationService.notify(
                author,
                NotificationType.PUBLISHED.value,
                f"Your post '{title}' has been published!",
                post=post,
            )
            if post.editor and (not author or str(post.editor.id) != str(author.id)):
                NotificationService.notify(
                    post.editor,
                    NotificationType.PUBLISHED.value,
                    f"'{title}' has been published.",
                    post=post,
                )
            return

        if new_status in (PostStatus.REJECTED.value, PostStatus.REJECTED_PUBLIC.value):
            NotificationService.notify(
                author,
                NotificationType.REJECTED.value,
                f"Your post '{title}' was rejected."
                + (" See moderator notes for details." if post.moderation_notes else ""),
                post=post,
            )
            return

        if new_status == PostStatus.ARCHIVED.value:
            NotificationService.notify(
                author,
                NotificationType.ARCHIVED.value,
                f"Your post '{title}' has been archived.",
                post=post,
            )
            return
