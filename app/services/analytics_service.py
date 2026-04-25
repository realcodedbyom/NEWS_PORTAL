"""
Analytics service: track views + aggregate dashboard metrics.
"""
import hashlib
from datetime import datetime, timedelta

from bson.errors import InvalidId
from mongoengine.errors import ValidationError as MEValidationError

from ..models.post import Post
from ..models.user import User
from ..models.alumni import Alumni
from ..models.analytics import PostView
from ..utils.enums import PostStatus


class AnalyticsService:
    @staticmethod
    def record_view(post: Post, *, user_id=None, ip: str | None, user_agent: str | None, referrer: str | None) -> None:
        ip_hash = None
        if ip:
            ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()

        user_ref = None
        if user_id:
            try:
                user_ref = User.objects(id=user_id).first()
            except (MEValidationError, InvalidId):
                user_ref = None

        PostView(
            post=post,
            user=user_ref,
            ip_hash=ip_hash,
            user_agent=(user_agent or "")[:500],
            referrer=(referrer or "")[:500],
        ).save()

        # Atomic increment on the post for cheap reads.
        Post.objects(id=post.id).update_one(inc__view_count=1)
        # Also update the in-memory instance so callers see the new count.
        post.view_count = (post.view_count or 0) + 1

    @staticmethod
    def dashboard_summary() -> dict:
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)

        total_posts = Post.objects.count()
        published = Post.objects(status=PostStatus.PUBLISHED.value).count()
        # Count both legacy REVIEW and the new IN_REVIEW together.
        in_review = Post.objects(
            status__in=[PostStatus.REVIEW.value, PostStatus.IN_REVIEW.value]
        ).count()
        pending_public = Post.objects(
            status=PostStatus.PENDING_REVIEW.value,
            is_public_submission=True,
        ).count()
        scheduled = Post.objects(
            status=PostStatus.READY_TO_PUBLISH.value,
            publish_at__ne=None,
        ).count()
        total_views = PostView.objects.count()
        weekly_views = PostView.objects(viewed_at__gte=week_ago).count()
        total_users = User.objects.count()
        total_alumni = Alumni.objects.count()

        return {
            "posts": {
                "total": total_posts,
                "published": published,
                "in_review": in_review,
                "pending_public": pending_public,
                "scheduled": scheduled,
            },
            "views": {"total": total_views, "last_7_days": weekly_views},
            "users": total_users,
            "alumni": total_alumni,
        }

    @staticmethod
    def top_posts(limit: int = 10, days: int | None = 30) -> list[dict]:
        """Top-viewed published posts.

        Uses the cached `view_count` on each Post. The `days` argument is
        accepted for API compatibility but currently ignored in favour of
        the lifetime view counter.
        """
        q = (
            Post.objects(status=PostStatus.PUBLISHED.value)
            .order_by("-view_count")
            .limit(limit)
        )
        return [
            {
                "id": str(p.id),
                "title": p.title,
                "slug": p.slug,
                "category": p.category,
                "views": int(p.view_count or 0),
                "published_at": p.published_at.isoformat() if p.published_at else None,
            }
            for p in q
        ]
