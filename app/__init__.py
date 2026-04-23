import os
import time
from flask import Flask
from flask import jsonify, request

from .db import init_db
from .demo import DemoEngine
from .db import get_db
from .routes import register_routes


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "uv_system.db"),
        INGEST_API_KEY=os.getenv("INGEST_API_KEY", ""),
        DEMO_INTERVAL_SECONDS=int(os.getenv("DEMO_INTERVAL_SECONDS", "5")),
        RATE_LIMIT_WINDOW_SECONDS=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
        RATE_LIMIT_MAX_REQUESTS=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120")),
    )

    if test_config:
        app.config.update(test_config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    init_db(app)
    app.extensions["rate_limit_state"] = {}
    app.extensions["demo_engine"] = DemoEngine(
        app, interval_seconds=app.config["DEMO_INTERVAL_SECONDS"]
    )
    register_routes(app)

    @app.before_request
    def _rate_limit_api():
        if not request.path.startswith("/api"):
            return None
        if request.path == "/api/health":
            return None

        now = time.time()
        key = request.remote_addr or "unknown"
        window = app.config["RATE_LIMIT_WINDOW_SECONDS"]
        max_requests = app.config["RATE_LIMIT_MAX_REQUESTS"]
        state = app.extensions["rate_limit_state"]
        bucket = state.setdefault(key, [])
        # Keep only active-window timestamps.
        state[key] = [ts for ts in bucket if now - ts <= window]
        if len(state[key]) >= max_requests:
            return jsonify({"error": "Rate limit exceeded. Please retry shortly."}), 429
        state[key].append(now)
        return None

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        return response

    @app.errorhandler(404)
    def _not_found(err):
        if request.path.startswith("/api"):
            return jsonify({"error": "Endpoint not found"}), 404
        return err

    @app.errorhandler(Exception)
    def _unhandled_error(err):
        app.logger.exception("Unhandled server error: %s", err)
        if request.path.startswith("/api"):
            return jsonify({"error": "Internal server error"}), 500
        return err

    with app.app_context():
        state = get_db().execute("SELECT mode FROM system_state WHERE id = 1").fetchone()
        if state and state["mode"] == "demo":
            app.extensions["demo_engine"].start()

    return app
