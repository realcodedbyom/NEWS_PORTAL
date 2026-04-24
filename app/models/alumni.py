"""
Alumni directory. Structured fields + JSON-like fields for flexible bits.
"""
from mongoengine import (
    StringField,
    IntField,
    BooleanField,
    ListField,
    DictField,
    ReferenceField,
)

from .base import TimestampedDocument


class Alumni(TimestampedDocument):
    name = StringField(required=True, max_length=150)
    email = StringField(max_length=150)

    graduation_year = IntField(required=True)
    course = StringField(required=True, max_length=150)

    current_role = StringField(max_length=150)
    company = StringField(max_length=150)
    location = StringField(max_length=150)

    bio = StringField()
    achievements = ListField(StringField())
    social_links = DictField()

    photo = ReferenceField("Media")

    is_featured = BooleanField(default=False, required=True)
    is_verified = BooleanField(default=False, required=True)

    meta = {
        "collection": "alumni",
        "indexes": [
            "name",
            "email",
            "graduation_year",
            "course",
            "company",
            "location",
            "is_featured",
            ("graduation_year", "course"),
        ],
    }

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "graduation_year": self.graduation_year,
            "course": self.course,
            "current_role": self.current_role,
            "company": self.company,
            "location": self.location,
            "bio": self.bio,
            "achievements": list(self.achievements or []),
            "social_links": dict(self.social_links or {}),
            "photo": self.photo.to_dict() if self.photo else None,
            "is_featured": bool(self.is_featured),
            "is_verified": bool(self.is_verified),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
