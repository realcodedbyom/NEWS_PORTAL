"""
Import all models here so MongoEngine registers them on app init.
"""
from .base import TimestampedDocument, TimestampMixin  # noqa: F401
from .role import Role  # noqa: F401
from .user import User  # noqa: F401
from .media import Media  # noqa: F401
from .tag import Tag  # noqa: F401
from .post import Post, PostVersion  # noqa: F401
from .notification import Notification  # noqa: F401
from .alumni import Alumni  # noqa: F401
from .analytics import PostView  # noqa: F401
