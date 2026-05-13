let activeLocation = "Perth, Australia";
let activeCoordinates = null;
let currentSensorReading = null;
let currentRecentRows = [];
let currentWeatherSummary = null;
let bluetoothDevice = null;
let bluetoothCharacteristic = null;
let bluetoothBuffer = "";

const LOW_THRESHOLD_LUX = 50;
const HIGH_THRESHOLD_LUX = 50000;
const BLE_UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
const BLE_UART_TX_CHARACTERISTIC_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";

function resultValue(result, fallback = null) {
  return result.status === "fulfilled" ? result.value : fallback;
}

function numberValue(value, fallback = 0) {
  if (value === null || value === undefined || value === "") return fallback;
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function rounded(value, fallback = "--") {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return fallback;
  return Math.round(numericValue).toLocaleString();
}

function signedLux(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "-- lux";
  const sign = numericValue > 0 ? "+" : "";
  return `${sign}${Math.round(numericValue).toLocaleString()} lux`;
}

function lightAdvice(level) {
  if (level === "Too Dark") return "Below the low threshold. OLED warns the user and the buzzer should turn on.";
  if (level === "Dim") return "Low but inside the safe threshold band. OLED shows dim light; buzzer stays off.";
  if (level === "Ideal") return "Light is in the ideal range. OLED shows normal status; buzzer stays off.";
  if (level === "Bright") return "Bright but still inside the safe threshold band. Monitor for glare.";
  if (level === "Very Bright") return "Above the high threshold. OLED warns the user and the buzzer should turn on.";
  return "Connect Bluetooth or start demo mode to receive sensor data.";
}

function expectedOutdoorLux(weather) {
  const current = weather?.current || {};
  const radiation = numberValue(current.shortwave_radiation_w_m2, null);
  if (radiation !== null) return Math.max(0, radiation * 120);

  const isDay = numberValue(current.is_day, 0) === 1;
  if (!isDay) return 0;
  const cloudCover = Math.max(0, Math.min(numberValue(current.cloud_cover_percent, 50), 100));
  return Math.max(800, 100000 * (1 - cloudCover / 100));
}

function thresholdStatus(lux) {
  const value = numberValue(lux, null);
  if (value === null) return "Waiting";
  if (value < LOW_THRESHOLD_LUX) return "Below Threshold";
  if (value >= HIGH_THRESHOLD_LUX) return "Above Threshold";
  return "Within Threshold";
}

function buzzerState(status) {
  return status === "Within Threshold" ? "OFF" : status === "Waiting" ? "OFF" : "ON";
}

function oledMessage(reading) {
  if (!reading) return "VEML6030\nWaiting for data...";
  return `VEML6030\nLux: ${rounded(reading.lux)} lx\n${reading.light_level}\nBuzzer: ${reading.buzzer_state || buzzerState(reading.threshold_status)}`;
}

function locationLabelFromReading(reading) {
  if (!reading) return "Unknown location";
  if (reading.location_label) return reading.location_label;
  if (reading.latitude !== null && reading.latitude !== undefined && reading.longitude !== null && reading.longitude !== undefined) {
    return `${Number(reading.latitude).toFixed(5)}, ${Number(reading.longitude).toFixed(5)}`;
  }
  return activeLocation || "Unknown location";
}

function coordinatesText(reading) {
  const lat = reading?.latitude ?? activeCoordinates?.latitude;
  const lon = reading?.longitude ?? activeCoordinates?.longitude;
  if (lat === null || lat === undefined || lon === null || lon === undefined) {
    return "No coordinates received yet.";
  }
  return `Lat ${Number(lat).toFixed(5)}, Lon ${Number(lon).toFixed(5)}`;
}

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: rect.width, height: rect.height };
}

function drawRoundedLabel(ctx, text, x, y) {
  ctx.font = "700 15px Segoe UI, Arial";
  const width = ctx.measureText(text).width + 22;
  ctx.fillStyle = "#22232f";
  ctx.beginPath();
  ctx.roundRect(x - width / 2, y - 22, width, 34, 8);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.fillText(text, x, y);
}

function drawNoData(ctx, width, height) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "rgba(255,255,255,0.76)";
  ctx.font = "700 18px Segoe UI, Arial";
  ctx.textAlign = "center";
  ctx.fillText("Connect Bluetooth hardware to start the light trend", width / 2, height / 2);
}

function estimateSeries(length, weather) {
  const hourly = weather?.hourly || [];
  if (!hourly.length) return Array.from({ length }, () => expectedOutdoorLux(weather));
  return Array.from({ length }, (_, index) => {
    const row = hourly[Math.min(index, hourly.length - 1)];
    const radiation = numberValue(row.shortwave_radiation_w_m2, null);
    if (radiation !== null) return Math.max(0, radiation * 120);
    return expectedOutdoorLux(weather);
  });
}

function drawLightTrend(rows, weather) {
  const canvas = document.getElementById("lightTrendChart");
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  const ordered = [...rows].reverse();
  if (!ordered.length) {
    drawNoData(ctx, width, height);
    return;
  }

  const sensorValues = ordered.map((row) => numberValue(row.lux));
  const weatherValues = estimateSeries(ordered.length, weather);
  const maxValue = Math.max(...sensorValues, ...weatherValues, HIGH_THRESHOLD_LUX, 1000);
  const yMax = Math.min(120000, Math.ceil(maxValue / 1000) * 1000 || 1000);
  const padding = { top: 48, right: 40, bottom: 64, left: 82 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const xFor = (index) => padding.left + (ordered.length === 1 ? plotWidth : (plotWidth / (ordered.length - 1)) * index);
  const yFor = (value) => padding.top + plotHeight - (Math.max(0, value) / yMax) * plotHeight;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#252b52";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  ctx.font = "700 14px Segoe UI, Arial";
  ctx.fillStyle = "#f7f8ff";
  ctx.textAlign = "right";
  for (let i = 0; i <= 5; i += 1) {
    const value = (yMax / 5) * i;
    const y = yFor(value);
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
    ctx.fillText(`${Math.round(value).toLocaleString()} lx`, padding.left - 14, y + 5);
  }

  function thresholdLine(value, color, label) {
    const y = yFor(value);
    ctx.setLineDash([9, 8]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.textAlign = "left";
    ctx.fillText(label, padding.left + 10, y - 8);
  }

  thresholdLine(LOW_THRESHOLD_LUX, "#60a5fa", "Low threshold");
  thresholdLine(HIGH_THRESHOLD_LUX, "#ef4444", "High threshold");

  function drawSeries(values, color, dashed = false, lineWidth = 3) {
    ctx.setLineDash(dashed ? [4, 8] : []);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    values.forEach((value, index) => {
      const x = xFor(index);
      const y = yFor(value);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }

  const gradient = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
  gradient.addColorStop(0, "rgba(255, 208, 63, 0.26)");
  gradient.addColorStop(1, "rgba(255, 208, 63, 0.02)");
  ctx.beginPath();
  sensorValues.forEach((value, index) => {
    const x = xFor(index);
    const y = yFor(value);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(xFor(sensorValues.length - 1), height - padding.bottom);
  ctx.lineTo(xFor(0), height - padding.bottom);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  drawSeries(weatherValues, "#ffffff", true, 3);
  drawSeries(sensorValues, "#ffd03f", false, 4);

  sensorValues.forEach((value, index) => {
    const x = xFor(index);
    const y = yFor(value);
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#ffd03f";
    ctx.fill();
  });

  const latestIndex = sensorValues.length - 1;
  const latestX = xFor(latestIndex);
  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(latestX, padding.top);
  ctx.lineTo(latestX, height - padding.bottom);
  ctx.stroke();
  drawRoundedLabel(ctx, "Now", latestX, padding.top + 24);

  ctx.fillStyle = "#c9d1e8";
  ctx.textAlign = "center";
  ctx.font = "700 13px Segoe UI, Arial";
  ordered.forEach((row, index) => {
    if (index % Math.ceil(ordered.length / 6) !== 0 && index !== ordered.length - 1) return;
    const label = new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    ctx.fillText(label, xFor(index), height - 26);
  });
}

function updateRecentTable(rows) {
  const body = document.getElementById("recentReadingsBody");
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7">No readings yet. Connect Bluetooth hardware or start demo mode.</td></tr>';
    return;
  }

  body.innerHTML = rows.slice(0, 12).map((row) => {
    const threshold = row.threshold_status || thresholdStatus(row.lux);
    const buzzer = row.buzzer_state || buzzerState(threshold);
    const oled = row.oled_message || oledMessage(row).replace(/\n/g, " / ");
    return `<tr>
      <td>${formatDateTime(row.timestamp)}</td>
      <td>${formatLux(row.lux)}</td>
      <td>${lightLevelBadge(row.light_level)}</td>
      <td>${escapeHtml(threshold)}</td>
      <td><span class="buzzer-chip ${buzzer === "ON" ? "on" : "off"}">${buzzer}</span></td>
      <td>${escapeHtml(oled)}</td>
      <td>${escapeHtml(locationLabelFromReading(row))}</td>
    </tr>`;
  }).join("");
}

function updateComparison() {
  const hardwareLux = numberValue(currentSensorReading?.lux, null);
  const weatherLux = currentWeatherSummary ? expectedOutdoorLux(currentWeatherSummary) : null;
  document.getElementById("weatherLuxCompare").textContent = weatherLux === null ? "-- lux" : formatLux(weatherLux);

  const basis = currentWeatherSummary?.current?.shortwave_radiation_w_m2;
  document.getElementById("weatherBasisCompare").textContent =
    basis === null || basis === undefined
      ? "Estimated from daylight at the selected location."
      : `Estimated from ${rounded(basis)} W/m2 solar radiation at the selected location.`;

  if (hardwareLux === null || weatherLux === null) {
    document.getElementById("luxDifferenceCompare").textContent = "-- lux";
    document.getElementById("comparisonStatus").textContent = "Waiting for sensor and location data.";
    return;
  }

  const difference = hardwareLux - weatherLux;
  const percent = weatherLux > 0 ? Math.abs(difference) / weatherLux * 100 : hardwareLux <= LOW_THRESHOLD_LUX ? 0 : Infinity;
  document.getElementById("luxDifferenceCompare").textContent = signedLux(difference);
  if (percent <= 25) {
    document.getElementById("comparisonStatus").textContent = "Close to outdoor estimate.";
  } else if (difference < 0) {
    document.getElementById("comparisonStatus").textContent = "Sensor is lower than outdoor estimate. It may be shaded or indoors.";
  } else {
    document.getElementById("comparisonStatus").textContent = "Sensor is higher than outdoor estimate. Check nearby artificial or reflected light.";
  }
}

function updateSensor(latest, recent, status) {
  currentSensorReading = latest;
  currentRecentRows = recent || [];
  const lux = numberValue(latest?.lux, null);
  const level = latest?.light_level || "No reading";
  const threshold = latest?.threshold_status || thresholdStatus(lux);
  const buzzer = latest?.buzzer_state || buzzerState(threshold);

  document.getElementById("luxValue").textContent = lux === null ? "--" : rounded(lux);
  document.getElementById("lightLevelValue").innerHTML = latest ? lightLevelBadge(level) : "No reading";
  document.getElementById("lightAdvice").textContent = lightAdvice(level);
  document.getElementById("thresholdStatus").textContent = threshold;
  document.getElementById("thresholdRange").textContent = `Safe range: ${LOW_THRESHOLD_LUX}-${HIGH_THRESHOLD_LUX.toLocaleString()} lux`;
  document.getElementById("buzzerState").textContent = buzzer;
  document.getElementById("buzzerReason").textContent =
    buzzer === "ON" ? "Threshold exceeded. Hardware buzzer should alert the user." : "Reading is inside threshold. Buzzer remains off.";
  document.getElementById("buzzerIndicator").textContent = `Buzzer ${buzzer}`;
  document.getElementById("buzzerIndicator").className = `buzzer-indicator ${buzzer === "ON" ? "on" : "off"}`;
  document.getElementById("oledPreview").textContent = latest?.oled_message || oledMessage(latest);
  document.getElementById("hardwareLocation").textContent = locationLabelFromReading(latest);
  document.getElementById("hardwareCoordinates").textContent = coordinatesText(latest);
  document.getElementById("deviceStatus").textContent = status?.online || "offline";

  const markerPercent = lux === null
    ? 0
    : Math.max(0, Math.min(100, (Math.log10(Math.max(1, lux)) / Math.log10(188000)) * 100));
  document.getElementById("thresholdMarker").style.left = `${markerPercent}%`;

  updateRecentTable(recent || []);
  updateComparison();
  drawLightTrend(currentRecentRows, currentWeatherSummary);
}

function updateWeather(weather) {
  if (!weather) return;
  currentWeatherSummary = weather;
  if (weather.location?.label && !activeCoordinates) {
    activeLocation = weather.location.label;
    document.getElementById("locationSearch").value = activeLocation;
  }
  updateComparison();
  drawLightTrend(currentRecentRows, currentWeatherSummary);
}

function setBluetoothStatus(message) {
  document.getElementById("bluetoothStatus").textContent = message;
}

function apiKeyHeader() {
  const key = document.getElementById("ingestKeyInput").value.trim();
  if (key) localStorage.setItem("lightSensorIngestKey", key);
  return key ? { "X-API-Key": key } : {};
}

function enrichPayloadWithLocation(payload) {
  const enriched = { ...payload };
  if (!enriched.location_label && activeLocation) enriched.location_label = activeLocation;
  if (activeCoordinates) {
    if (enriched.latitude === undefined || enriched.latitude === null) enriched.latitude = activeCoordinates.latitude;
    if (enriched.longitude === undefined || enriched.longitude === null) enriched.longitude = activeCoordinates.longitude;
  }
  return enriched;
}

function parseBluetoothPayload(text) {
  const cleanText = text.trim();
  if (!cleanText) return null;

  if (cleanText.startsWith("{")) {
    const payload = JSON.parse(cleanText);
    return enrichPayloadWithLocation({
      device_id: payload.device_id || payload.device || "veml6030-ble-01",
      lux: Number(payload.lux),
      wifi_signal: payload.wifi_signal ?? payload.rssi,
      timestamp: payload.timestamp || new Date().toISOString(),
      source: "hardware",
      location_label: payload.location_label || payload.location,
      latitude: payload.latitude ?? payload.lat,
      longitude: payload.longitude ?? payload.lon ?? payload.lng,
    });
  }

  const pairs = {};
  cleanText.split(/[;,]/).forEach((part) => {
    const [key, value] = part.split("=").map((item) => item?.trim());
    if (key && value !== undefined) pairs[key.toLowerCase()] = value;
  });

  if (pairs.lux) {
    return enrichPayloadWithLocation({
      device_id: pairs.device_id || pairs.device || "veml6030-ble-01",
      lux: Number(pairs.lux),
      wifi_signal: pairs.wifi_signal || pairs.rssi || null,
      timestamp: pairs.timestamp || new Date().toISOString(),
      source: "hardware",
      location_label: pairs.location_label || pairs.location,
      latitude: pairs.latitude || pairs.lat,
      longitude: pairs.longitude || pairs.lon || pairs.lng,
    });
  }

  const values = cleanText.split(/[,\s]+/).filter(Boolean);
  const firstIsNumber = Number.isFinite(Number(values[0]));
  return enrichPayloadWithLocation({
    device_id: firstIsNumber ? "veml6030-ble-01" : values[0],
    lux: Number(firstIsNumber ? values[0] : values[1]),
    wifi_signal: firstIsNumber ? values[1] || null : values[2] || null,
    timestamp: new Date().toISOString(),
    source: "hardware",
  });
}

async function postBluetoothReading(payload) {
  if (!Number.isFinite(payload.lux)) {
    throw new Error("Bluetooth packet did not include a valid lux value.");
  }

  const response = await fetch(`${API_BASE}/readings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...apiKeyHeader(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || "Failed to save Bluetooth reading.");
  }
  return response.json();
}

async function handleBluetoothText(text) {
  const payload = parseBluetoothPayload(text);
  if (!payload) return;
  document.getElementById("bluetoothPacket").textContent = `Last packet: ${text.trim()}`;
  await postBluetoothReading(payload);
  setBluetoothStatus("receiving");
  refreshDashboard();
}

function handleBluetoothNotification(event) {
  const value = new TextDecoder().decode(event.target.value);
  bluetoothBuffer += value;
  const packets = bluetoothBuffer.split(/\r?\n/);
  bluetoothBuffer = packets.pop();
  packets.filter(Boolean).forEach((packet) => {
    handleBluetoothText(packet).catch((error) => {
      console.error("Bluetooth packet failed", error);
      setBluetoothStatus("packet error");
    });
  });

  const possiblePacket = bluetoothBuffer.trim();
  if (
    possiblePacket &&
    ((possiblePacket.startsWith("{") && possiblePacket.endsWith("}")) ||
      possiblePacket.includes("lux=") ||
      /^-?\d+(\.\d+)?([,\s]|$)/.test(possiblePacket))
  ) {
    bluetoothBuffer = "";
    handleBluetoothText(possiblePacket).catch((error) => {
      console.error("Bluetooth packet failed", error);
      setBluetoothStatus("packet error");
    });
  }
}

async function connectBluetooth() {
  if (!navigator.bluetooth) {
    setBluetoothStatus("unsupported");
    return;
  }

  try {
    setBluetoothStatus("pairing");
    bluetoothDevice = await navigator.bluetooth.requestDevice({
      filters: [
        { services: [BLE_UART_SERVICE_UUID] },
        { namePrefix: "VEML" },
        { namePrefix: "Light" },
        { namePrefix: "ESP32" },
      ],
      optionalServices: [BLE_UART_SERVICE_UUID],
    });
    bluetoothDevice.addEventListener("gattserverdisconnected", () => {
      setBluetoothStatus("disconnected");
      bluetoothCharacteristic = null;
    });

    setBluetoothStatus("connecting");
    const server = await bluetoothDevice.gatt.connect();
    const service = await server.getPrimaryService(BLE_UART_SERVICE_UUID);
    bluetoothCharacteristic = await service.getCharacteristic(BLE_UART_TX_CHARACTERISTIC_UUID);
    bluetoothCharacteristic.addEventListener("characteristicvaluechanged", handleBluetoothNotification);
    await bluetoothCharacteristic.startNotifications();
    setBluetoothStatus("connected");
  } catch (error) {
    console.error("Bluetooth connection failed", error);
    setBluetoothStatus("connection failed");
  }
}

function disconnectBluetooth() {
  if (bluetoothCharacteristic) {
    bluetoothCharacteristic.removeEventListener("characteristicvaluechanged", handleBluetoothNotification);
    bluetoothCharacteristic = null;
  }
  if (bluetoothDevice?.gatt?.connected) bluetoothDevice.gatt.disconnect();
  setBluetoothStatus("disconnected");
}

async function useCurrentLocation() {
  if (!navigator.geolocation) {
    document.getElementById("hardwareCoordinates").textContent = "Browser geolocation is not available.";
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (position) => {
      activeCoordinates = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      };
      activeLocation = "Current hardware location";
      document.getElementById("locationSearch").value = activeLocation;
      refreshDashboard();
    },
    (error) => {
      document.getElementById("hardwareCoordinates").textContent = `Location unavailable: ${error.message}`;
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
  );
}

async function fetchWeather() {
  const params = new URLSearchParams();
  params.set("location", activeLocation);
  if (activeCoordinates) {
    params.set("latitude", activeCoordinates.latitude);
    params.set("longitude", activeCoordinates.longitude);
  }
  return apiGet(`/weather?${params.toString()}`);
}

async function refreshDashboard() {
  try {
    const [latestResult, recentResult, statusResult] = await Promise.allSettled([
      apiGet("/readings/latest"),
      apiGet("/readings/recent?limit=60"),
      apiGet("/device-status"),
    ]);
    const latest = resultValue(latestResult);
    if (latest?.latitude !== null && latest?.latitude !== undefined && latest?.longitude !== null && latest?.longitude !== undefined) {
      activeCoordinates = {
        latitude: latest.latitude,
        longitude: latest.longitude,
      };
      if (latest.location_label) {
        activeLocation = latest.location_label;
        document.getElementById("locationSearch").value = activeLocation;
      }
    }

    updateSensor(
      latest,
      resultValue(recentResult, []),
      resultValue(statusResult, {})
    );
    const weather = await fetchWeather();
    updateWeather(weather);
  } catch (error) {
    console.error("Dashboard refresh failed", error);
  }
}

document.getElementById("refreshDashboardBtn").addEventListener("click", refreshDashboard);
document.getElementById("connectBluetoothBtn").addEventListener("click", connectBluetooth);
document.getElementById("disconnectBluetoothBtn").addEventListener("click", disconnectBluetooth);
document.getElementById("useLocationBtn").addEventListener("click", useCurrentLocation);
document.getElementById("locationSearch").addEventListener("change", (event) => {
  activeLocation = event.target.value.trim() || "Perth, Australia";
  activeCoordinates = null;
  refreshDashboard();
});
document.getElementById("ingestKeyInput").value = localStorage.getItem("lightSensorIngestKey") || "";
document.getElementById("locationSearch").value = activeLocation;
refreshDashboard();
setInterval(refreshDashboard, 30000);
window.addEventListener("resize", () => refreshDashboard());
