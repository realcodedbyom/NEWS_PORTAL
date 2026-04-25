"""
Cloudinary URL helpers for responsive images.

Builds transformed URLs for Cloudinary-hosted Media. For non-Cloudinary
image URLs (e.g., seed data with external URLs), returns the original
URL unchanged so templates remain safe.
"""
from __future__ import annotations

from typing import Optional

import cloudinary.utils


# Preset width ladder for srcset generation. Keeps transformations small
# and cacheable at the CDN edge.
SRCSET_WIDTHS = (320, 480, 640, 800, 1024, 1280, 1600)


def _is_cloudinary_media(media) -> bool:
    return bool(
        media is not None
        and getattr(media, "provider", None) == "cloudinary"
        and getattr(media, "public_id", None)
    )


def cld_url(
    media,
    width: Optional[int] = None,
    height: Optional[int] = None,
    crop: str = "fill",
    gravity: str = "auto",
) -> str:
    """Build a Cloudinary delivery URL with sensible defaults.

    Falls back to the stored `url` for non-Cloudinary media.
    """
    if media is None:
        return ""
    if not _is_cloudinary_media(media):
        return getattr(media, "url", "") or ""
    opts = {
        "fetch_format": "auto",
        "quality": "auto",
        "secure": True,
    }
    if width:
        opts["width"] = width
    if height:
        opts["height"] = height
    if width and height:
        opts["crop"] = crop
        opts["gravity"] = gravity
    url, _ = cloudinary.utils.cloudinary_url(media.public_id, **opts)
    return url


def cld_srcset(
    media,
    widths: tuple[int, ...] = SRCSET_WIDTHS,
    ref_width: Optional[int] = None,
    ref_height: Optional[int] = None,
    crop: str = "fill",
    gravity: str = "auto",
) -> str:
    """Build a srcset string preserving aspect ratio across breakpoints.

    If `ref_width` and `ref_height` are provided, each srcset entry's
    height is scaled proportionally so the aspect ratio is stable.
    Returns empty string for non-Cloudinary media.
    """
    if not _is_cloudinary_media(media):
        return ""
    # Cap emitted widths at 2x the reference (enough for retina) to keep
    # srcset attributes compact — a 640px card never needs a 1600w variant.
    max_w = (ref_width * 2) if ref_width else max(widths)
    effective_widths = [w for w in widths if w <= max_w] or [widths[0]]
    parts = []
    for w in effective_widths:
        h = None
        if ref_width and ref_height and ref_width > 0:
            h = int(round(w * ref_height / ref_width))
        parts.append(
            f"{cld_url(media, width=w, height=h, crop=crop, gravity=gravity)} {w}w"
        )
    return ", ".join(parts)


def register_jinja_helpers(app) -> None:
    """Expose cld_url / cld_srcset + common 'sizes' presets to templates."""
    app.jinja_env.globals["cld_url"] = cld_url
    app.jinja_env.globals["cld_srcset"] = cld_srcset
    app.jinja_env.globals["CLD_SIZES_HERO"] = "(min-width: 1024px) 860px, 100vw"
    app.jinja_env.globals["CLD_SIZES_CARD"] = (
        "(min-width: 1024px) 320px, (min-width: 640px) 50vw, 100vw"
    )
