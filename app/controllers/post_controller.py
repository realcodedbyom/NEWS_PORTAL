"""
Post HTTP controllers.
"""
from flask import request, g
from mongoengine import Q
from werkzeug.datastructures import FileStorage

from ..models.post import Post
from ..services.post_service import PostService
from ..services.analytics_service import AnalyticsService
from ..services.media_service import MediaService
from ..utils.enums import PostStatus
from ..utils.pagination import get_page_params, paginate_query
from ..utils.responses import success_response, paginated_response
from ..utils.validators import (
    load_or_raise,
    PostCreateSchema,
    PostUpdateSchema,
    PostTransitionSchema,
    PublicSubmissionSchema,
    ModerationNoteSchema,
)


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() in ("1", "true", "yes")


def _parse_form_list(key: str) -> list[str]:
    """Read a repeated form field (e.g. tags=a&tags=b) or a single CSV string."""
    vals = request.form.getlist(key)
    if len(vals) == 1 and "," in vals[0]:
        return [v.strip() for v in vals[0].split(",") if v.strip()]
    return [v.strip() for v in vals if v and v.strip()]


def _collect_image_files() -> list[FileStorage]:
    """Collect uploaded image files from a multipart request.

    Accepts any of: `images`, `images[]`, or `image` (repeated) form keys.
    """
    buckets: list[FileStorage] = []
    for key in ("images", "images[]", "image"):
        buckets.extend(request.files.getlist(key))
    # de-dup identical FileStorage refs while preserving order
    seen_ids: set[int] = set()
    unique: list[FileStorage] = []
    for f in buckets:
        if id(f) in seen_ids:
            continue
        seen_ids.add(id(f))
        if f and f.filename:
            unique.append(f)
    return unique


def _read_post_form_data() -> dict:
    """Parse post fields from a multipart/form request."""
    def _bool(v):
        return (v or "").lower() in ("1", "true", "yes", "on")

    return {
        "title": (request.form.get("title") or "").strip(),
        "subtitle": (request.form.get("subtitle") or "").strip() or None,
        "slug": (request.form.get("slug") or "").strip() or None,
        "content": request.form.get("content") or "",
        "excerpt": (request.form.get("excerpt") or "").strip() or None,
        "category": (request.form.get("category") or "news").strip(),
        "tags": _parse_form_list("tags"),
        "is_featured": _bool(request.form.get("is_featured")),
        "is_announcement": _bool(request.form.get("is_announcement")),
        "is_pinned": _bool(request.form.get("is_pinned")),
    }


def _is_multipart() -> bool:
    return bool(request.content_type and request.content_type.startswith("multipart/"))


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
        # Multipart path: images[] uploaded alongside post fields.
        if _is_multipart():
            raw = _read_post_form_data()
            data = load_or_raise(PostCreateSchema(), raw)
            files = _collect_image_files()
            media_items = (
                MediaService.upload_many(files, g.current_user, max_count=10)
                if files else []
            )
            if media_items:
                data["featured_image_id"] = str(media_items[0].id)
                data["gallery_ids"] = [str(m.id) for m in media_items[1:]]
            post = PostService.create(data, g.current_user)
            return success_response(post.to_dict(), message="Post created", status=201)

        # JSON path (unchanged behaviour)
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

    # ---- Public submission ----
    @staticmethod
    def submit_public():
        # Always multipart for the public form; accept JSON fallback for tests.
        if _is_multipart():
            raw = _read_post_form_data()
        else:
            raw = request.get_json(silent=True) or {}
        data = load_or_raise(PublicSubmissionSchema(), raw)
        # Pre-flight rate-limit check so API clients don't waste Cloudinary
        # uploads on requests that will be rejected anyway. submit_public()
        # re-checks internally as defense-in-depth.
        PostService.check_daily_submission_limit(g.current_user)
        files = _collect_image_files() if _is_multipart() else []
        media_items = (
            MediaService.upload_many(files, g.current_user, max_count=10)
            if files else []
        )
        post = PostService.submit_public(data, g.current_user, images=media_items)
        return success_response(post.to_dict(), message="Submission received", status=201)

    # ---- My submissions ----
    @staticmethod
    def list_mine():
        params = get_page_params()
        q = PostService.build_list_query(
            author_id=str(g.current_user.id),
            status=request.args.get("status"),
            category=request.args.get("category"),
        )
        items, total = paginate_query(q, params)
        return paginated_response(
            [p.to_dict(include_content=False) for p in items],
            params.page, params.per_page, total,
        )

    # ---- Moderation notes ----
    @staticmethod
    def add_moderation_note(post_id: str):
        data = load_or_raise(ModerationNoteSchema(), request.get_json(silent=True))
        post = PostService.get_or_404(post_id)
        post = PostService.add_moderation_note(post, g.current_user, data["note"])
        return success_response(post.to_dict(), message="Note added", status=201)

    # ---- Queues ----
    @staticmethod
    def list_public_queue():
        """Editor/admin queue: posts sitting in pending_review (public submissions)."""
        params = get_page_params()
        q = PostService.build_list_query(
            status=PostStatus.PENDING_REVIEW.value,
            public_submission=True,
        )
        items, total = paginate_query(q, params)
        return paginated_response(
            [p.to_dict(include_content=False) for p in items],
            params.page, params.per_page, total,
        )

    @staticmethod
    def list_review_queue():
        """Editor queue: posts in in_review (new) or review (legacy)."""
        params = get_page_params()
        status_arg = request.args.get("status")
        query = Post.objects
        if status_arg:
            query = query.filter(status=status_arg)
        else:
            query = query.filter(
                Q(status=PostStatus.IN_REVIEW.value) | Q(status=PostStatus.REVIEW.value)
            )
        query = query.order_by("-updated_at", "-created_at")
        items, total = paginate_query(query, params)
        return paginated_response(
            [p.to_dict(include_content=False) for p in items],
            params.page, params.per_page, total,
        )
