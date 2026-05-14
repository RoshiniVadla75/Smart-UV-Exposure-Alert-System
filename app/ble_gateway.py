import asyncio
import json
import threading

from .db import get_db
from .services import now_iso, persist_reading, update_device_status


BLE_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
BLE_NOTIFY_CHARACTERISTIC_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
BLE_NAME_HINTS = ("esp32", "veml", "light", "uv")


class BleGateway:
    def __init__(self, app):
        self.app = app
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.client = None
        self.device_name = "ESP32-VEML6030"
        self.device_address = None
        self.packet_buffer = ""
        self.status = "disconnected"
        self.error = None

    def scan(self, timeout=8):
        bleak = _load_bleak()
        return asyncio.run(_scan_devices(bleak.BleakScanner, timeout=timeout))

    def connect(self, address, name=None):
        if not address:
            raise ValueError("Bluetooth device address is required.")

        self.disconnect()
        with self.lock:
            self.stop_event.clear()
            self.device_address = address
            self.device_name = name or address
            self.status = "connecting"
            self.error = None
            self.packet_buffer = ""
            self.thread = threading.Thread(
                target=self._thread_main,
                args=(address,),
                daemon=True,
                name="ble-gateway",
            )
            self.thread.start()
        self._update_device_status("connecting", signal_active=False)
        return self.snapshot()

    def disconnect(self):
        thread = None
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.stop_event.set()
                thread = self.thread
        if thread:
            thread.join(timeout=3)
        with self.lock:
            self.thread = None
            self.client = None
            if self.status != "failed":
                self.status = "disconnected"
        self._update_device_status("disconnected", signal_active=False)

    def snapshot(self):
        with self.lock:
            return {
                "status": self.status,
                "device_name": self.device_name,
                "device_address": self.device_address,
                "error": self.error,
                "connected": self.status == "connected",
            }

    def _thread_main(self, address):
        try:
            asyncio.run(self._run_connection(address))
        except Exception as exc:  # noqa: BLE connection errors are surfaced to the UI.
            with self.lock:
                self.status = "failed"
                self.error = str(exc)
            self._update_device_status("failed", signal_active=False)

    async def _run_connection(self, address):
        bleak = _load_bleak()

        async with bleak.BleakClient(address) as client:
            with self.lock:
                self.client = client
                self.status = "connected"
                self.error = None
            self._update_device_status("connected", signal_active=True)

            await client.start_notify(
                BLE_NOTIFY_CHARACTERISTIC_UUID,
                lambda _, data: self._handle_notification(data),
            )

            while not self.stop_event.is_set() and client.is_connected:
                await asyncio.sleep(0.25)

            if client.is_connected:
                await client.stop_notify(BLE_NOTIFY_CHARACTERISTIC_UUID)

        with self.lock:
            if self.status != "failed":
                self.status = "disconnected"
        self._update_device_status("disconnected", signal_active=False)

    def _handle_notification(self, data):
        self.packet_buffer += bytes(data).decode("utf-8", errors="replace")
        packets = self.packet_buffer.splitlines(keepends=True)
        if packets and not packets[-1].endswith(("\n", "\r")):
            self.packet_buffer = packets.pop()
        else:
            self.packet_buffer = ""

        for packet in packets:
            cleaned = packet.strip()
            if cleaned:
                self._persist_packet(cleaned)

    def _persist_packet(self, packet):
        payload = parse_ble_packet(packet, self.device_name)
        with self.app.app_context():
            persist_reading(get_db(), payload)

    def _update_device_status(self, status, signal_active=False):
        with self.app.app_context():
            update_device_status(
                get_db(),
                {
                    "device_id": self.device_name,
                    "last_seen": now_iso(),
                    "ble_status": status,
                    "signal_active": signal_active,
                    "sensor_status": "active" if status == "connected" else "inactive",
                    "oled_status": "active" if status == "connected" else "inactive",
                },
            )


def _load_bleak():
    try:
        import bleak
    except ImportError as exc:
        raise RuntimeError(
            "Server Bluetooth scanning needs the bleak package. "
            "Run `python -m pip install -r requirements.txt` and restart Flask."
        ) from exc
    return bleak


async def _scan_devices(scanner, timeout=8):
    discovered = await scanner.discover(
        timeout=max(2, min(float(timeout or 8), 15)),
        return_adv=True,
    )
    payload = []
    for item in discovered.values():
        if isinstance(item, tuple):
            device, advertisement = item
        else:
            device, advertisement = item, None
        name = (
            getattr(advertisement, "local_name", None)
            or device.name
            or "Unnamed BLE device"
        )
        service_uuids = [
            str(uuid).lower()
            for uuid in (getattr(advertisement, "service_uuids", None) or [])
        ]
        address = device.address
        payload.append(
            {
                "name": name,
                "address": address,
                "rssi": getattr(device, "rssi", None),
                "service_uuids": service_uuids,
                "likely_esp32": _looks_like_sensor(name) or BLE_SERVICE_UUID in service_uuids,
            }
        )

    payload.sort(key=lambda item: (not item["likely_esp32"], item["name"].lower()))
    return payload


def _looks_like_sensor(name):
    value = str(name or "").lower()
    return any(hint in value for hint in BLE_NAME_HINTS)


def parse_ble_packet(packet, fallback_device_name="ESP32-VEML6030"):
    raw_packet = str(packet or "").strip()
    if not raw_packet:
        raise ValueError("BLE packet was empty.")

    if raw_packet.startswith("{"):
        parsed = json.loads(raw_packet)
    elif "=" in raw_packet:
        parsed = {}
        for part in raw_packet.split(","):
            key, separator, value = part.partition("=")
            if separator:
                parsed[key.strip()] = value.strip()
    else:
        parts = [part.strip() for part in raw_packet.split(",")]
        if len(parts) == 1:
            parsed = {"device_id": fallback_device_name, "lux": parts[0]}
        else:
            parsed = {
                "device_id": parts[0],
                "lux": parts[1],
                "wifi_signal": parts[2] if len(parts) > 2 else None,
            }

    try:
        lux = float(parsed.get("lux"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"BLE packet did not include a numeric lux value: {raw_packet}") from exc

    return {
        "device_id": parsed.get("device_id") or parsed.get("device") or fallback_device_name,
        "lux": lux,
        "wifi_signal": parsed.get("wifi_signal") or parsed.get("rssi"),
        "esp32_uptime_seconds": parsed.get("esp32_uptime_seconds") or parsed.get("uptime"),
        "raw_packet": raw_packet,
        "source": "hardware",
        "ble_status": "connected",
        "signal_active": True,
        "timestamp": now_iso(),
    }
