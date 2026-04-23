import sqlite3
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_schema():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            uv_index REAL NOT NULL,
            risk_level TEXT NOT NULL,
            wifi_signal INTEGER,
            source TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            uv_index REAL NOT NULL,
            risk_level TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            device_id TEXT,
            last_seen TEXT,
            latest_wifi_signal INTEGER,
            mode TEXT NOT NULL DEFAULT 'hardware'
        );
        """
    )

    state = db.execute("SELECT id FROM system_state WHERE id = 1").fetchone()
    if not state:
        db.execute(
            """
            INSERT INTO system_state (id, device_id, last_seen, latest_wifi_signal, mode)
            VALUES (1, 'uv-station-01', NULL, NULL, 'hardware')
            """
        )
    db.commit()


def init_db(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_schema()
