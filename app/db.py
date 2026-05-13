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


def _ensure_column(db, table, column, definition):
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_schema():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lux REAL NOT NULL,
            light_level TEXT NOT NULL,
            threshold_status TEXT,
            buzzer_state TEXT,
            oled_message TEXT,
            wifi_signal INTEGER,
            source TEXT NOT NULL,
            location_label TEXT,
            latitude REAL,
            longitude REAL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lux REAL NOT NULL,
            light_level TEXT NOT NULL,
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

    _ensure_column(db, "readings", "threshold_status", "TEXT")
    _ensure_column(db, "readings", "buzzer_state", "TEXT")
    _ensure_column(db, "readings", "oled_message", "TEXT")
    _ensure_column(db, "readings", "location_label", "TEXT")
    _ensure_column(db, "readings", "latitude", "REAL")
    _ensure_column(db, "readings", "longitude", "REAL")

    state = db.execute("SELECT id FROM system_state WHERE id = 1").fetchone()
    if not state:
        db.execute(
            """
            INSERT INTO system_state (id, device_id, last_seen, latest_wifi_signal, mode)
            VALUES (1, 'light-sensor-01', NULL, NULL, 'hardware')
            """
        )
    db.commit()


def init_db(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_schema()
