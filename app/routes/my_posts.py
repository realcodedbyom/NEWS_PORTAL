"""
Convenience alias for /api/my-posts so it matches the public API spec.
Internally delegates to the same controller as /api/posts/mine.
"""
from flask import Blueprint

from ..controllers.post_controller import PostController
from ..utils.decorators import auth_required

my_posts_bp = Blueprint("my_posts", __name__)


@my_posts_bp.get("")
@auth_required
def list_mine():
    return PostController.list_mine()
