"""
StockFind Pro — Flask application entrypoint.

Serves the JSON API under /api/* and the static dashboard frontend at /.
Run with:  python -m app.main
(First run: python -m app.seed   to generate the simulated database.)
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from .api.auth import auth
from .api.routes import api
from .db.database import DB_PATH, init_db

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    # Render terminates TLS in front of the app; without this, request.is_secure
    # is always False, which would break the session cookie's Secure flag.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RENDER"))

    app.register_blueprint(api)
    app.register_blueprint(auth)

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.errorhandler(404)
    def not_found(e):
        # SPA-style fallback for any non-API route
        from flask import request
        if request.path.startswith("/api"):
            return {"error": "not found"}, 404
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


if not DB_PATH.exists():
    init_db(reset=True)

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
