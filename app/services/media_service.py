"""
Media service: upload, list, delete.

Stores files on local disk by default; swap `_store_file` for S3/GCS
without touching the rest of the app.
"""
import os
import uuid
from pathlib import Path

from bson.errors import InvalidId
from flask import current_app
from mongoengine.errors import ValidationError as MEValidationError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..models.media import Media
from ..models.user import User
from ..utils.enums import MediaType
from ..utils.exceptions import BadRequest, NotFound


class MediaService:
    @staticmethod
    def upload(file: FileStorage, uploader: User, alt_text: str | None = None, caption: str | None = None) -> Media:
        if not file or not file.filename:
            raise BadRequest("No file provided")

        original = secure_filename(file.filename)
        ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
        allowed_image = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
        allowed_video = current_app.config["ALLOWED_VIDEO_EXTENSIONS"]

        if ext in allowed_image:
            media_type = MediaType.IMAGE.value
        elif ext in allowed_video:
            media_type = MediaType.VIDEO.value
        else:
            raise BadRequest(f"Unsupported file type: .{ext}")

        filename = f"{uuid.uuid4().hex}.{ext}"
        rel_path = MediaService._store_file(file, filename)

        media = Media(
            filename=filename,
            original_name=original,
            url=rel_path,
            mime_type=file.mimetype or "application/octet-stream",
            size_bytes=MediaService._file_size(file),
            media_type=media_type,
            alt_text=alt_text,
            caption=caption,
            uploaded_by=uploader,
        )
        media.save()
        return media

    @staticmethod
    def delete(media: Media) -> None:
        # Best-effort file cleanup; DB is the source of truth.
        try:
            upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
            (upload_dir / media.filename).unlink(missing_ok=True)
        except Exception as exc:
            current_app.logger.warning("Failed to delete file: %s", exc)
        media.delete()

    @staticmethod
    def get_or_404(media_id) -> Media:
        try:
            m = Media.objects(id=media_id).first()
        except (MEValidationError, InvalidId):
            m = None
        if not m:
            raise NotFound("Media not found")
        return m

    # ---- internals ----
    @staticmethod
    def _store_file(file: FileStorage, filename: str) -> str:
        upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / filename
        file.save(path)
        # Served through a static route; return a URL-ish path.
        return f"/uploads/{filename}"

    @staticmethod
    def _file_size(file: FileStorage) -> int:
        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(0)
        return size
