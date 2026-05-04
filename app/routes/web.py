"""
Server-rendered HTML admin UI.

Uses Flask sessions (signed by SECRET_KEY) for authentication so editors
can sign in from a browser without handling JWTs. The JSON API under
/api/* continues to use JWT independently.
"""
from __future__ import annotations

from functools import wraps
from datetime import datetime

from bson.errors import InvalidId
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    g,
    abort,
)
from mongoengine import Q
from mongoengine.errors import ValidationError as MEValidationError

from ..models.user import User
from ..models.role import Role
from ..models.post import Post, PostVersion
from ..models.alumni import Alumni
from ..models.media import Media
from ..models.notification import Notification
from ..services.post_service import PostService
from ..services.alumni_service import AlumniService
from ..services.media_service import MediaService
from ..services.analytics_service import AnalyticsService
from ..services.notification_service import NotificationService
from ..utils.enums import PostStatus, PostCategory, RoleName, ALLOWED_TRANSITIONS
from ..utils.exceptions import AppException

web_bp = Blueprint(
    "web",
    __name__,
    template_folder="../templates",
    static_folder="../static",
)


# ---------- Helpers ----------

def _get_or_404(model, doc_id):
    """Return a document by id (string hex), aborting with 404 if missing/invalid."""
    try:
        obj = model.objects(id=doc_id).first()
    except (MEValidationError, InvalidId):
        obj = None
    if not obj:
        abort(404)
    return obj


def _current_user() -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    if getattr(g, "_current_user", None) is None:
        try:
            g._current_user = User.objects(id=uid).first()
        except (MEValidationError, InvalidId):
            g._current_user = None
    return g._current_user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _current_user():
            flash("Please sign in to continue.", "error")
            return redirect(url_for("web.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*role_names: str):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = _current_user()
            if not user:
                return redirect(url_for("web.login", next=request.path))
            if not user.has_any_role(*role_names):
                flash("You do not have permission to perform this action.", "error")
                return redirect(url_for("web.dashboard"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


@web_bp.app_context_processor
def _inject_globals():
    user = _current_user()
    # Cheap unread-count query so the bell badge stays in sync without
    # every view having to pass it explicitly.
    unread = NotificationService.unread_count(user) if user else 0
    return {
        "current_user": user,
        "now": datetime.utcnow(),
        "PostStatus": PostStatus,
        "PostCategory": PostCategory,
        "RoleName": RoleName,
        "unread_notifications_count": unread,
    }


# ---------- Root / uploads ----------

@web_bp.route("/")
def index():
    return redirect(url_for("web.news_home"))


@web_bp.route("/cms")
def cms_index():
    if _current_user():
        return redirect(url_for("web.dashboard"))
    return redirect(url_for("web.login"))


@web_bp.route("/cms/login")
def cms_login_alias():
    return redirect(url_for("web.login"))


def _live_posts_base_query():
    now = datetime.utcnow()
    return Post.objects(status=PostStatus.PUBLISHED.value).filter(
        Q(publish_at=None) | Q(publish_at__lte=now)
    ).filter(
        Q(expires_at=None) | Q(expires_at__gt=now)
    )


@web_bp.route("/news")
def news_home():
    featured_stories = list(
        _live_posts_base_query()
        .filter(is_featured=True)
        .order_by("-published_at", "-created_at")
        .limit(8)
    )
    featured_story = featured_stories[0] if featured_stories else None

    top_stories = list(
        _live_posts_base_query()
        .order_by("-is_pinned", "-published_at", "-created_at")
        .limit(8)
    )

    # Build carousel: all featured stories first, then top stories that
    # aren't already in the featured list, capped to 8 items for perf.
    # Only include posts with a featured_image so the carousel arrows
    # stay anchored to the hero photo on every slide.
    seen_ids = {str(p.id) for p in featured_stories if p.featured_image}
    carousel_items = [p for p in featured_stories if p.featured_image]
    for p in top_stories:
        if not p.featured_image:
            continue
        if str(p.id) not in seen_ids:
            carousel_items.append(p)
            seen_ids.add(str(p.id))
        if len(carousel_items) >= 8:
            break

    latest_updates = list(
        _live_posts_base_query()
        .order_by("-published_at", "-created_at")
        .limit(16)
    )

    by_category = {}
    for category in PostCategory.values():
        by_category[category] = list(
            _live_posts_base_query()
            .filter(category=category)
            .order_by("-published_at", "-created_at")
            .limit(4)
        )

    return render_template(
        "public/home.html",
        featured_story=featured_story,
        featured_stories=featured_stories,
        carousel_items=carousel_items,
        top_stories=top_stories,
        latest_updates=latest_updates,
        by_category=by_category,
        categories=PostCategory.values(),
    )


@web_bp.route("/news/search")
def news_search():
    # Cap length as defense-in-depth against pathological queries hitting
    # the regex-based icontains scan over all post content.
    q = (request.args.get("q") or "").strip()[:200]
    posts = []
    if q:
        posts = list(
            _live_posts_base_query()
            .filter(
                Q(title__icontains=q)
                | Q(subtitle__icontains=q)
                | Q(excerpt__icontains=q)
                | Q(content__icontains=q)
            )
            .order_by("-published_at", "-created_at")
            .limit(60)
        )
    top_stories = list(
        _live_posts_base_query()
        .order_by("-is_pinned", "-published_at", "-created_at")
        .limit(8)
    )
    return render_template(
        "public/search.html",
        q=q,
        posts=posts,
        categories=PostCategory.values(),
        top_stories=top_stories,
    )


@web_bp.route("/news/category/<string:category>")
def news_category(category: str):
    category = (category or "").strip().lower()
    if category not in PostCategory.values():
        abort(404)

    posts = list(
        _live_posts_base_query()
        .filter(category=category)
        .order_by("-published_at", "-created_at")
        .limit(40)
    )
    top_stories = list(
        _live_posts_base_query()
        .order_by("-is_pinned", "-published_at", "-created_at")
        .limit(8)
    )
    return render_template(
        "public/category.html",
        category=category,
        posts=posts,
        categories=PostCategory.values(),
        top_stories=top_stories,
    )


@web_bp.route("/news/<string:slug>")
def news_detail(slug: str):
    post = _live_posts_base_query().filter(slug=slug).first()
    if not post:
        abort(404)

    AnalyticsService.record_view(
        post,
        user_id=None,
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        referrer=request.referrer,
    )

    related_posts = list(
        _live_posts_base_query()
        .filter(category=post.category, id__ne=post.id)
        .order_by("-published_at", "-created_at")
        .limit(6)
    )
    top_stories = list(
        _live_posts_base_query()
        .order_by("-is_pinned", "-published_at", "-created_at")
        .limit(8)
    )

    return render_template(
        "public/detail.html",
        post=post,
        related_posts=related_posts,
        categories=PostCategory.values(),
        top_stories=top_stories,
    )


# ---------- Auth routes ----------

@web_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.objects(email=email).first()
        if not user or not user.verify_password(password):
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email), 401
        if not user.is_active:
            flash("This account has been disabled.", "error")
            return render_template("auth/login.html", email=email), 403

        user.last_login_at = datetime.utcnow()
        user.save()

        session.clear()
        session["user_id"] = str(user.id)
        session.permanent = True
        flash(f"Welcome back, {user.name}.", "success")
        return redirect(request.args.get("next") or url_for("web.dashboard"))
    return render_template("auth/login.html", email="")


@web_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("web.login"))


# ---------- Dashboard ----------

def _dashboard_extras_for_staff(user: User) -> tuple[list, list, int]:
    """Return (review_queue, public_queue, public_queue_count) for editors/admins.

    Non-staff users get empty lists and a zero count; keeps the dashboard
    view tidy without branching inside the template.
    """
    if not user.has_any_role(RoleName.EDITOR.value, RoleName.ADMIN.value):
        return [], [], 0
    review_queue = list(
        Post.objects.filter(
            Q(status=PostStatus.REVIEW.value) | Q(status=PostStatus.IN_REVIEW.value)
        )
        .order_by("-updated_at")
        .limit(8)
    )
    public_queue = list(
        Post.objects(
            status=PostStatus.PENDING_REVIEW.value,
            is_public_submission=True,
        )
        .order_by("-created_at")
        .limit(8)
    )
    public_queue_count = Post.objects(
        status=PostStatus.PENDING_REVIEW.value,
        is_public_submission=True,
    ).count()
    return review_queue, public_queue, public_queue_count


@web_bp.route("/dashboard")
@login_required
def dashboard():
    user = _current_user()
    summary = AnalyticsService.dashboard_summary()
    my_drafts = list(
        Post.objects(author=user).order_by("-updated_at").limit(5)
    )
    review_queue, public_queue, public_queue_count = _dashboard_extras_for_staff(user)
    recent_notifications = list(
        NotificationService.list_for(user).limit(5)
    )
    return render_template(
        "dashboard.html",
        summary=summary,
        my_drafts=my_drafts,
        review_queue=review_queue,
        public_queue=public_queue,
        public_queue_count=public_queue_count,
        recent_notifications=recent_notifications,
    )


# ---------- Posts ----------

@web_bp.route("/posts")
@login_required
def posts_list():
    status = request.args.get("status") or ""
    q = request.args.get("q") or ""
    query = Post.objects
    if status:
        query = query.filter(status=status)
    if q:
        query = query.filter(Q(title__icontains=q) | Q(slug__icontains=q))
    posts = list(query.order_by("-updated_at").limit(100))
    return render_template(
        "posts/list.html",
        posts=posts,
        status=status,
        q=q,
        statuses=PostStatus.values(),
    )


@web_bp.route("/posts/new", methods=["GET", "POST"])
@login_required
@roles_required(RoleName.WRITER.value, RoleName.EDITOR.value, RoleName.ADMIN.value)
def post_new():
    user = _current_user()
    if request.method == "POST":
        data = _read_post_form()
        files = _collect_post_images()
        images: list[Media] = []
        if files:
            try:
                images = MediaService.upload_many(files, user, max_count=10)
            except AppException as exc:
                flash(exc.message, "error")
                return render_template("posts/form.html", post=None, form=data,
                                       categories=PostCategory.values()), exc.status_code
        try:
            post = PostService.create(data=data, author=user, images=images)
        except AppException as exc:
            # Roll back any uploaded media so we don't orphan Cloudinary assets.
            for m in images:
                try:
                    MediaService.delete(m)
                except Exception:
                    pass
            flash(exc.message, "error")
            return render_template("posts/form.html", post=None, form=data,
                                   categories=PostCategory.values()), exc.status_code
        if post.status == PostStatus.PUBLISHED.value:
            flash("Post published.", "success")
            return redirect(url_for("web.post_detail", post_id=str(post.id)))
        flash("Draft created.", "success")
        return redirect(url_for("web.post_edit", post_id=str(post.id)))
    return render_template("posts/form.html", post=None, form={}, categories=PostCategory.values())


@web_bp.route("/posts/<string:post_id>", methods=["GET"])
@login_required
def post_detail(post_id: str):
    post = _get_or_404(Post, post_id)
    versions = list(
        PostVersion.objects(post=post).order_by("-version").limit(20)
    )
    # Compute allowed next statuses for the current user, using ALLOWED_TRANSITIONS.
    try:
        current_status = PostStatus(post.status)
    except ValueError:
        current_status = PostStatus.DRAFT
    allowed_map = ALLOWED_TRANSITIONS.get(current_status, {})
    user = _current_user()
    next_statuses: list[str] = []
    for role_name in user.role_names():
        try:
            role_enum = RoleName(role_name)
        except ValueError:
            continue
        for st in allowed_map.get(role_enum, []):
            if st.value not in next_statuses:
                next_statuses.append(st.value)
    return render_template(
        "posts/detail.html",
        post=post,
        versions=versions,
        next_statuses=next_statuses,
    )


@web_bp.route("/posts/<string:post_id>/edit", methods=["GET", "POST"])
@login_required
def post_edit(post_id: str):
    post = _get_or_404(Post, post_id)
    user = _current_user()

    # Writers may only edit their own posts, and only in draft/rejected.
    if user.has_role(RoleName.WRITER.value) and not user.has_any_role(
        RoleName.EDITOR.value, RoleName.ADMIN.value
    ):
        if post.author_id != str(user.id):
            abort(403)

    if request.method == "POST":
        data = _read_post_form()
        files = _collect_post_images()
        images: list[Media] = []
        if files:
            try:
                images = MediaService.upload_many(files, user, max_count=10)
            except AppException as exc:
                flash(exc.message, "error")
                return render_template("posts/form.html", post=post, form=data,
                                       categories=PostCategory.values()), exc.status_code
        try:
            PostService.update(post=post, data=data, actor=user, images=images)
        except AppException as exc:
            for m in images:
                try:
                    MediaService.delete(m)
                except Exception:
                    pass
            flash(exc.message, "error")
            return render_template("posts/form.html", post=post, form=data,
                                   categories=PostCategory.values()), exc.status_code
        flash("Post updated.", "success")
        return redirect(url_for("web.post_detail", post_id=str(post.id)))

    form = {
        "title": post.title,
        "subtitle": post.subtitle or "",
        "content": post.content or "",
        "excerpt": post.excerpt or "",
        "category": post.category,
        "tags": ", ".join(t.name for t in (post.tags or []) if t),
        "is_featured": post.is_featured,
        "is_announcement": post.is_announcement,
        "is_pinned": post.is_pinned,
        "publish_at": post.publish_at.strftime("%Y-%m-%dT%H:%M") if post.publish_at else "",
        "expires_at": post.expires_at.strftime("%Y-%m-%dT%H:%M") if post.expires_at else "",
    }
    return render_template("posts/form.html", post=post, form=form, categories=PostCategory.values())


@web_bp.route("/posts/<string:post_id>/media/featured/clear", methods=["POST"])
@login_required
def post_media_featured_clear(post_id: str):
    post = _get_or_404(Post, post_id)
    _assert_can_edit_web(post, _current_user())
    PostService.clear_featured_image(post)
    flash("Featured image cleared.", "success")
    return redirect(url_for("web.post_edit", post_id=post_id))


@web_bp.route(
    "/posts/<string:post_id>/media/gallery/<string:media_id>/remove",
    methods=["POST"],
)
@login_required
def post_media_gallery_remove(post_id: str, media_id: str):
    post = _get_or_404(Post, post_id)
    _assert_can_edit_web(post, _current_user())
    PostService.remove_gallery_item(post, media_id)
    flash("Image removed from gallery.", "success")
    return redirect(url_for("web.post_edit", post_id=post_id))


@web_bp.route("/posts/<string:post_id>/moderation-note", methods=["POST"])
@login_required
@roles_required(RoleName.EDITOR.value, RoleName.ADMIN.value)
def post_moderation_note(post_id: str):
    post = _get_or_404(Post, post_id)
    note = (request.form.get("note") or "").strip()
    if not note:
        flash("Note cannot be empty.", "error")
        return redirect(url_for("web.post_detail", post_id=post_id))
    try:
        PostService.add_moderation_note(post, _current_user(), note)
    except AppException as exc:
        flash(exc.message, "error")
        return redirect(url_for("web.post_detail", post_id=post_id))
    flash("Moderation note added.", "success")
    return redirect(url_for("web.post_detail", post_id=post_id))


@web_bp.route("/posts/<string:post_id>/transition", methods=["POST"])
@login_required
def post_transition(post_id: str):
    post = _get_or_404(Post, post_id)
    target = request.form.get("target") or ""
    note = (request.form.get("note") or "").strip() or None
    try:
        PostService.transition_status(post=post, new_status=target, actor=_current_user(), note=note)
    except AppException as exc:
        flash(exc.message, "error")
        return redirect(url_for("web.post_detail", post_id=str(post.id)))
    flash(f"Post moved to '{target}'.", "success")
    return redirect(url_for("web.post_detail", post_id=str(post.id)))


@web_bp.route("/posts/<string:post_id>/delete", methods=["POST"])
@login_required
@roles_required(RoleName.ADMIN.value)
def post_delete(post_id: str):
    post = _get_or_404(Post, post_id)
    try:
        PostService.delete(post=post, actor=_current_user())
    except AppException as exc:
        flash(exc.message, "error")
        return redirect(url_for("web.post_detail", post_id=str(post.id)))
    flash("Post deleted.", "success")
    return redirect(url_for("web.posts_list"))


def _collect_post_images():
    """Return uploaded image files from the post form, filtering blanks."""
    return [f for f in request.files.getlist("images") if f and f.filename]


def _assert_can_edit_web(post, user):
    """Guard that reuses PostService's permission logic for the web layer."""
    try:
        PostService._assert_can_edit(post, user)
    except AppException:
        abort(403)


def _read_post_form() -> dict:
    def _parse_dt(val: str | None):
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None

    tags_raw = request.form.get("tags") or ""
    return {
        "title": (request.form.get("title") or "").strip(),
        "subtitle": (request.form.get("subtitle") or "").strip() or None,
        "content": request.form.get("content") or "",
        "excerpt": (request.form.get("excerpt") or "").strip() or None,
        "category": (request.form.get("category") or PostCategory.NEWS.value).strip(),
        "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
        "is_featured": bool(request.form.get("is_featured")),
        "is_announcement": bool(request.form.get("is_announcement")),
        "is_pinned": bool(request.form.get("is_pinned")),
        "publish_at": _parse_dt(request.form.get("publish_at")),
        "expires_at": _parse_dt(request.form.get("expires_at")),
    }


# ---------- Alumni ----------

@web_bp.route("/alumni")
@login_required
def alumni_list():
    q = request.args.get("q") or ""
    year = request.args.get("year", type=int)
    query = Alumni.objects
    if q:
        query = query.filter(
            Q(name__icontains=q)
            | Q(company__icontains=q)
            | Q(location__icontains=q)
        )
    if year:
        query = query.filter(graduation_year=year)
    alumni = list(query.order_by("-graduation_year", "name").limit(200))
    return render_template("alumni/list.html", alumni=alumni, q=q, year=year or "")


@web_bp.route("/alumni/new", methods=["GET", "POST"])
@login_required
@roles_required(RoleName.EDITOR.value, RoleName.ADMIN.value)
def alumni_new():
    if request.method == "POST":
        data = _read_alumni_form()
        try:
            record = AlumniService.create(data)
        except Exception as exc:
            flash(str(exc), "error")
            return render_template("alumni/form.html", alumni=None, form=data), 400
        flash("Alumni record created.", "success")
        return redirect(url_for("web.alumni_edit", alumni_id=str(record.id)))
    return render_template("alumni/form.html", alumni=None, form={})


@web_bp.route("/alumni/<string:alumni_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(RoleName.EDITOR.value, RoleName.ADMIN.value)
def alumni_edit(alumni_id: str):
    record = _get_or_404(Alumni, alumni_id)
    if request.method == "POST":
        data = _read_alumni_form()
        try:
            AlumniService.update(record, data)
        except Exception as exc:
            flash(str(exc), "error")
            return render_template("alumni/form.html", alumni=record, form=data), 400
        flash("Alumni record updated.", "success")
        return redirect(url_for("web.alumni_list"))
    form = {
        "name": record.name,
        "email": record.email or "",
        "graduation_year": record.graduation_year,
        "course": record.course,
        "current_role": record.current_role or "",
        "company": record.company or "",
        "location": record.location or "",
        "bio": record.bio or "",
        "is_featured": record.is_featured,
        "is_verified": record.is_verified,
    }
    return render_template("alumni/form.html", alumni=record, form=form)


@web_bp.route("/alumni/<string:alumni_id>/delete", methods=["POST"])
@login_required
@roles_required(RoleName.ADMIN.value)
def alumni_delete(alumni_id: str):
    record = _get_or_404(Alumni, alumni_id)
    AlumniService.delete(record)
    flash("Alumni record removed.", "success")
    return redirect(url_for("web.alumni_list"))


def _read_alumni_form() -> dict:
    def _int_or_none(val):
        try:
            return int(val) if val not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return {
        "name": (request.form.get("name") or "").strip(),
        "email": (request.form.get("email") or "").strip().lower() or None,
        "graduation_year": _int_or_none(request.form.get("graduation_year")) or 0,
        "course": (request.form.get("course") or "").strip(),
        "current_role": (request.form.get("current_role") or "").strip() or None,
        "company": (request.form.get("company") or "").strip() or None,
        "location": (request.form.get("location") or "").strip() or None,
        "bio": (request.form.get("bio") or "").strip() or None,
        "is_featured": bool(request.form.get("is_featured")),
        "is_verified": bool(request.form.get("is_verified")),
    }


# ---------- Media ----------

@web_bp.route("/media", methods=["GET", "POST"])
@login_required
def media_list():
    if request.method == "POST":
        file = request.files.get("file")
        alt = (request.form.get("alt_text") or "").strip() or None
        caption = (request.form.get("caption") or "").strip() or None
        try:
            MediaService.upload(file=file, uploader=_current_user(), alt_text=alt, caption=caption)
        except AppException as exc:
            flash(exc.message, "error")
            return redirect(url_for("web.media_list"))
        flash("File uploaded.", "success")
        return redirect(url_for("web.media_list"))

    items = list(Media.objects.order_by("-created_at").limit(60))
    return render_template("media/list.html", items=items)


@web_bp.route("/media/<string:media_id>/delete", methods=["POST"])
@login_required
@roles_required(RoleName.EDITOR.value, RoleName.ADMIN.value)
def media_delete(media_id: str):
    item = _get_or_404(Media, media_id)
    MediaService.delete(item)
    flash("Media removed.", "success")
    return redirect(url_for("web.media_list"))


# ---------- Notifications ----------

@web_bp.route("/cms/notifications")
@login_required
def notifications_list():
    user = _current_user()
    notifications = list(NotificationService.list_for(user).limit(100))
    return render_template("notifications.html", notifications=notifications)


@web_bp.route("/cms/notifications/<string:notification_id>/read", methods=["POST"])
@login_required
def notification_mark_read(notification_id: str):
    notification = _get_or_404(Notification, notification_id)
    try:
        NotificationService.mark_read(notification, _current_user())
    except AppException as exc:
        flash(exc.message, "error")
        return redirect(url_for("web.notifications_list"))
    # If the notification points at a live post, deep-link to it.
    # safe_post swallows stale-ref DoesNotExist so a deleted post
    # doesn't 500 the notification redirect.
    linked = notification.safe_post
    if linked:
        return redirect(url_for("web.post_detail", post_id=str(linked.id)))
    return redirect(url_for("web.notifications_list"))


@web_bp.route("/cms/notifications/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    NotificationService.mark_all_read(_current_user())
    flash("All notifications marked as read.", "success")
    return redirect(url_for("web.notifications_list"))


# ---------- Public submissions queue (editors/admins) ----------

@web_bp.route("/cms/public-queue")
@login_required
@roles_required(RoleName.EDITOR.value, RoleName.ADMIN.value)
def public_queue():
    posts = list(
        Post.objects(
            status=PostStatus.PENDING_REVIEW.value,
            is_public_submission=True,
        )
        .order_by("-created_at")
        .limit(100)
    )
    return render_template("public_queue.html", posts=posts)


# ---------- Internal review queue (editors/admins) ----------

@web_bp.route("/cms/review-queue")
@login_required
@roles_required(RoleName.EDITOR.value, RoleName.ADMIN.value)
def review_queue():
    posts = list(
        Post.objects.filter(
            Q(status=PostStatus.IN_REVIEW.value) | Q(status=PostStatus.REVIEW.value)
        )
        .order_by("-updated_at", "-created_at")
        .limit(100)
    )
    return render_template("review_queue.html", posts=posts)


# ---------- My submissions (writer dashboard) ----------

@web_bp.route("/my-submissions")
@login_required
def my_submissions():
    posts = list(
        Post.objects(author=_current_user())
        .order_by("-updated_at")
        .limit(200)
    )
    return render_template("my_submissions.html", posts=posts)


# ---------- Public submit form (any logged-in user) ----------

@web_bp.route("/submit", methods=["GET", "POST"])
@web_bp.route("/news/submit", methods=["GET", "POST"])
@login_required
def public_submit():
    user = _current_user()
    if request.method == "POST":
        form = {
            "title": (request.form.get("title") or "").strip(),
            "subtitle": (request.form.get("subtitle") or "").strip() or None,
            "content": request.form.get("content") or "",
            "excerpt": (request.form.get("excerpt") or "").strip() or None,
            "category": (request.form.get("category") or PostCategory.NEWS.value).strip(),
            "tags": [
                t.strip() for t in (request.form.get("tags") or "").split(",") if t.strip()
            ],
        }

        # Pre-flight rate-limit check BEFORE uploading images so we don't
        # burn Cloudinary uploads on requests that will be rejected anyway.
        try:
            PostService.check_daily_submission_limit(user)
        except AppException as exc:
            flash(exc.message, "error")
            return render_template("public/submit.html", form=form), exc.status_code

        # Upload any attached images first (up to 10).
        files = [f for f in request.files.getlist("images") if f and f.filename]
        images = []
        if files:
            try:
                images = MediaService.upload_many(files, user, max_count=10)
            except AppException as exc:
                flash(exc.message, "error")
                return render_template("public/submit.html", form=form), exc.status_code

        try:
            post = PostService.submit_public(form, user, images=images)
        except AppException as exc:
            # Roll back any uploaded media so we don't orphan assets.
            for m in images:
                try:
                    MediaService.delete(m)
                except Exception:
                    pass
            flash(exc.message, "error")
            return render_template("public/submit.html", form=form), exc.status_code

        flash("Thanks! Your submission is now pending review.", "success")
        return redirect(url_for("web.my_submissions"))

    return render_template("public/submit.html", form={})


# ---------- Users (admin only) ----------

@web_bp.route("/users")
@login_required
@roles_required(RoleName.ADMIN.value)
def users_list():
    users = list(User.objects.order_by("-created_at"))
    roles = list(Role.objects.order_by("name"))
    return render_template("users/list.html", users=users, roles=roles)


@web_bp.route("/users/new", methods=["POST"])
@login_required
@roles_required(RoleName.ADMIN.value)
def users_create():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    role_names = request.form.getlist("roles") or [RoleName.WRITER.value]

    if not name or not email or len(password) < 8:
        flash("Name, email, and an 8+ character password are required.", "error")
        return redirect(url_for("web.users_list"))

    if User.objects(email=email).first():
        flash("A user with that email already exists.", "error")
        return redirect(url_for("web.users_list"))

    user = User(name=name, email=email)
    user.set_password(password)
    for rn in role_names:
        role = Role.objects(name=rn).first()
        if role:
            user.roles.append(role)
    if not user.roles:
        flash("At least one valid role is required.", "error")
        return redirect(url_for("web.users_list"))

    user.save()
    flash("User created.", "success")
    return redirect(url_for("web.users_list"))


@web_bp.route("/users/<string:user_id>/toggle", methods=["POST"])
@login_required
@roles_required(RoleName.ADMIN.value)
def users_toggle(user_id: str):
    target = _get_or_404(User, user_id)
    current = _current_user()
    if str(target.id) == str(current.id):
        flash("You cannot disable your own account.", "error")
        return redirect(url_for("web.users_list"))
    target.is_active = not target.is_active
    target.save()
    flash(f"User {'enabled' if target.is_active else 'disabled'}.", "success")
    return redirect(url_for("web.users_list"))
