"""
Post service: CRUD, workflow transitions, versioning, listings,
public submissions, moderation notes, and notification hooks.

All write operations create a PostVersion snapshot so nothing is lost.
Workflow enforcement lives in `transition_status` and uses the
ALLOWED_TRANSITIONS map as the single source of truth.
"""
from datetime import datetime, timedelta
from typing import Iterable

from bson import ObjectId
from bson.errors import InvalidId
from mongoengine import Q
from mongoengine.errors import ValidationError as MEValidationError

from ..models.post import (
    Post,
    PostVersion,
    StatusHistoryEntry,
    ModerationNote,
)
from ..models.tag import Tag
from ..models.media import Media
from ..models.user import User
from ..utils.enums import PostStatus, PostCategory, RoleName, ALLOWED_TRANSITIONS
from ..utils.exceptions import NotFound, Forbidden, WorkflowError, BadRequest, TooManyRequests
from ..utils.slug import generate_unique_slug
from .notification_service import NotificationService


# Anti-spam: maximum public submissions per rolling 24h window per user.
DAILY_PUBLIC_SUBMISSION_LIMIT = 5

# Minimum sizes for post payloads. Enforced at the service layer so every
# caller (JSON API, web CMS form, public submit) gets the same guarantee,
# regardless of whether the caller also runs marshmallow validation.
MIN_TITLE_LENGTH = 3
MIN_CONTENT_LENGTH = 20

# Transitions that carry author-facing feedback. When a note is provided
# for one of these, the note is also appended to post.moderation_notes so
# it survives subsequent transitions (status_note is transient).
_FEEDBACK_STATUSES: frozenset = frozenset({
    PostStatus.CHANGES_REQUIRED,
    PostStatus.REJECTED,
    PostStatus.REJECTED_PUBLIC,
})


def _validate_post_payload(data: dict, partial: bool = False) -> None:
    """Validate title + content length. Raise BadRequest on failure.

    When `partial=True` (update path), only validate fields that are
    actually present in the payload — omitted fields keep their
    existing values and don't need re-validation.
    """
    if not partial or "title" in data:
        title = (data.get("title") or "").strip()
        if len(title) < MIN_TITLE_LENGTH:
            raise BadRequest(
                f"Title must be at least {MIN_TITLE_LENGTH} characters."
            )
    if not partial or "content" in data:
        content = (data.get("content") or "").strip()
        if len(content) < MIN_CONTENT_LENGTH:
            raise BadRequest(
                f"Content must be at least {MIN_CONTENT_LENGTH} characters."
            )


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
    def create(
        data: dict,
        author: User,
        images: list[Media] | None = None,
    ) -> Post:
        """Create a post from the CMS.

        - Optional `images` list (from multipart uploads) supplies the
          featured image + gallery when `data` doesn't already specify them.
        - If `author` is an admin, the post is auto-published immediately
          (admins bypass the draft -> review -> publish chain).
        """
        _validate_post_payload(data)
        slug_source = data.get("slug") or data["title"]

        # Resolve featured image: explicit ID wins over uploaded files.
        featured_image = _resolve_media(data.get("featured_image_id"))
        extra_images = [m for m in (images or []) if m]
        if featured_image is None and extra_images:
            featured_image = extra_images[0]
            extra_images = extra_images[1:]

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
            featured_image=featured_image,
        )

        PostService._attach_tags(post, data.get("tags", []))
        PostService._attach_gallery(post, data.get("gallery_ids", []))
        if extra_images:
            post.gallery.extend(extra_images)

        # Admin fast-path: admins bypass the draft -> review -> publish chain.
        # If they chose a future publish_at we stage the post in
        # ready_to_publish so the scheduler can flip it to published at the
        # scheduled time (and fire the right notifications).
        is_admin = bool(
            author and author.has_role(RoleName.ADMIN.value)
        )
        admin_autopublish = False
        admin_schedule = False
        if is_admin:
            now = datetime.utcnow()
            post.editor = post.editor or author
            if post.publish_at and post.publish_at > now:
                post.status = PostStatus.READY_TO_PUBLISH.value
                admin_schedule = True
            else:
                post.status = PostStatus.PUBLISHED.value
                post.publisher = author
                post.published_at = now
                if not post.publish_at:
                    post.publish_at = now
                admin_autopublish = True

        post.save()
        if admin_autopublish:
            snapshot_note = "Admin auto-publish"
        elif admin_schedule:
            snapshot_note = "Admin scheduled for publish"
        else:
            snapshot_note = "Created"
        PostService._snapshot(post, author, note=snapshot_note)

        if admin_autopublish:
            # Fire PUBLISHED event so interested listeners (editors, etc.)
            # get notified. Self-notify is skipped inside NotificationService.
            NotificationService.dispatch_status_change(
                post, PostStatus.PUBLISHED.value, author
            )
        elif admin_schedule:
            # Stage the scheduler with the ready_to_publish event — the
            # scheduler will fire PUBLISHED when it flips the status.
            NotificationService.dispatch_status_change(
                post, PostStatus.READY_TO_PUBLISH.value, author
            )
        return post

    # ---------- Public submission ----------
    @staticmethod
    def submit_public(
        data: dict,
        author: User,
        images: list[Media] | None = None,
    ) -> Post:
        """Create a post from a public contributor.

        - Applies rolling-24h rate limit (DAILY_PUBLIC_SUBMISSION_LIMIT).
        - Marks is_public_submission=True and status=PENDING_REVIEW.
        - First image (if any) becomes featured_image; the rest go to gallery.
        - Increments author.submission_count atomically.
        - Fires the notification hook for PENDING_REVIEW.
        """
        _validate_post_payload(data)
        PostService._enforce_daily_submission_limit(author)

        images = [m for m in (images or []) if m]
        featured_image = images[0] if images else None
        gallery_images = list(images[1:]) if len(images) > 1 else []

        slug_source = data.get("slug") or data["title"]
        post = Post(
            title=data["title"].strip(),
            subtitle=data.get("subtitle"),
            slug=generate_unique_slug(slug_source, Post),
            content=data["content"],
            excerpt=data.get("excerpt"),
            category=data.get("category", PostCategory.NEWS.value),
            status=PostStatus.PENDING_REVIEW.value,
            is_public_submission=True,
            author=author,
            featured_image=featured_image,
            gallery=gallery_images,
        )
        PostService._attach_tags(post, data.get("tags", []))
        post.save()

        # Bump the submitter's counter atomically and mirror in-memory.
        User.objects(id=author.id).update_one(inc__submission_count=1)
        author.submission_count = (author.submission_count or 0) + 1

        PostService._snapshot(post, author, note="Public submission received")
        NotificationService.dispatch_status_change(
            post, PostStatus.PENDING_REVIEW.value, author
        )
        return post

    # ---------- Update ----------
    @staticmethod
    def update(
        post: Post,
        data: dict,
        actor: User,
        images: list[Media] | None = None,
    ) -> Post:
        PostService._assert_can_edit(post, actor)
        _validate_post_payload(data, partial=True)

        for field in ("title", "subtitle", "content", "excerpt", "category",
                      "is_featured", "is_announcement", "is_pinned",
                      "publish_at", "expires_at"):
            if field in data:
                setattr(post, field, data[field])

        explicit_featured = "featured_image_id" in data
        if explicit_featured:
            post.featured_image = _resolve_media(data.get("featured_image_id"))

        if data.get("slug"):
            post.slug = generate_unique_slug(data["slug"], Post)

        if "tags" in data:
            post.tags = []
            PostService._attach_tags(post, data["tags"])

        if "gallery_ids" in data:
            post.gallery = []
            PostService._attach_gallery(post, data["gallery_ids"])

        # New uploads from the edit form: only fill featured_image if the
        # post has none AND the caller didn't explicitly set one. Extras
        # always append to the existing gallery.
        extra_images = [m for m in (images or []) if m]
        if extra_images:
            if post.featured_image is None and not explicit_featured:
                post.featured_image = extra_images[0]
                extra_images = extra_images[1:]
            if extra_images:
                post.gallery = list(post.gallery or []) + extra_images

        post.save()
        PostService._snapshot(post, actor, note="Updated")
        return post

    # ---------- Inline media management ----------
    @staticmethod
    def clear_featured_image(post: Post) -> Post:
        """Detach the featured image from this post.

        The underlying Media document is NOT deleted so it remains
        available in the library / other posts.
        """
        post.featured_image = None
        post.save()
        return post

    @staticmethod
    def remove_gallery_item(post: Post, media_id) -> Post:
        """Detach a single media from this post's gallery (non-destructive)."""
        target = str(media_id)
        post.gallery = [
            m for m in (post.gallery or [])
            if m and str(m.id) != target
        ]
        post.save()
        return post

    # ---------- Delete ----------
    @staticmethod
    def delete(post: Post, actor: User) -> None:
        # Only admins or the original author (if still draft) can hard-delete.
        if not actor.has_role(RoleName.ADMIN.value):
            if post.author_id != str(actor.id) or post.status != PostStatus.DRAFT.value:
                raise Forbidden("You cannot delete this post")
        post.delete()

    # ---------- Moderation ----------
    @staticmethod
    def add_moderation_note(post: Post, actor: User, note: str) -> Post:
        """Attach a moderation note (editors/admins only)."""
        if not actor.has_any_role(RoleName.EDITOR.value, RoleName.ADMIN.value):
            raise Forbidden("Only editors or admins can add moderation notes")
        text = (note or "").strip()
        if not text:
            raise BadRequest("Note cannot be empty")

        entry = ModerationNote(author=actor, note=text, created_at=datetime.utcnow())
        # Atomic push so we don't race with concurrent updates to the post.
        Post.objects(id=post.id).update_one(push__moderation_notes=entry)
        post.moderation_notes = list(post.moderation_notes or []) + [entry]
        return post

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

        # Feedback-producing transitions: persist the note as a permanent
        # ModerationNote so the author has a durable record. status_note
        # is overwritten on the next transition, so it alone isn't enough.
        note_text = (note or "").strip()
        if target in _FEEDBACK_STATUSES and note_text and actor:
            entry = ModerationNote(
                author=actor,
                note=note_text,
                created_at=datetime.utcnow(),
            )
            Post.objects(id=post.id).update_one(push__moderation_notes=entry)
            post.moderation_notes = list(post.moderation_notes or []) + [entry]

        PostService._snapshot(
            post,
            actor,
            note=f"Status -> {target.value}" + (f" ({note})" if note else ""),
        )
        # Fire notifications after the status change is durable.
        NotificationService.dispatch_status_change(post, target.value, actor)
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
        public_submission: bool | None = None,
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
        if public_submission is not None:
            q = q.filter(is_public_submission=public_submission)

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

    # ---------- Anti-spam ----------
    @staticmethod
    def check_daily_submission_limit(
        author: User, limit: int = DAILY_PUBLIC_SUBMISSION_LIMIT
    ) -> None:
        """Public pre-flight check so callers can reject a request before
        spending Cloudinary uploads. `submit_public` also calls this internally
        as defense-in-depth."""
        PostService._enforce_daily_submission_limit(author, limit=limit)

    # ---------- Internals ----------
    @staticmethod
    def _enforce_daily_submission_limit(
        author: User, limit: int = DAILY_PUBLIC_SUBMISSION_LIMIT
    ) -> None:
        """Refuse more than `limit` public submissions in a rolling 24h window."""
        since = datetime.utcnow() - timedelta(hours=24)
        count = Post.objects(
            author=author,
            is_public_submission=True,
            created_at__gte=since,
        ).count()
        if count >= limit:
            raise TooManyRequests(
                f"Submission limit reached ({limit} per 24 hours). "
                "Please try again later."
            )

    @staticmethod
    def _assert_can_edit(post: Post, actor: User) -> None:
        if actor.has_role(RoleName.ADMIN.value) or actor.has_role(RoleName.EDITOR.value):
            return
        if actor.has_role(RoleName.WRITER.value) and post.author_id == str(actor.id):
            # Writers can edit their own drafts, rejected posts, and anything
            # bounced back with changes_required.
            if post.status in (
                PostStatus.DRAFT.value,
                PostStatus.REJECTED.value,
                PostStatus.REJECTED_PUBLIC.value,
                PostStatus.CHANGES_REQUIRED.value,
            ):
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
        """Snapshot the post content + append a status_history row if status changed.

        Keeping both in one place guarantees every meaningful write leaves
        an audit trail on both the versions collection (full content) and
        the embedded status_history list (lightweight timeline).
        """
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

        # Append a status_history entry only when the status actually differs
        # from the last recorded entry (or when this is the first entry).
        history = post.status_history or []
        last_status = history[-1].status if history else None
        if last_status != post.status:
            entry = StatusHistoryEntry(
                status=post.status,
                changed_by=actor,
                changed_at=datetime.utcnow(),
                note=note,
            )
            # Atomic push avoids races with concurrent post.save() calls.
            Post.objects(id=post.id).update_one(push__status_history=entry)
            post.status_history = list(history) + [entry]
