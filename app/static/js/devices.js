async function refreshDevices() {
  try {
    const [status, health] = await Promise.all([apiGet("/device-status"), apiGet("/health")]);
    document.getElementById("deviceId").textContent = status.device_id ?? "-";
    document.getElementById("onlineStatus").textContent = status.online;
    document.getElementById("mode").textContent = status.mode ?? "hardware";
    document.getElementById("lastSeen").textContent = formatDateTime(status.last_seen);
    document.getElementById("wifiSignal").textContent = status.latest_wifi_signal ?? "-";
    document.getElementById("apiHealth").textContent = `${health.backend}/${health.database}`;
  } catch (error) {
    console.error("Devices refresh failed", error);
  }
}

refreshDevices();
setInterval(refreshDevices, 5000);
