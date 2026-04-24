"""
Application factory.

Exposes `create_app(config_name)` which wires extensions, blueprints,
error handlers, and the background scheduler.
"""
from __future__ import annotations

import logging
import os

from flask import Flask
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException

from .config import get_config
from .extensions import jwt, cors, csrf, scheduler, revoked_tokens, init_db


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    _configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_jwt_callbacks(jwt)
    _start_scheduler(app)

    # Ensure upload folder exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    return app


def _configure_logging(app: Flask) -> None:
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _init_extensions(app: Flask) -> None:
    # Connect MongoDB first so models register against a live connection.
    init_db(app)

    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )
    csrf.init_app(app)
    # CSRF guards HTML forms only. JSON API blueprints are exempted below.

    # Import models so MongoEngine registers all collections.
    with app.app_context():
        from . import models  # noqa: F401


def _register_blueprints(app: Flask) -> None:
    from .routes.auth import auth_bp
    from .routes.posts import posts_bp
    from .routes.alumni import alumni_bp
    from .routes.media import media_bp
    from .routes.users import users_bp
    from .routes.analytics import analytics_bp
    from .routes.health import health_bp
    from .routes.web import web_bp

    # JSON API blueprints (JWT-protected, CSRF-exempt)
    for bp, prefix in [
        (health_bp, "/api"),
        (auth_bp, "/api/auth"),
        (posts_bp, "/api/posts"),
        (alumni_bp, "/api/alumni"),
        (media_bp, "/api/media"),
        (users_bp, "/api/users"),
        (analytics_bp, "/api/analytics"),
    ]:
        csrf.exempt(bp)
        app.register_blueprint(bp, url_prefix=prefix)

    # Server-rendered HTML admin UI (session-based, CSRF-protected forms)
    app.register_blueprint(web_bp)


def _register_error_handlers(app: Flask) -> None:
    from flask import request, render_template
    from .utils.responses import error_response
    from .utils.exceptions import AppException

    def _wants_json() -> bool:
        return request.path.startswith("/api/") or request.is_json

    @app.errorhandler(AppException)
    def handle_app_exception(exc: AppException):
        if _wants_json():
            return error_response(exc.message, exc.status_code, details=exc.details)
        return render_template("errors/error.html", code=exc.status_code, message=exc.message), exc.status_code

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):
        if _wants_json():
            return error_response(exc.description or exc.name, exc.code or 500)
        return render_template("errors/error.html", code=exc.code or 500, message=exc.description or exc.name), exc.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        app.logger.exception("Unhandled exception: %s", exc)
        message = str(exc) if app.config.get("DEBUG") else "Internal server error"
        if _wants_json():
            return error_response(message, 500)
        return render_template("errors/error.html", code=500, message=message), 500


def _register_jwt_callbacks(jwt_mgr: JWTManager) -> None:
    from .utils.responses import error_response

    @jwt_mgr.token_in_blocklist_loader
    def _check_if_token_revoked(_jwt_header, jwt_payload):
        return jwt_payload.get("jti") in revoked_tokens

    @jwt_mgr.unauthorized_loader
    def _missing_token(reason):
        return error_response(f"Missing authorization: {reason}", 401)

    @jwt_mgr.invalid_token_loader
    def _invalid_token(reason):
        return error_response(f"Invalid token: {reason}", 401)

    @jwt_mgr.expired_token_loader
    def _expired_token(_jwt_header, _jwt_payload):
        return error_response("Token has expired", 401)

    @jwt_mgr.revoked_token_loader
    def _revoked_token(_jwt_header, _jwt_payload):
        return error_response("Token has been revoked", 401)


def _start_scheduler(app: Flask) -> None:
    """Start APScheduler for post scheduling/expiry jobs."""
    if not app.config.get("SCHEDULER_ENABLED"):
        return
    if scheduler.running:
        return

    from .services.scheduler_service import run_scheduled_jobs

    interval = app.config.get("SCHEDULER_INTERVAL_SECONDS", 60)

    def _job():
        # Scheduler runs outside request context; push one manually.
        with app.app_context():
            run_scheduled_jobs()

    scheduler.add_job(
        _job,
        "interval",
        seconds=interval,
        id="news_scheduler",
        replace_existing=True,
    )
    scheduler.start()
    app.logger.info("Scheduler started (interval=%ss)", interval)
