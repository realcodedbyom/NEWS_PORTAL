"""
Media service: upload to and delete from Cloudinary.

Cloudinary is the sole storage backend. The Media document stores
metadata (URL, public_id, dimensions, mime type) so assets can be
reused across posts and cleaned up from Cloudinary on delete.
"""
from bson.errors import InvalidId
from flask import current_app
from mongoengine.errors import ValidationError as MEValidationError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

import cloudinary.uploader

from ..models.media import Media
from ..models.user import User
from ..utils.enums import MediaType
from ..utils.exceptions import AppException, BadRequest, NotFound


class MediaService:
    @staticmethod
    def upload(
        file: FileStorage,
        uploader: User,
        alt_text: str | None = None,
        caption: str | None = None,
    ) -> Media:
        if not file or not file.filename:
            raise BadRequest("No file provided")

        original = secure_filename(file.filename)
        ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
        allowed_image = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
        allowed_video = current_app.config["ALLOWED_VIDEO_EXTENSIONS"]

        if ext in allowed_image:
            media_type = MediaType.IMAGE.value
            resource_type = "image"
        elif ext in allowed_video:
            media_type = MediaType.VIDEO.value
            resource_type = "video"
        else:
            raise BadRequest(f"Unsupported file type: .{ext}")

        folder = current_app.config.get("CLOUDINARY_UPLOAD_FOLDER", "dsvv_news")

        try:
            result = cloudinary.uploader.upload(
                file,
                folder=folder,
                resource_type=resource_type,
                use_filename=True,
                unique_filename=True,
                overwrite=False,
            )
        except Exception:
            current_app.logger.exception("Cloudinary upload failed")
            raise AppException("Upload failed. Please try again.", status_code=502)

        public_id = result.get("public_id")
        secure_url = result.get("secure_url") or result.get("url")
        fmt = result.get("format") or ext
        size_bytes = int(result.get("bytes") or 0)
        width = result.get("width")
        height = result.get("height")
        returned_rt = result.get("resource_type") or resource_type

        if public_id:
            base = public_id.split('/')[-1]
            filename = f"{base}.{fmt}" if fmt else base
        else:
            filename = original

        media = Media(
            filename=filename,
            original_name=original,
            url=secure_url,
            mime_type=file.mimetype or f"{returned_rt}/{fmt or 'octet-stream'}",
            size_bytes=size_bytes,
            media_type=media_type,
            width=width,
            height=height,
            alt_text=alt_text,
            caption=caption,
            provider="cloudinary",
            public_id=public_id,
            folder=folder,
            uploaded_by=uploader,
        )
        media.save()
        return media

    @staticmethod
    def upload_many(
        files: list[FileStorage],
        uploader: User,
        *,
        max_count: int = 10,
    ) -> list[Media]:
        """Upload multiple files to Cloudinary in one request.

        Enforces `max_count` and rolls back any successful uploads if a
        subsequent upload fails so we don't leave orphaned Cloudinary
        assets or Media rows.
        """
        # Strip out empty slots (a multipart form with no file picker often
        # sends a single blank FileStorage).
        candidates = [f for f in (files or []) if f and f.filename]
        if not candidates:
            return []
        if len(candidates) > max_count:
            raise BadRequest(f"Too many files (max {max_count})")

        uploaded: list[Media] = []
        try:
            for f in candidates:
                uploaded.append(MediaService.upload(f, uploader))
        except Exception:
            # Best-effort rollback: remove anything already persisted.
            for m in uploaded:
                try:
                    MediaService.delete(m)
                except Exception:
                    current_app.logger.warning(
                        "Rollback failed for media %s", getattr(m, "id", None)
                    )
            raise
        return uploaded

    @staticmethod
    def delete(media: Media) -> None:
        # Best-effort Cloudinary cleanup; DB is the source of truth.
        if media.provider == "cloudinary" and media.public_id:
            resource_type = (
                "video" if media.media_type == MediaType.VIDEO.value else "image"
            )
            try:
                cloudinary.uploader.destroy(
                    media.public_id,
                    resource_type=resource_type,
                    invalidate=True,
                )
            except Exception as exc:
                current_app.logger.warning(
                    "Cloudinary destroy failed for %s: %s", media.public_id, exc
                )
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
