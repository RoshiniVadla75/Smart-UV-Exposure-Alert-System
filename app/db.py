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


def _table_exists(db, table):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _ensure_column(db, table, column, definition):
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_legacy_readings(db):
    if not _table_exists(db, "readings"):
        return

    db.execute(
        """
        INSERT INTO light_readings (
            timestamp,
            device_id,
            lux,
            status,
            buzzer,
            source,
            oled_message,
            led_color,
            location_label,
            latitude,
            longitude
        )
        SELECT
            timestamp,
            device_id,
            lux,
            COALESCE(light_level, 'Acceptable Street Lighting'),
            COALESCE(buzzer_state, 'OFF'),
            COALESCE(source, 'legacy'),
            oled_message,
            CASE
                WHEN light_level IN ('Too Dark', 'Very Bright') THEN 'red'
                WHEN light_level = 'Dim' THEN 'yellow'
                ELSE 'green'
            END,
            location_label,
            latitude,
            longitude
        FROM readings legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM light_readings modern
            WHERE modern.timestamp = legacy.timestamp
              AND modern.device_id = legacy.device_id
              AND modern.lux = legacy.lux
        )
        """
    )


def _migrate_legacy_alerts(db):
    if not _table_exists(db, "alerts"):
        return

    alert_columns = {row["name"] for row in db.execute("PRAGMA table_info(alerts)")}
    required_columns = {"timestamp", "lux", "message"}
    if not required_columns.issubset(alert_columns):
        return

    if {"alert_type", "device_id"}.issubset(alert_columns):
        return

    rows = db.execute(
        """
        SELECT timestamp, COALESCE(device_id, 'light-sensor-01') AS device_id,
               lux, COALESCE(light_level, 'legacy_alert') AS light_level, message
        FROM alerts
        """
    ).fetchall()
    db.execute("ALTER TABLE alerts RENAME TO alerts_legacy")
    db.executescript(
        """
        CREATE TABLE alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lux REAL NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp DESC);
        """
    )
    for row in rows:
        db.execute(
            """
            INSERT INTO alerts (timestamp, device_id, lux, alert_type, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["timestamp"],
                row["device_id"],
                row["lux"],
                str(row["light_level"]).lower().replace(" ", "_"),
                row["message"],
            ),
        )


def init_schema():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS light_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lux REAL NOT NULL,
            status TEXT NOT NULL,
            buzzer TEXT NOT NULL,
            source TEXT NOT NULL,
            oled_message TEXT,
            led_color TEXT,
            sudden_drop INTEGER NOT NULL DEFAULT 0,
            ble_status TEXT,
            signal_active INTEGER NOT NULL DEFAULT 0,
            location_label TEXT,
            latitude REAL,
            longitude REAL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lux REAL NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS device_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            device_id TEXT,
            last_seen TEXT,
            ble_status TEXT NOT NULL DEFAULT 'disconnected',
            signal_active INTEGER NOT NULL DEFAULT 0,
            sensor_status TEXT NOT NULL DEFAULT 'inactive',
            oled_status TEXT NOT NULL DEFAULT 'inactive',
            buzzer_status TEXT NOT NULL DEFAULT 'OFF',
            esp32_uptime_seconds INTEGER,
            last_packet TEXT
        );

        CREATE TABLE IF NOT EXISTS system_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            mode TEXT NOT NULL DEFAULT 'hardware',
            simulation_label TEXT NOT NULL DEFAULT 'Built-in light cycle'
        );

        CREATE INDEX IF NOT EXISTS idx_light_readings_timestamp
            ON light_readings(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_light_readings_device
            ON light_readings(device_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
            ON alerts(timestamp DESC);
        """
    )

    _ensure_column(db, "light_readings", "oled_message", "TEXT")
    _ensure_column(db, "light_readings", "led_color", "TEXT")
    _ensure_column(db, "light_readings", "sudden_drop", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "light_readings", "ble_status", "TEXT")
    _ensure_column(db, "light_readings", "signal_active", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "light_readings", "location_label", "TEXT")
    _ensure_column(db, "light_readings", "latitude", "REAL")
    _ensure_column(db, "light_readings", "longitude", "REAL")
    _ensure_column(db, "device_status", "signal_active", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "device_status", "sensor_status", "TEXT NOT NULL DEFAULT 'inactive'")
    _ensure_column(db, "device_status", "oled_status", "TEXT NOT NULL DEFAULT 'inactive'")
    _ensure_column(db, "device_status", "buzzer_status", "TEXT NOT NULL DEFAULT 'OFF'")
    _ensure_column(db, "device_status", "esp32_uptime_seconds", "INTEGER")
    _ensure_column(db, "device_status", "last_packet", "TEXT")
    _ensure_column(db, "system_state", "simulation_label", "TEXT NOT NULL DEFAULT 'Built-in light cycle'")

    _migrate_legacy_alerts(db)
    _migrate_legacy_readings(db)

    device_state = db.execute("SELECT id FROM device_status WHERE id = 1").fetchone()
    if not device_state:
        db.execute(
            """
            INSERT INTO device_status (
                id,
                device_id,
                last_seen,
                ble_status,
                signal_active,
                sensor_status,
                oled_status,
                buzzer_status,
                esp32_uptime_seconds,
                last_packet
            )
            VALUES (1, 'ambient-light-esp32', NULL, 'disconnected', 0, 'inactive', 'inactive', 'OFF', NULL, NULL)
            """
        )

    system_state = db.execute("SELECT id FROM system_state WHERE id = 1").fetchone()
    if not system_state:
        db.execute(
            """
            INSERT INTO system_state (id, mode, simulation_label)
            VALUES (1, 'hardware', 'Built-in light cycle')
            """
        )

    db.commit()


def init_db(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_schema()
