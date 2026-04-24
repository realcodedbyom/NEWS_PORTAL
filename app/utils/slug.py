"""
Slug generator. Ensures uniqueness by appending an incrementing suffix.
"""
from slugify import slugify


def generate_unique_slug(base: str, model, field: str = "slug") -> str:
    """Generate a unique slug for a MongoEngine Document class.

    `model` must expose `.objects(**{field: slug})` (i.e. a MongoEngine Document).
    """
    base_slug = slugify(base)[:200] or "post"
    slug = base_slug
    counter = 2
    while model.objects(**{field: slug}).first() is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug
