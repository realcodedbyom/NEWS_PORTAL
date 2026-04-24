"""
Media routes.
"""
from flask import Blueprint, send_from_directory, current_app

from ..controllers.media_controller import MediaController
from ..utils.decorators import roles_required
from ..utils.enums import RoleName

media_bp = Blueprint("media", __name__)


@media_bp.post("/upload")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def upload():
    return MediaController.upload()


@media_bp.get("")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def list_media():
    return MediaController.list()


@media_bp.get("/<string:media_id>")
@roles_required(RoleName.WRITER, RoleName.EDITOR, RoleName.ADMIN)
def get_media(media_id: str):
    return MediaController.get(media_id)


@media_bp.delete("/<string:media_id>")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def delete_media(media_id: str):
    return MediaController.delete(media_id)


# Local file serving — in production, serve via Nginx/S3 instead.
@media_bp.get("/file/<path:filename>")
def serve_file(filename: str):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
