import itertools
import threading
import time

from .db import get_db
from .services import now_iso, persist_reading


class DemoEngine:
    """Generate demo light sensor readings from VEML6030."""

    def __init__(self, app, interval_seconds=5):
        self.app = app
        self.interval_seconds = max(1, int(interval_seconds))
        self._thread = None
        self._stop_event = threading.Event()
        # Simulate realistic lux values throughout the day
        self._values = itertools.cycle([
            100, 250, 500, 800, 1200, 2000, 3500, 5000, 7500, 10000,
            15000, 25000, 40000, 55000, 65000, 55000, 40000, 25000, 15000, 10000,
            7500, 5000, 3500, 2000, 1200, 800, 500, 250, 100, 50
        ])

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

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
                with self.app.app_context():
                    db = get_db()
                    persist_reading(
                        db,
                        {
                            "device_id": "light-sensor-01",
                            "lux": next(self._values),
                            "wifi_signal": -58,
                            "timestamp": now_iso(),
                            "source": "demo",
                        },
                    )
            except Exception:
                self.app.logger.exception("Demo engine failed to generate reading")
            self._stop_event.wait(self.interval_seconds)
