"""
Roles.

The old M2M association table (user_roles) is removed; users embed
their role references directly via a ListField(ReferenceField(Role)).
"""
from mongoengine import StringField

from .base import TimestampedDocument


class Role(TimestampedDocument):
    name = StringField(required=True, unique=True, max_length=50)
    description = StringField(max_length=255)

    meta = {
        "collection": "roles",
    }

    def to_dict(self) -> dict:
        return {"id": str(self.id), "name": self.name, "description": self.description}

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
