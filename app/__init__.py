"""AegisCloud application factory."""
import os
from datetime import timedelta

from flask import Flask, redirect, render_template, request, session as flask_session

from . import db
from .security import verify_token


def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.secret_key = os.environ.get("AEGIS_SECRET", "aegis-dev-secret-change-me-in-prod")
    app.permanent_session_lifetime = timedelta(hours=8)
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

    db.init_db()

    from . import api as api_module
    from . import views

    app.register_blueprint(api_module.api)
    app.register_blueprint(views.bp)

    @app.after_request
    def harden(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        # Embedded previews can be cross-origin. Keep clickjacking protection
        # by default; opt in to embedding only for a trusted demo.
        if os.environ.get("AEGIS_ALLOW_EMBED", "0") != "1":
            resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline';"
            " script-src 'self' 'unsafe-inline'; connect-src 'self'")
        return resp

    @app.context_processor
    def inject():
        user = None
        token = request.cookies.get("aegis_token") or request.args.get("token")
        payload = verify_token(token) if token else None
        if payload:
            row = db.query("SELECT username, role, email FROM users WHERE id=?",
                           (payload["uid"],), one=True)
            if row:
                user = {"username": row["username"], "role": row["role"], "email": row["email"]}
        return {"current_user": user}

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return {"success": False, "error": "not found"}, 404
        return render_template("error.html", code=404, message="Page not found"), 404

    @app.errorhandler(413)
    def too_large(e):
        return {"success": False, "error": "upload too large"}, 413

    @app.errorhandler(500)
    def server_error(e):                                   # pragma: no cover
        if request.path.startswith("/api/"):
            return {"success": False, "error": "internal error"}, 500
        return render_template("error.html", code=500, message="Internal error"), 500

    return app
