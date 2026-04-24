"""
Alumni routes. Listings are public; writes require editor/admin.
"""
from flask import Blueprint

from ..controllers.alumni_controller import AlumniController
from ..utils.decorators import roles_required
from ..utils.enums import RoleName

alumni_bp = Blueprint("alumni", __name__)


@alumni_bp.get("")
def list_alumni():
    return AlumniController.list()


@alumni_bp.get("/<string:alumni_id>")
def get_alumni(alumni_id: str):
    return AlumniController.get(alumni_id)


@alumni_bp.post("")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def create_alumni():
    return AlumniController.create()


@alumni_bp.patch("/<string:alumni_id>")
@roles_required(RoleName.EDITOR, RoleName.ADMIN)
def update_alumni(alumni_id: str):
    return AlumniController.update(alumni_id)


@alumni_bp.delete("/<string:alumni_id>")
@roles_required(RoleName.ADMIN)
def delete_alumni(alumni_id: str):
    return AlumniController.delete(alumni_id)
