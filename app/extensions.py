"""
Centralized Flask extension instances.

Keep them here to avoid circular imports. Bind them to the app
inside the application factory.

MongoDB connection is established via `init_db(app)` using
MongoEngine directly (we skip Flask-MongoEngine for compatibility
with newer Flask releases).

Cloudinary is initialized via `init_cloudinary(app)` and is
required — the app will refuse to start without credentials.
"""
import mongoengine
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from apscheduler.schedulers.background import BackgroundScheduler

jwt = JWTManager()
cors = CORS()
csrf = CSRFProtect()
scheduler = BackgroundScheduler(timezone="UTC")

# In-memory revoked-token store. Swap for Redis in production.
revoked_tokens: set[str] = set()


def init_db(app) -> None:
    """Connect to MongoDB using MongoEngine.

    Disconnects any existing default connection first so the factory
    can be called multiple times (tests, reloaders).
    """
    try:
        mongoengine.disconnect(alias="default")
    except Exception:
        pass

    mongoengine.connect(
        db=app.config.get("MONGODB_DB", "dsvv_news"),
        host=app.config.get("MONGODB_HOST"),
        alias="default",
        uuidRepresentation="standard",
    )


def init_cloudinary(app) -> None:
    """Configure the Cloudinary SDK from Flask config.

    Fail-fast: raises RuntimeError if the three required credentials
    (cloud name, API key, API secret) are missing. Cloudinary is the
    sole storage backend for media in this app.
    """
    name = app.config.get("CLOUDINARY_CLOUD_NAME")
    key = app.config.get("CLOUDINARY_API_KEY")
    secret = app.config.get("CLOUDINARY_API_SECRET")
    if not (name and key and secret):
        raise RuntimeError(
            "Cloudinary is required. Set CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET in your .env."
        )
    import cloudinary
    cloudinary.config(
        cloud_name=name,
        api_key=key,
        api_secret=secret,
        secure=True,
    )
    app.logger.info("Cloudinary configured for cloud '%s' (secure HTTPS)", name)
