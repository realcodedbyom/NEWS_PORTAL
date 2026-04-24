"""
Post service: CRUD, workflow transitions, versioning, listings.

All write operations create a PostVersion snapshot so nothing is lost.
Workflow enforcement lives in `transition_status` and uses the
ALLOWED_TRANSITIONS map as the single source of truth.
"""
from datetime import datetime
from typing import Iterable

from bson import ObjectId
from bson.errors import InvalidId
from mongoengine import Q
from mongoengine.errors import ValidationError as MEValidationError

from ..models.post import Post, PostVersion
from ..models.tag import Tag
from ..models.media import Media
from ..models.user import User
from ..utils.enums import PostStatus, RoleName, ALLOWED_TRANSITIONS
from ..utils.exceptions import NotFound, Forbidden, WorkflowError, BadRequest
from ..utils.slug import generate_unique_slug


def _resolve_media(ref_id):
    """Resolve a media ObjectId-string to a Media doc, or None."""
    if not ref_id:
        return None
    try:
        return Media.objects(id=ref_id).first()
    except (MEValidationError, InvalidId):
        return None


class PostService:
    # ---------- Create ----------
    @staticmethod
    def create(data: dict, author: User) -> Post:
        slug_source = data.get("slug") or data["title"]
        post = Post(
            title=data["title"].strip(),
            subtitle=data.get("subtitle"),
            slug=generate_unique_slug(slug_source, Post),
            content=data["content"],
            excerpt=data.get("excerpt"),
            category=data["category"],
            status=PostStatus.DRAFT.value,
            is_featured=data.get("is_featured", False),
            is_announcement=data.get("is_announcement", False),
            is_pinned=data.get("is_pinned", False),
            publish_at=data.get("publish_at"),
            expires_at=data.get("expires_at"),
            author=author,
            featured_image=_resolve_media(data.get("featured_image_id")),
        )

        PostService._attach_tags(post, data.get("tags", []))
        PostService._attach_gallery(post, data.get("gallery_ids", []))

        post.save()
        PostService._snapshot(post, author, note="Created")
        return post

    # ---------- Update ----------
    @staticmethod
    def update(post: Post, data: dict, actor: User) -> Post:
        PostService._assert_can_edit(post, actor)

        for field in ("title", "subtitle", "content", "excerpt", "category",
                      "is_featured", "is_announcement", "is_pinned",
                      "publish_at", "expires_at"):
            if field in data:
                setattr(post, field, data[field])

        if "featured_image_id" in data:
            post.featured_image = _resolve_media(data.get("featured_image_id"))

        if data.get("slug"):
            post.slug = generate_unique_slug(data["slug"], Post)

        if "tags" in data:
            post.tags = []
            PostService._attach_tags(post, data["tags"])

        if "gallery_ids" in data:
            post.gallery = []
            PostService._attach_gallery(post, data["gallery_ids"])

        post.save()
        PostService._snapshot(post, actor, note="Updated")
        return post

    # ---------- Delete ----------
    @staticmethod
    def delete(post: Post, actor: User) -> None:
        # Only admins or the original author (if still draft) can hard-delete.
        if not actor.has_role(RoleName.ADMIN.value):
            if post.author_id != str(actor.id) or post.status != PostStatus.DRAFT.value:
                raise Forbidden("You cannot delete this post")
        post.delete()

    # ---------- Workflow ----------
    @staticmethod
    def transition_status(post: Post, new_status: str, actor: User, note: str | None = None) -> Post:
        try:
            current = PostStatus(post.status)
            target = PostStatus(new_status)
        except ValueError as exc:
            raise BadRequest(f"Invalid status: {exc}")

        # Check at least one of the actor's roles allows this transition.
        allowed = False
        for role_name in actor.role_names():
            try:
                role_enum = RoleName(role_name)
            except ValueError:
                continue
            if target in ALLOWED_TRANSITIONS.get(current, {}).get(role_enum, []):
                allowed = True
                break

        if not allowed:
            raise WorkflowError(
                f"Transition {current.value} -> {target.value} not allowed for your role"
            )

        # Side effects per target state.
        post.status = target.value
        post.status_note = note

        if target == PostStatus.REVIEW:
            pass  # Writer submits for review
        elif target == PostStatus.APPROVED:
            post.editor = actor
        elif target == PostStatus.READY_TO_PUBLISH:
            if not post.editor:
                post.editor = actor
        elif target == PostStatus.PUBLISHED:
            post.publisher = actor
            post.published_at = datetime.utcnow()
            # If no explicit publish_at was set, this is "publish now".
            if not post.publish_at:
                post.publish_at = post.published_at

        post.save()
        PostService._snapshot(
            post,
            actor,
            note=f"Status -> {target.value}" + (f" ({note})" if note else ""),
        )
        return post

    # ---------- Queries ----------
    @staticmethod
    def build_list_query(
        *,
        status: str | None = None,
        category: str | None = None,
        author_id: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        featured: bool | None = None,
        pinned: bool | None = None,
        public_only: bool = False,
    ):
        q = Post.objects

        if public_only:
            q = q.filter(status=PostStatus.PUBLISHED.value)
            q = q.filter(Q(expires_at=None) | Q(expires_at__gt=datetime.utcnow()))
        elif status:
            q = q.filter(status=status)

        if category:
            q = q.filter(category=category)

        if author_id:
            try:
                q = q.filter(author=ObjectId(author_id))
            except (InvalidId, TypeError):
                return Post.objects(id__in=[])  # empty queryset

        if featured is not None:
            q = q.filter(is_featured=featured)
        if pinned is not None:
            q = q.filter(is_pinned=pinned)

        if tag:
            tag_doc = Tag.objects(slug=tag).first()
            if not tag_doc:
                return Post.objects(id__in=[])
            q = q.filter(tags=tag_doc)

        if search:
            q = q.filter(Q(title__icontains=search) | Q(content__icontains=search))

        # Pinned first, then newest.
        return q.order_by("-is_pinned", "-published_at", "-created_at")

    @staticmethod
    def get_by_slug(slug: str, public_only: bool = False) -> Post:
        q = Post.objects(slug=slug)
        if public_only:
            q = q.filter(status=PostStatus.PUBLISHED.value)
        post = q.first()
        if not post:
            raise NotFound("Post not found")
        return post

    @staticmethod
    def get_or_404(post_id) -> Post:
        try:
            post = Post.objects(id=post_id).first()
        except (MEValidationError, InvalidId):
            post = None
        if not post:
            raise NotFound("Post not found")
        return post

    # ---------- Internals ----------
    @staticmethod
    def _assert_can_edit(post: Post, actor: User) -> None:
        if actor.has_role(RoleName.ADMIN.value) or actor.has_role(RoleName.EDITOR.value):
            return
        if actor.has_role(RoleName.WRITER.value) and post.author_id == str(actor.id):
            # Writers can edit their own drafts & rejected posts.
            if post.status in (PostStatus.DRAFT.value, PostStatus.REJECTED.value):
                return
        raise Forbidden("You cannot edit this post in its current state")

    @staticmethod
    def _attach_tags(post: Post, tag_names: Iterable[str]) -> None:
        for name in tag_names:
            name = (name or "").strip()
            if not name:
                continue
            post.tags.append(Tag.get_or_create(name))

    @staticmethod
    def _attach_gallery(post: Post, media_ids: Iterable) -> None:
        ids = [m for m in (media_ids or []) if m]
        if not ids:
            return
        try:
            media_items = list(Media.objects(id__in=ids))
        except (MEValidationError, InvalidId):
            return
        post.gallery.extend(media_items)

    @staticmethod
    def _snapshot(post: Post, actor: User, note: str | None = None) -> None:
        last = PostVersion.objects(post=post).order_by("-version").first()
        next_version = (last.version if last else 0) + 1
        PostVersion(
            post=post,
            version=next_version,
            title=post.title,
            subtitle=post.subtitle,
            content=post.content,
            excerpt=post.excerpt,
            category=post.category,
            status=post.status,
            changed_by=actor,
            change_note=note,
        ).save()
