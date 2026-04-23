import itertools
import threading
import time

from .db import get_db
from .services import now_iso, persist_reading


class DemoEngine:
    def __init__(self, app, interval_seconds=5):
        self.app = app
        self.interval_seconds = max(1, int(interval_seconds))
        self._thread = None
        self._stop_event = threading.Event()
        self._values = itertools.cycle([1.2, 1.8, 2.5, 3.1, 4.4, 5.2, 6.7, 7.4, 5.9, 3.8, 2.1])

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
                            "device_id": "uv-station-01",
                            "uv_index": next(self._values),
                            "wifi_signal": -58,
                            "timestamp": now_iso(),
                            "source": "demo",
                        },
                    )
            except Exception:
                self.app.logger.exception("Demo engine failed to generate reading")
            self._stop_event.wait(self.interval_seconds)
