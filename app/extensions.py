"""
Centralized Flask extension instances.

Keep them here to avoid circular imports. Bind them to the app
inside the application factory.

MongoDB connection is established via `init_db(app)` using
MongoEngine directly (we skip Flask-MongoEngine for compatibility
with newer Flask releases).
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
