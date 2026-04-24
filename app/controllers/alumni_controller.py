"""
Alumni HTTP controllers.
"""
from flask import request

from ..services.alumni_service import AlumniService
from ..utils.pagination import get_page_params, paginate_query
from ..utils.responses import success_response, paginated_response
from ..utils.validators import load_or_raise, AlumniCreateSchema, AlumniUpdateSchema


class AlumniController:
    @staticmethod
    def list():
        params = get_page_params()
        featured = request.args.get("featured")
        q = AlumniService.build_list_query(
            search=request.args.get("q"),
            year=request.args.get("year", type=int),
            course=request.args.get("course"),
            company=request.args.get("company"),
            location=request.args.get("location"),
            featured=(featured.lower() in ("1", "true", "yes")) if featured else None,
        )
        items, total = paginate_query(q, params)
        return paginated_response(
            [a.to_dict() for a in items], params.page, params.per_page, total
        )

    @staticmethod
    def get(alumni_id):
        alumni = AlumniService.get_or_404(alumni_id)
        return success_response(alumni.to_dict())

    @staticmethod
    def create():
        data = load_or_raise(AlumniCreateSchema(), request.get_json(silent=True))
        alumni = AlumniService.create(data)
        return success_response(alumni.to_dict(), message="Alumni created", status=201)

    @staticmethod
    def update(alumni_id):
        data = load_or_raise(AlumniUpdateSchema(partial=True), request.get_json(silent=True))
        alumni = AlumniService.get_or_404(alumni_id)
        alumni = AlumniService.update(alumni, data)
        return success_response(alumni.to_dict(), message="Alumni updated")

    @staticmethod
    def delete(alumni_id):
        alumni = AlumniService.get_or_404(alumni_id)
        AlumniService.delete(alumni)
        return success_response(message="Alumni deleted")
