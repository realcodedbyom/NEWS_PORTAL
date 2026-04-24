"""
Background scheduler jobs.

- Auto-publish posts that are ready_to_publish and whose publish_at has passed.
- Auto-archive published posts whose expires_at has passed.
"""
import logging
from datetime import datetime

from flask import current_app

from ..models.post import Post
from ..utils.enums import PostStatus


logger = logging.getLogger(__name__)


def run_scheduled_jobs() -> None:
    """Called periodically by APScheduler."""
    try:
        _auto_publish_due_posts()
        _auto_archive_expired_posts()
    except Exception:
        logger.exception("Scheduler iteration failed")


def _auto_publish_due_posts() -> None:
    now = datetime.utcnow()
    count = Post.objects(
        status=PostStatus.READY_TO_PUBLISH.value,
        publish_at__ne=None,
        publish_at__lte=now,
    ).update(set__status=PostStatus.PUBLISHED.value, set__published_at=now)
    if count:
        current_app.logger.info("Auto-published %d scheduled post(s)", count)


def _auto_archive_expired_posts() -> None:
    now = datetime.utcnow()
    count = Post.objects(
        status=PostStatus.PUBLISHED.value,
        expires_at__ne=None,
        expires_at__lte=now,
    ).update(set__status=PostStatus.ARCHIVED.value)
    if count:
        current_app.logger.info("Auto-archived %d expired post(s)", count)
