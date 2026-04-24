"""
Post HTTP controllers.
"""
from flask import request, g

from ..services.post_service import PostService
from ..services.analytics_service import AnalyticsService
from ..utils.pagination import get_page_params, paginate_query
from ..utils.responses import success_response, paginated_response
from ..utils.validators import (
    load_or_raise,
    PostCreateSchema,
    PostUpdateSchema,
    PostTransitionSchema,
)


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() in ("1", "true", "yes")


class PostController:
    # ---- Public list ----
    @staticmethod
    def list_public():
        params = get_page_params()
        q = PostService.build_list_query(
            category=request.args.get("category"),
            tag=request.args.get("tag"),
            search=request.args.get("q"),
            featured=_parse_bool(request.args.get("featured")),
            pinned=_parse_bool(request.args.get("pinned")),
            public_only=True,
        )
        items, total = paginate_query(q, params)
        return paginated_response(
            [p.to_dict(include_content=False) for p in items],
            params.page, params.per_page, total,
        )

    @staticmethod
    def get_public(slug: str):
        post = PostService.get_by_slug(slug, public_only=True)
        # Track view asynchronously-ish (simple inline for now).
        AnalyticsService.record_view(
            post,
            user_id=None,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            referrer=request.referrer,
        )
        return success_response(post.to_dict())

    # ---- Admin list ----
    @staticmethod
    def list_admin():
        params = get_page_params()
        q = PostService.build_list_query(
            status=request.args.get("status"),
            category=request.args.get("category"),
            author_id=request.args.get("author_id"),
            tag=request.args.get("tag"),
            search=request.args.get("q"),
            featured=_parse_bool(request.args.get("featured")),
            pinned=_parse_bool(request.args.get("pinned")),
        )
        items, total = paginate_query(q, params)
        return paginated_response(
            [p.to_dict(include_content=False) for p in items],
            params.page, params.per_page, total,
        )

    @staticmethod
    def get_admin(post_id: str):
        post = PostService.get_or_404(post_id)
        return success_response(post.to_dict())

    # ---- CRUD ----
    @staticmethod
    def create():
        data = load_or_raise(PostCreateSchema(), request.get_json(silent=True))
        post = PostService.create(data, g.current_user)
        return success_response(post.to_dict(), message="Post created", status=201)

    @staticmethod
    def update(post_id: str):
        data = load_or_raise(PostUpdateSchema(partial=True), request.get_json(silent=True))
        post = PostService.get_or_404(post_id)
        post = PostService.update(post, data, g.current_user)
        return success_response(post.to_dict(), message="Post updated")

    @staticmethod
    def delete(post_id: str):
        post = PostService.get_or_404(post_id)
        PostService.delete(post, g.current_user)
        return success_response(message="Post deleted")

    # ---- Workflow ----
    @staticmethod
    def submit_for_review(post_id: str):
        post = PostService.get_or_404(post_id)
        post = PostService.transition_status(post, "review", g.current_user, note="Submitted for review")
        return success_response(post.to_dict(), message="Submitted for review")

    @staticmethod
    def approve(post_id: str):
        post = PostService.get_or_404(post_id)
        note = (request.get_json(silent=True) or {}).get("note")
        post = PostService.transition_status(post, "approved", g.current_user, note=note)
        return success_response(post.to_dict(), message="Post approved")

    @staticmethod
    def reject(post_id: str):
        post = PostService.get_or_404(post_id)
        note = (request.get_json(silent=True) or {}).get("note")
        post = PostService.transition_status(post, "rejected", g.current_user, note=note)
        return success_response(post.to_dict(), message="Post rejected")

    @staticmethod
    def mark_ready(post_id: str):
        post = PostService.get_or_404(post_id)
        post = PostService.transition_status(post, "ready_to_publish", g.current_user, note="Queued for publish")
        return success_response(post.to_dict(), message="Ready to publish")

    @staticmethod
    def publish(post_id: str):
        post = PostService.get_or_404(post_id)
        post = PostService.transition_status(post, "published", g.current_user, note="Published")
        return success_response(post.to_dict(), message="Post published")

    @staticmethod
    def transition(post_id: str):
        """Generic transition endpoint driven by the validator + state machine."""
        data = load_or_raise(PostTransitionSchema(), request.get_json(silent=True))
        post = PostService.get_or_404(post_id)
        post = PostService.transition_status(post, data["status"], g.current_user, note=data.get("note"))
        return success_response(post.to_dict(), message=f"Post moved to {data['status']}")

    # ---- Versions ----
    @staticmethod
    def list_versions(post_id: str):
        from ..models.post import PostVersion
        post = PostService.get_or_404(post_id)
        versions = PostVersion.objects(post=post).order_by("-version")
        return success_response([v.to_dict() for v in versions])
