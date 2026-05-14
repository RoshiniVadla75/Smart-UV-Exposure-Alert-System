import logging
import os
import socket

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


def _local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _ssl_context_from_env():
    cert_file = os.getenv("SSL_CERT_FILE", "").strip()
    key_file = os.getenv("SSL_KEY_FILE", "").strip()
    if cert_file and key_file:
        return (cert_file, key_file)

    if _env_flag("FLASK_HTTPS", False):
        try:
            import cryptography  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "FLASK_HTTPS=true needs the cryptography package for Flask's "
                "temporary HTTPS certificate. Run `python -m pip install -r "
                "requirements.txt`, or set SSL_CERT_FILE and SSL_KEY_FILE."
            ) from exc
        return "adhoc"

    return None


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
    host = os.getenv("HOST", "0.0.0.0")
    ssl_context = _ssl_context_from_env()
    scheme = "https" if ssl_context else "http"
    logging.info("Starting Smart UV app at %s://127.0.0.1:%s", scheme, port)
    if host in {"0.0.0.0", "::"}:
        logging.info("LAN URL: %s://%s:%s", scheme, _local_ip(), port)
    if not ssl_context:
        logging.info(
            "Web Bluetooth works on http://localhost:%s. For 192.168.x.x LAN "
            "access, restart with FLASK_HTTPS=true or use Chrome's secure-origin "
            "development flag.",
            port,
        )
    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=debug,
        ssl_context=ssl_context,
    )
