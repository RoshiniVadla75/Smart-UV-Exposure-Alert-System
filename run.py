import logging
import os

from app import create_app


def _load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_dev_app():
    flask_app = create_app()
    flask_app.config["TEMPLATES_AUTO_RELOAD"] = True
    flask_app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    flask_app.jinja_env.auto_reload = True
    return flask_app


_load_dotenv()
app = create_dev_app()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    port = int(os.getenv("PORT", "5000"))
    debug = _env_flag("FLASK_DEBUG", True)
    logging.info("Starting current Smart UV app at http://127.0.0.1:%s", port)
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=port,
        debug=debug,
        use_reloader=debug,
    )
