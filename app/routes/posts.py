"""
Post routes.

Public endpoints (listings + slug detail) are unauthenticated.
Everything else requires auth + the right role.
"""
from flask import Blueprint

from ..controllers.post_controller import PostController
from ..utils.decorators import auth_required, roles_required
from ..utils.enums import RoleName

posts_bp = Blueprint("posts", __name__)


# ---------- Public ----------
@posts_bp.get("")
def list_public():
    return PostController.list_public()


@posts_bp.get("/slug/<slug>")
def get_public(slug: str):
    return PostController.get_public(slug)


# ---------- Admin listing ----------
@posts_bp.get("/admin")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def list_admin():
    return PostController.list_admin()


@posts_bp.get("/admin/<string:post_id>")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def get_admin(post_id: str):
    return PostController.get_admin(post_id)


# ---------- CRUD ----------
@posts_bp.post("")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def create():
    return PostController.create()


@posts_bp.patch("/<string:post_id>")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def update(post_id: str):
    return PostController.update(post_id)


@posts_bp.delete("/<string:post_id>")
@auth_required
def delete(post_id: str):
    return PostController.delete(post_id)


# ---------- Workflow ----------
@posts_bp.post("/<string:post_id>/submit")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def submit_for_review(post_id: str):
    return PostController.submit_for_review(post_id)


@posts_bp.post("/<string:post_id>/approve")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def approve(post_id: str):
    return PostController.approve(post_id)


@posts_bp.post("/<string:post_id>/reject")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def reject(post_id: str):
    return PostController.reject(post_id)


@posts_bp.post("/<string:post_id>/ready")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def mark_ready(post_id: str):
    return PostController.mark_ready(post_id)


@posts_bp.post("/<string:post_id>/publish")
@roles_required(RoleName.ADMIN)
def publish(post_id: str):
    return PostController.publish(post_id)


@posts_bp.post("/<string:post_id>/transition")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def transition(post_id: str):
    return PostController.transition(post_id)


# ---------- Versions ----------
@posts_bp.get("/<string:post_id>/versions")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def versions(post_id: str):
    return PostController.list_versions(post_id)


# ---------- My submissions ----------
@posts_bp.get("/mine")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def list_mine():
    return PostController.list_mine()


# ---------- Moderation queues ----------
@posts_bp.get("/queue/public")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def list_public_queue():
    return PostController.list_public_queue()


@posts_bp.get("/queue/review")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def list_review_queue():
    return PostController.list_review_queue()


# ---------- Moderation notes ----------
@posts_bp.post("/<string:post_id>/notes")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def add_moderation_note(post_id: str):
    return PostController.add_moderation_note(post_id)
