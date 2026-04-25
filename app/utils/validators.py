"""
Marshmallow schemas for validating & normalizing request payloads.

Keep validation out of controllers. Raise ValidationError with a clean
details dict so the frontend gets field-level errors.
"""
from marshmallow import Schema, fields, validate, ValidationError as MMValidationError

from .enums import PostCategory, PostStatus
from .exceptions import ValidationError


def load_or_raise(schema: Schema, payload: dict | None) -> dict:
    try:
        return schema.load(payload or {})
    except MMValidationError as err:
        raise ValidationError("Validation failed", details=err.messages)


# ---------- Auth ----------

class RegisterSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=2, max=120))
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=8, max=128))
    role = fields.String(validate=validate.OneOf(["writer", "editor", "admin"]))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)


# ---------- Posts ----------

class PostCreateSchema(Schema):
    title = fields.String(required=True, validate=validate.Length(min=3, max=255))
    subtitle = fields.String(allow_none=True, validate=validate.Length(max=255))
    slug = fields.String(allow_none=True, validate=validate.Length(max=255))
    content = fields.String(required=True)
    excerpt = fields.String(allow_none=True, validate=validate.Length(max=500))
    category = fields.String(
        required=True,
        validate=validate.OneOf([c.value for c in PostCategory]),
    )
    tags = fields.List(fields.String(), load_default=list)
    featured_image_id = fields.String(allow_none=True)
    gallery_ids = fields.List(fields.String(), load_default=list)
    is_featured = fields.Boolean(load_default=False)
    is_announcement = fields.Boolean(load_default=False)
    is_pinned = fields.Boolean(load_default=False)
    publish_at = fields.DateTime(allow_none=True)
    expires_at = fields.DateTime(allow_none=True)


class PostUpdateSchema(PostCreateSchema):
    title = fields.String(validate=validate.Length(min=3, max=255))
    content = fields.String()
    category = fields.String(validate=validate.OneOf([c.value for c in PostCategory]))


class PostTransitionSchema(Schema):
    status = fields.String(
        required=True,
        validate=validate.OneOf([s.value for s in PostStatus]),
    )
    note = fields.String(allow_none=True, validate=validate.Length(max=500))


# ---------- Alumni ----------

class AlumniCreateSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=2, max=150))
    graduation_year = fields.Integer(required=True, validate=validate.Range(min=1950, max=2100))
    course = fields.String(required=True, validate=validate.Length(max=150))
    current_role = fields.String(allow_none=True, validate=validate.Length(max=150))
    company = fields.String(allow_none=True, validate=validate.Length(max=150))
    location = fields.String(allow_none=True, validate=validate.Length(max=150))
    bio = fields.String(allow_none=True)
    achievements = fields.List(fields.String(), load_default=list)
    social_links = fields.Dict(keys=fields.String(), values=fields.String(), load_default=dict)
    email = fields.Email(allow_none=True)
    photo_id = fields.String(allow_none=True)
    is_featured = fields.Boolean(load_default=False)


class AlumniUpdateSchema(AlumniCreateSchema):
    name = fields.String(validate=validate.Length(min=2, max=150))
    graduation_year = fields.Integer(validate=validate.Range(min=1950, max=2100))
    course = fields.String(validate=validate.Length(max=150))


# ---------- Public submission ----------

class PublicSubmissionSchema(Schema):
    """Used when the multipart form for /api/public/submit is parsed.

    Images are handled separately in the controller (request.files); the
    schema only covers the text fields.
    """
    title = fields.String(required=True, validate=validate.Length(min=3, max=255))
    content = fields.String(required=True, validate=validate.Length(min=20))
    subtitle = fields.String(allow_none=True, validate=validate.Length(max=255))
    excerpt = fields.String(allow_none=True, validate=validate.Length(max=500))
    category = fields.String(
        load_default=PostCategory.NEWS.value,
        validate=validate.OneOf([c.value for c in PostCategory]),
    )
    tags = fields.List(fields.String(), load_default=list)


class ModerationNoteSchema(Schema):
    note = fields.String(required=True, validate=validate.Length(min=1, max=1000))
