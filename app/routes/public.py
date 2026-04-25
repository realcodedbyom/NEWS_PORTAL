"""
Public-facing API for news submissions.

All routes here require auth (any registered user is implicitly a writer).
Rate limiting happens inside PostService.submit_public.
"""
from flask import Blueprint

from ..controllers.post_controller import PostController
from ..utils.decorators import auth_required

public_bp = Blueprint("public", __name__)


@public_bp.post("/submit")
@auth_required
def submit():
    return PostController.submit_public()
