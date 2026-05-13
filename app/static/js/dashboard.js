let uvTrendChart = null;

const DASHBOARD_DEFAULTS = {
  lux: 0,
  estimated_uv: null,
  weather_uv: null,
  risk: "Unknown",
  buzzer: false,
  bluetooth: "Disconnected",
  condition: "Weather unavailable",
  daylight: "Unknown",
  location: "Perth, Western Australia, Australia",
  cloud_cover: null,
  temperature: null,
  humidity: null,
  wind: null,
  sunrise: null,
  sunset: null,
  weather_available: false,
  weather_source_label: "Weather unavailable",
  weather_note: "Weather unavailable",
  forecast: [],
};

function text(id, value) {
  if (Array.isArray(id)) {
    id.forEach((item) => text(item, value));
    return;
  }
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function safeNumber(value, fallback = 0) {
  const numeric = numberOrNull(value);
  return numeric === null ? fallback : numeric;
}

function titleCase(value) {
  return String(value || "")
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function uvRisk(value) {
  const score = numberOrNull(value);
  if (score === null) return "Unavailable";
  if (score <= 2) return "Low";
  if (score <= 5) return "Moderate";
  if (score <= 7) return "High";
  if (score <= 10) return "Very High";
  return "Extreme";
}

function luxBand(lux) {
  const value = safeNumber(lux);
  if (value < 1000) return "Low brightness";
  if (value < 10000) return "Moderate brightness";
  return "High brightness";
}

function formatLux(value) {
  return `${Math.round(safeNumber(value)).toLocaleString()} lux`;
}

function formatPercent(value) {
  const numeric = numberOrNull(value);
  return numeric === null ? "--" : `${Math.round(numeric)}%`;
}

function formatTemperature(value) {
  const numeric = numberOrNull(value);
  return numeric === null ? "Weather unavailable" : `${Math.round(numeric)}\u00b0C`;
}

function formatWind(value) {
  const numeric = numberOrNull(value);
  return numeric === null ? "--" : `${Math.round(numeric)} km/h`;
}

function formatUv(value) {
  const numeric = numberOrNull(value);
  if (numeric === null) return "--";
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1);
}

function formatDateLabel(value) {
  if (!value) return "--";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

function formatTimeLabel(value) {
  if (!value) return "--";
  if (!String(value).includes("T")) return String(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function weatherMode(condition, daylight) {
  const value = String(condition || "").toLowerCase();
  if (String(daylight || "").toLowerCase() === "night") return "night";
  if (value.includes("rain") || value.includes("drizzle") || value.includes("storm")) return "rainy";
  if (value.includes("cloud") || value.includes("overcast") || value.includes("fog")) return "cloudy";
  return "sunny";
}

function climateSummary(weatherResponse = {}) {
  const status = weatherResponse.status || "error";
  const source = weatherResponse.source || "unavailable";
  const current = weatherResponse.current || {};
  const daily = weatherResponse.daily || {};
  const isLive = status === "ok" && source !== "demo";
  const isDemo = source === "demo";
  const isDay = current.is_day;
  const weatherUv = numberOrNull(current.uv_index ?? daily.uv_index_max);

  return {
    available: status === "ok",
    source,
    source_label:
      weatherResponse.source_label ||
      (isLive ? "Live weather" : isDemo ? "Demo weather" : "Weather unavailable"),
    note:
      weatherResponse.note ||
      (isLive ? "Live weather" : isDemo ? "Demo weather data" : "Weather unavailable"),
    condition: status === "ok" ? current.condition || "Mixed Conditions" : "Weather unavailable",
    daylight: isDay === 0 ? "Night" : isDay === 1 ? "Day" : "Unknown",
    cloud_cover: numberOrNull(current.cloud_cover_percent),
    temperature: numberOrNull(current.temperature_c),
    humidity: numberOrNull(current.humidity_percent),
    wind: numberOrNull(current.wind_speed_kmh),
    weather_uv: weatherUv,
    sunrise: daily.sunrise || null,
    sunset: daily.sunset || null,
    location: weatherResponse.location?.label || DASHBOARD_DEFAULTS.location,
    forecast: Array.isArray(weatherResponse.forecast) ? weatherResponse.forecast : [],
  };
}

function estimateUvFromEnvironment(lux, weatherUv, daylight, cloudCover) {
  const brightnessFactor = Math.min(1.25, safeNumber(lux) / 28000);
  const dayFactor = String(daylight).toLowerCase() === "night" ? 0.18 : 1;
  const cloudFactor =
    numberOrNull(cloudCover) === null ? 1 : Math.max(0.48, 1 - safeNumber(cloudCover) / 180);
  const weatherComponent = numberOrNull(weatherUv) === null ? 0 : safeNumber(weatherUv) * 0.58;
  const composite = weatherComponent + brightnessFactor * 5.4 * cloudFactor * dayFactor;
  return Math.max(0, Math.min(12, Math.round(composite * 10) / 10));
}

function deriveComparison(model, risk) {
  if (!model.weather_available) {
    return {
      expected: "Weather unavailable",
      message: "Weather unavailable. The local UV estimate is using sensor brightness only until live weather reconnects.",
    };
  }

  const lowerCondition = String(model.condition).toLowerCase();
  if (String(model.daylight).toLowerCase() === "night") {
    return {
      expected: "Low",
      message: "Night-time conditions reduce expected UV exposure. The monitor keeps local brightness separate from weather-derived UV context.",
    };
  }
  if (lowerCondition.includes("rain") || lowerCondition.includes("storm") || lowerCondition.includes("fog")) {
    return {
      expected: "Low to Moderate",
      message: `Cloudy or wet conditions reduce expected exposure. The estimated local UV display is ${risk.toLowerCase()} after combining brightness and live weather context.`,
    };
  }
  if (numberOrNull(model.weather_uv) !== null && model.estimated_uv + 1 < model.weather_uv) {
    return {
      expected: uvRisk(model.weather_uv),
      message: "Local brightness is lower than the live weather UV context suggests. Shade, obstruction, or the immediate environment may be reducing exposure.",
    };
  }
  return {
    expected: uvRisk(model.weather_uv),
    message: `Local brightness and live weather conditions are consistent. Estimated UV exposure is ${risk.toLowerCase()} today.`,
  };
}

function setGauge(prefix, value) {
  const numeric = numberOrNull(value);
  const valueId =
    prefix === "estimated"
      ? ["estimatedUvValue", "estimated-uv-value"]
      : [`${prefix}UvValue`, `${prefix}-uv-value`];

  text(valueId, formatUv(numeric));
  text(`${prefix}RiskLabel`, numeric === null ? "Weather unavailable" : uvRisk(numeric));

  const needle = document.getElementById(`${prefix}Needle`);
  if (needle) {
    const angle = numeric === null ? -90 : -90 + Math.min(1, numeric / 12) * 180;
    needle.style.transform = `rotate(${angle}deg)`;
  }
}

async function connectBluetooth() {
  console.log("Bluetooth button clicked");

  if (!navigator.bluetooth) {
    alert("Web Bluetooth is not supported in this browser. Use Chrome or Edge.");
    return;
  }

  try {
    const device = await navigator.bluetooth.requestDevice({
      acceptAllDevices: true,
      optionalServices: ["12345678-1234-1234-1234-123456789abc"]
    });

    console.log("Selected device:", device.name);
    alert("Connected popup opened. Selected: " + device.name);

  } catch (error) {
    console.error("Bluetooth error:", error);
    alert("Bluetooth failed: " + error.message);
  }
}

function updateDashboardFromBLE(data) {
  const estimatedUv = safeNumber(
    data.estimated_uv,
    estimateUvFromEnvironment(data.lux, null, "Unknown", null)
  );
  const risk = data.risk || uvRisk(estimatedUv);
  const buzzerOn = Boolean(data.buzzer);

  text(["lux-value", "luxStatValue"], formatLux(data.lux));
  text(["estimated-uv-value", "estimatedUvValue"], formatUv(estimatedUv));
  text(["risk-value", "riskStatValue"], risk);
  text(["buzzer-value", "buzzerStatValue"], buzzerOn ? "ON" : "OFF");
  text(["bluetooth-value", "bluetoothStatValue"], "Connected");
  text("oled-lux", `Lux: ${Math.round(safeNumber(data.lux))}`);
  text("oled-risk", `UV Risk: ${risk.toUpperCase()}`);
  text("oled-buzzer", `Buzzer: ${buzzerOn ? "ON" : "OFF"}`);
  text("oled-ble", "BLE: CONNECTED");
  text("luxBandLabel", luxBand(data.lux));
  text("buzzerStatNote", buzzerOn ? "Alert active" : "No alert");
  setGauge("estimated", estimatedUv);
  updateBluetoothStatus("Connected");
}

function updateBluetoothStatus(status) {
  text(["bluetooth-value", "bluetoothStatValue"], status);
  text("heroBluetoothLabel", status);
  text("sidebarBluetoothLabel", status);
  text("mobileBluetoothLabel", status === "Connected" ? "BLE On" : "BLE Off");
  text("oled-ble", `BLE: ${String(status).toUpperCase()}`);
}

function applyHeroMode(condition, daylight) {
  const hero = document.getElementById("heroPanel");
  if (!hero) return;
  const mode = weatherMode(condition, daylight);
  hero.classList.remove("hero-sunny", "hero-cloudy", "hero-rainy", "hero-night");
  hero.classList.add(`hero-${mode}`);

  const orb = document.getElementById("weatherOrb");
  if (orb) {
    orb.className = `weather-orb ${mode === "night" ? "night" : "sunny"}`;
  }
}

function setClock() {
  const now = new Date();
  text("clockValue", now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
  text("dateValue", now.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }));
}

function buildTrendSeries(historyRows, estimatedUv, weatherUv, daylight, cloudCover) {
  if (!Array.isArray(historyRows) || historyRows.length < 2) {
    return {
      labels: ["Now"],
      estimated: [numberOrNull(estimatedUv)],
      weather: [numberOrNull(weatherUv)],
    };
  }

  const rows = historyRows.slice(-9);
  return {
    labels: rows.map((row) =>
      new Date(row.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    ),
    estimated: rows.map((row) =>
      estimateUvFromEnvironment(row.lux, weatherUv, daylight, cloudCover)
    ),
    weather: rows.map(() => numberOrNull(weatherUv)),
  };
}

function renderTrendChart(series) {
  const canvas = document.getElementById("uvTrendChart");
  if (!canvas || typeof Chart === "undefined") return;
  if (uvTrendChart) uvTrendChart.destroy();

  uvTrendChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: series.labels,
      datasets: [
        {
          label: "Estimated Local UV",
          data: series.estimated,
          borderColor: "#a764ff",
          backgroundColor: "rgba(167, 100, 255, 0.14)",
          tension: 0.42,
          fill: false,
          pointRadius: 3,
          pointHoverRadius: 5,
        },
        {
          label: "Weather UV Index",
          data: series.weather,
          borderColor: "#ffd447",
          backgroundColor: "rgba(255, 212, 71, 0.12)",
          tension: 0.42,
          fill: false,
          pointRadius: 3,
          pointHoverRadius: 5,
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: "#d8e6f7",
            boxWidth: 12,
            usePointStyle: true,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#afc2da" },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
        y: {
          min: 0,
          max: 12,
          ticks: { color: "#afc2da", stepSize: 2 },
          grid: { color: "rgba(255,255,255,0.08)" },
        },
      },
    },
  });
}

function renderForecast(forecast = []) {
  const grid = document.getElementById("forecastGrid");
  if (!grid) return;

  if (!forecast.length) {
    grid.innerHTML = `
      <article class="forecast-card">
        <span>Forecast</span>
        <strong>Weather unavailable</strong>
        <div class="forecast-visual cloudy" aria-hidden="true"></div>
        <strong>--</strong>
        <small>No live forecast</small>
      </article>
    `;
    return;
  }

  grid.innerHTML = forecast.slice(0, 7).map((item) => {
    const mode = weatherMode(item.condition, "Day");
    return `
      <article class="forecast-card">
        <span>${formatDateLabel(item.date).split(",")[0]}</span>
        <strong>${formatDateLabel(item.date)}</strong>
        <div class="forecast-visual ${mode}" aria-hidden="true"></div>
        <strong>${formatTemperature(item.temperature_max_c)} / ${formatTemperature(item.temperature_min_c)}</strong>
        <small>UV: ${formatUv(item.uv_index_max)}</small>
      </article>
    `;
  }).join("");
}

function updateRecommendations(risk) {
  const list = document.getElementById("recommendationList");
  if (!list) return;
  const guidance = {
    Low: ["Outdoor activity is comfortable.", "Keep hydration nearby.", "Use eye comfort measures when glare is present."],
    Moderate: ["Use sunscreen SPF 30+.", "Wear sunglasses outdoors.", "Stay hydrated.", "Avoid direct sun from 12 PM to 3 PM."],
    High: ["Use sunscreen SPF 30+.", "Wear sunglasses and a hat.", "Prefer shade during peak daylight.", "Reduce prolonged direct exposure."],
    "Very High": ["Seek shade during peak hours.", "Use broad sun protection.", "Limit unnecessary direct exposure.", "Recheck conditions before outdoor work."],
    Extreme: ["Minimize direct exposure.", "Use comprehensive protection.", "Schedule outdoor tasks outside peak daylight.", "Follow local safety advice."],
    Unavailable: ["Weather UV is unavailable.", "Use local brightness as a temporary estimate.", "Reconnect live weather before making weather-based decisions."],
  };
  list.innerHTML = (guidance[risk] || guidance.Unavailable).map((item) => `<li>${item}</li>`).join("");
}

function updateDashboard(model) {
  const risk = uvRisk(model.estimated_uv);
  const comparison = deriveComparison(model, risk);
  const updatedAt = new Date();

  text("locationLabel", model.location);
  text("temperatureLabel", formatTemperature(model.temperature));
  text("conditionLabel", model.condition);
  text("humidityLabel", formatPercent(model.humidity));
  text("windLabel", formatWind(model.wind));
  text("cloudCoverLabel", formatPercent(model.cloud_cover));
  text("sunriseLabel", formatTimeLabel(model.sunrise));
  text("sunsetLabel", formatTimeLabel(model.sunset));
  text("weatherSourceLabel", model.weather_source_label);
  text("weatherApiNote", model.weather_note);

  setGauge("estimated", model.estimated_uv);
  setGauge("weather", model.weather_uv);
  text(
    "estimatedGaugeMessage",
    model.weather_available
      ? "Estimated from local brightness, daylight, cloud cover, and live weather UV."
      : "Weather unavailable. Estimated from local brightness only."
  );

  text(["lux-value", "luxStatValue"], formatLux(model.lux));
  text("luxBandLabel", luxBand(model.lux));
  text(["risk-value", "riskStatValue"], risk);
  text(["buzzer-value", "buzzerStatValue"], model.buzzer ? "ON" : "OFF");
  text("buzzerStatNote", model.buzzer ? "Alert active" : "No alert");
  text(["bluetooth-value", "bluetoothStatValue"], model.bluetooth);
  text("bluetoothSignalText", model.bluetooth === "Connected" ? "Signal active" : "Awaiting BLE");
  text("updatedStatValue", model.last_updated || updatedAt.toLocaleTimeString());
  text("updatedStatDate", model.last_updated_date || updatedAt.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }));

  text("heroBluetoothLabel", model.bluetooth);
  text("sidebarBluetoothLabel", model.bluetooth);
  text("sidebarBuzzerLabel", model.buzzer ? "ON" : "OFF");
  text("deviceOnlineLabel", model.device_online || "Online");
  text("sensorStateLabel", model.sensor_status || "Active");
  text("oledStateLabel", model.oled_status || "Active");
  text("lastSeenLabel", model.last_seen || "Recently");

  text("comparisonWeather", model.condition);
  text("comparisonDaylight", model.daylight);
  text("comparisonExpected", comparison.expected);
  text("comparisonEstimated", risk);
  text("comparisonMessage", comparison.message);

  if (document.getElementById("oled-lux")) {
    text("oled-lux", `Lux: ${Math.round(safeNumber(model.lux))}`);
    text("oled-risk", `UV Risk: ${risk.toUpperCase()}`);
    text("oled-buzzer", `Buzzer: ${model.buzzer ? "ON" : "OFF"}`);
    text("oled-ble", `BLE: ${model.bluetooth.toUpperCase()}`);
  } else {
    text(
      "oledSimulation",
      `Lux: ${Math.round(safeNumber(model.lux))}\nUV Risk: ${risk.toUpperCase()}\nBuzzer: ${model.buzzer ? "ON" : "OFF"}\nBLE: ${model.bluetooth.toUpperCase()}`
    );
  }

  updateRecommendations(risk);
  applyHeroMode(model.condition, model.daylight);
  renderForecast(model.forecast);
}

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Request failed for ${path}`);
  return response.json();
}

function mergeDeviceState(model, deviceStatus) {
  if (!deviceStatus) return model;
  const connected = String(deviceStatus.ble_status || "").toLowerCase() === "connected";
  return {
    ...model,
    bluetooth: connected ? "Connected" : titleCase(deviceStatus.ble_status || "Disconnected"),
    device_online: titleCase(deviceStatus.online || "online"),
    sensor_status: titleCase(deviceStatus.sensor_status || "active"),
    oled_status: titleCase(deviceStatus.oled_status || "active"),
    buzzer: String(deviceStatus.buzzer_status || "").toUpperCase() === "ON" || model.buzzer,
    last_seen: deviceStatus.last_seen ? "Recently updated" : model.last_seen,
  };
}

async function loadDashboard() {
  setClock();

  const [currentResult, weatherResult, historyResult, deviceResult] =
    await Promise.allSettled([
      getJson("/api/readings/latest"),
      getJson("/api/weather"),
      getJson("/api/history"),
      getJson("/api/device-status"),
    ]);

  const weather =
    weatherResult.status === "fulfilled"
      ? climateSummary(weatherResult.value)
      : climateSummary({ source: "unavailable", status: "error", note: "Weather unavailable" });
  const current = currentResult.status === "fulfilled" && currentResult.value ? currentResult.value : {};
  const lux = safeNumber(current.lux);
  const weatherUv = weather.weather_uv;
  const estimatedUv = estimateUvFromEnvironment(lux, weatherUv, weather.daylight, weather.cloud_cover);
  const currentTimestamp = current.timestamp ? new Date(current.timestamp) : new Date();
  let model = {
    ...DASHBOARD_DEFAULTS,
    lux,
    estimated_uv: estimatedUv,
    weather_uv: weatherUv,
    risk: uvRisk(estimatedUv),
    buzzer: String(current.buzzer || "").toUpperCase() === "ON",
    bluetooth: titleCase(current.ble_status || DASHBOARD_DEFAULTS.bluetooth),
    condition: weather.condition,
    daylight: weather.daylight,
    location: weather.location,
    cloud_cover: weather.cloud_cover,
    temperature: weather.temperature,
    humidity: weather.humidity,
    wind: weather.wind,
    sunrise: weather.sunrise,
    sunset: weather.sunset,
    weather_available: weather.available,
    weather_source_label: weather.source_label,
    weather_note: weather.note,
    forecast: weather.forecast,
    last_updated: currentTimestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    last_updated_date: currentTimestamp.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }),
  };

  if (deviceResult.status === "fulfilled") {
    model = mergeDeviceState(model, deviceResult.value);
  }

  updateDashboard(model);
  const historyRows = historyResult.status === "fulfilled" ? historyResult.value : [];
  renderTrendChart(buildTrendSeries(historyRows, estimatedUv, weatherUv, weather.daylight, weather.cloud_cover));
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("connectBluetoothBtn");

  if (btn) {
    btn.addEventListener("click", connectBluetooth);
  }

  loadDashboard().catch((error) => {
    console.error("Dashboard data load failed", error);
    const model = {
      ...DASHBOARD_DEFAULTS,
      estimated_uv: estimateUvFromEnvironment(DASHBOARD_DEFAULTS.lux, null, "Unknown", null),
    };
    updateDashboard(model);
    renderTrendChart(buildTrendSeries([], model.estimated_uv, null, "Unknown", null));
  });
  setInterval(setClock, 30000);
});

window.connectBluetooth = connectBluetooth;
