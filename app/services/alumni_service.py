"""
Alumni service: CRUD + search/filter.
"""
from bson.errors import InvalidId
from mongoengine import Q
from mongoengine.errors import ValidationError as MEValidationError

from ..models.alumni import Alumni
from ..models.media import Media
from ..utils.exceptions import NotFound


def _resolve_photo(data: dict) -> dict:
    """Translate a `photo_id` string in the payload into a `photo` Media ref."""
    if "photo_id" in data:
        photo_id = data.pop("photo_id")
        photo = None
        if photo_id:
            try:
                photo = Media.objects(id=photo_id).first()
            except (MEValidationError, InvalidId):
                photo = None
        data["photo"] = photo
    return data


class AlumniService:
    @staticmethod
    def create(data: dict) -> Alumni:
        data = _resolve_photo(dict(data))
        alumni = Alumni(**data)
        alumni.save()
        return alumni

    @staticmethod
    def update(alumni: Alumni, data: dict) -> Alumni:
        data = _resolve_photo(dict(data))
        for key, value in data.items():
            setattr(alumni, key, value)
        alumni.save()
        return alumni

    @staticmethod
    def delete(alumni: Alumni) -> None:
        alumni.delete()

    @staticmethod
    def get_or_404(alumni_id) -> Alumni:
        try:
            a = Alumni.objects(id=alumni_id).first()
        except (MEValidationError, InvalidId):
            a = None
        if not a:
            raise NotFound("Alumni not found")
        return a

    @staticmethod
    def build_list_query(
        *,
        search: str | None = None,
        year: int | None = None,
        course: str | None = None,
        company: str | None = None,
        location: str | None = None,
        featured: bool | None = None,
    ):
        q = Alumni.objects

        if search:
            q = q.filter(
                Q(name__icontains=search)
                | Q(company__icontains=search)
                | Q(current_role__icontains=search)
                | Q(location__icontains=search)
            )
        if year:
            q = q.filter(graduation_year=year)
        if course:
            q = q.filter(course__icontains=course)
        if company:
            q = q.filter(company__icontains=company)
        if location:
            q = q.filter(location__icontains=location)
        if featured is not None:
            q = q.filter(is_featured=featured)

        return q.order_by("-is_featured", "-graduation_year", "name")
