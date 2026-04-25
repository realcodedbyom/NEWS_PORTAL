"""
User document with password hashing and role references.
"""
import bcrypt
from mongoengine import (
    StringField,
    BooleanField,
    DateTimeField,
    IntField,
    ListField,
    ReferenceField,
)

from .base import TimestampedDocument
from .role import Role


class User(TimestampedDocument):
    name = StringField(required=True, max_length=120)
    email = StringField(required=True, unique=True, max_length=150)
    password_hash = StringField(required=True, max_length=255)
    is_active = BooleanField(default=True, required=True)
    avatar_url = StringField(max_length=500)
    last_login_at = DateTimeField()

    # Counter of posts this user has submitted (public or internal);
    # used for lightweight anti-spam rate limiting.
    submission_count = IntField(default=0, required=True)

    roles = ListField(ReferenceField(Role))

    meta = {
        "collection": "users",
        "indexes": [
            "-created_at",
        ],
    }

    # ---- password helpers ----

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def verify_password(self, password: str) -> bool:
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                (self.password_hash or "").encode("utf-8"),
            )
        except (ValueError, AttributeError, TypeError):
            return False

    # ---- role helpers ----

    def has_role(self, role_name: str) -> bool:
        return any(r and r.name == role_name for r in (self.roles or []))

    def has_any_role(self, *role_names: str) -> bool:
        names = {r.name for r in (self.roles or []) if r}
        return any(n in names for n in role_names)

    def role_names(self) -> list[str]:
        return [r.name for r in (self.roles or []) if r]

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "is_active": self.is_active,
            "avatar_url": self.avatar_url,
            "roles": self.role_names(),
            "submission_count": int(self.submission_count or 0),
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<User {self.email}>"
