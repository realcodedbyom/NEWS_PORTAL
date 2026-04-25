"""
Background scheduler jobs.

- Auto-publish posts that are ready_to_publish and whose publish_at has passed.
- Auto-archive published posts whose expires_at has passed.

Each transition is persisted per-document (not a bulk update) so that:
- the Post's status_history gets a new entry,
- notifications fire to the author (and editor on publish).
"""
import logging
from datetime import datetime

from flask import current_app

from ..models.post import Post, StatusHistoryEntry
from ..utils.enums import PostStatus
from .notification_service import NotificationService


logger = logging.getLogger(__name__)


def run_scheduled_jobs() -> None:
    """Called periodically by APScheduler."""
    try:
        _auto_publish_due_posts()
        _auto_archive_expired_posts()
    except Exception:
        logger.exception("Scheduler iteration failed")


def _apply_auto_transition(post: Post, new_status: str, note: str) -> None:
    """Set status, published_at (if needed), append history, fire notifications."""
    now = datetime.utcnow()
    post.status = new_status
    if new_status == PostStatus.PUBLISHED.value and not post.published_at:
        post.published_at = now

    entry = StatusHistoryEntry(
        status=new_status,
        changed_by=None,  # scheduler-driven, no human actor
        changed_at=now,
        note=note,
    )
    post.status_history = list(post.status_history or []) + [entry]
    post.save()

    NotificationService.dispatch_status_change(post, new_status, actor=None)


def _auto_publish_due_posts() -> None:
    now = datetime.utcnow()
    due = list(
        Post.objects(
            status=PostStatus.READY_TO_PUBLISH.value,
            publish_at__ne=None,
            publish_at__lte=now,
        )
    )
    if not due:
        return
    for post in due:
        _apply_auto_transition(
            post, PostStatus.PUBLISHED.value, note="Auto-published by scheduler"
        )
    current_app.logger.info("Auto-published %d scheduled post(s)", len(due))


def _auto_archive_expired_posts() -> None:
    now = datetime.utcnow()
    expired = list(
        Post.objects(
            status=PostStatus.PUBLISHED.value,
            expires_at__ne=None,
            expires_at__lte=now,
        )
    )
    if not expired:
        return
    for post in expired:
        _apply_auto_transition(
            post, PostStatus.ARCHIVED.value, note="Auto-archived (expired)"
        )
    current_app.logger.info("Auto-archived %d expired post(s)", len(expired))
