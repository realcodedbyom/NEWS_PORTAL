"""
Tags. Unique by slug.

The old post_tags association table is removed; posts keep tag
references directly in a ListField(ReferenceField(Tag)).
"""
from mongoengine import StringField
from slugify import slugify

from .base import TimestampedDocument


class Tag(TimestampedDocument):
    name = StringField(required=True, unique=True, max_length=80)
    slug = StringField(required=True, unique=True, max_length=100)

    meta = {
        "collection": "tags",
    }

    @classmethod
    def get_or_create(cls, name: str) -> "Tag":
        name = (name or "").strip()
        s = slugify(name)
        tag = cls.objects(slug=s).first()
        if tag:
            return tag
        tag = cls(name=name, slug=s)
        tag.save()
        return tag

    def to_dict(self) -> dict:
        return {"id": str(self.id), "name": self.name, "slug": self.slug}
