import csv
import io
import itertools
import threading

from .db import get_db
from .services import now_iso, persist_reading


DEFAULT_SIMULATION_ROWS = [
    {"device_id": "ambient-light-esp32", "lux": 8},
    {"device_id": "ambient-light-esp32", "lux": 18},
    {"device_id": "ambient-light-esp32", "lux": 46},
    {"device_id": "ambient-light-esp32", "lux": 88},
    {"device_id": "ambient-light-esp32", "lux": 150},
    {"device_id": "ambient-light-esp32", "lux": 320},
    {"device_id": "ambient-light-esp32", "lux": 620},
    {"device_id": "ambient-light-esp32", "lux": 95},
    {"device_id": "ambient-light-esp32", "lux": 24},
]


class DemoEngine:
    """Cycle through CSV or built-in lux rows as a live hardware substitute."""

    def __init__(self, app, interval_seconds=5):
        self.app = app
        self.interval_seconds = max(1, int(interval_seconds))
        self._thread = None
        self._stop_event = threading.Event()
        self._rows = list(DEFAULT_SIMULATION_ROWS)
        self._values = itertools.cycle(self._rows)
        self.label = "Built-in light cycle"

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def load_csv_text(self, csv_text, label="Uploaded CSV simulation"):
        reader = csv.DictReader(io.StringIO(csv_text))
        expected = {"timestamp", "device_id", "lux"}
        if set(reader.fieldnames or []) != expected:
            raise ValueError("CSV header must be exactly: timestamp,device_id,lux")

        rows = []
        for row in reader:
            device_id = (row.get("device_id") or "").strip()
            if not device_id:
                raise ValueError("CSV rows must include device_id.")
            try:
                lux = float(row.get("lux"))
            except (TypeError, ValueError):
                raise ValueError("CSV lux values must be numeric.") from None
            if lux < 0:
                raise ValueError("CSV lux values cannot be negative.")
            rows.append({"device_id": device_id, "lux": lux})

        if not rows:
            raise ValueError("CSV file did not contain any data rows.")

        self._rows = rows
        self._values = itertools.cycle(self._rows)
        self.label = label

    def reset_default_rows(self):
        self._rows = list(DEFAULT_SIMULATION_ROWS)
        self._values = itertools.cycle(self._rows)
        self.label = "Built-in light cycle"

    def start(self):
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if not self.is_running():
            return
        self._stop_event.set()
        self._thread.join(timeout=1.5)
        self._thread = None

    def _run(self):
        while not self._stop_event.is_set():
            try:
                row = next(self._values)
                with self.app.app_context():
                    db = get_db()
                    persist_reading(
                        db,
                        {
                            "device_id": row["device_id"],
                            "lux": row["lux"],
                            "timestamp": now_iso(),
                            "source": "simulation",
                            "ble_status": "simulated",
                            "signal_active": True,
                            "sensor_status": "simulated",
                            "oled_status": "simulated",
                        },
                    )
            except Exception:
                self.app.logger.exception("Simulation engine failed to generate a reading")
            self._stop_event.wait(self.interval_seconds)
