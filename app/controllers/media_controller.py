"""
Media HTTP controllers.
"""
from flask import request, g

from ..models.media import Media
from ..services.media_service import MediaService
from ..utils.pagination import get_page_params, paginate_query
from ..utils.responses import success_response, paginated_response


class MediaController:
    @staticmethod
    def upload():
        file = request.files.get("file")
        alt_text = request.form.get("alt_text")
        caption = request.form.get("caption")
        media = MediaService.upload(file, g.current_user, alt_text=alt_text, caption=caption)
        return success_response(media.to_dict(), message="Uploaded", status=201)

    @staticmethod
    def list():
        params = get_page_params()
        q = Media.objects.order_by("-created_at")
        media_type = request.args.get("type")
        if media_type:
            q = q.filter(media_type=media_type)
        items, total = paginate_query(q, params)
        return paginated_response(
            [m.to_dict() for m in items], params.page, params.per_page, total
        )

    @staticmethod
    def get(media_id):
        m = MediaService.get_or_404(media_id)
        return success_response(m.to_dict())

    @staticmethod
    def delete(media_id):
        m = MediaService.get_or_404(media_id)
        MediaService.delete(m)
        return success_response(message="Media deleted")
