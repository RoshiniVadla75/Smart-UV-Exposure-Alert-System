const API_BASE = "/api";

function escapeHtml(value) {
  return String(value ?? "-")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatLux(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numericValue = Number(value);
  if (Number.isNaN(numericValue)) return "-";
  return `${numericValue.toLocaleString(undefined, { maximumFractionDigits: 2 })} lux`;
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`Request failed: ${path}`);
  return response.json();
}

async function apiPost(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { method: "POST", ...options });
  if (!response.ok) throw new Error(`Request failed: ${path}`);
  return response.json();
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function openSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const toggle = document.getElementById("sidebarToggle");
  if (!sidebar || !overlay || !toggle) return;
  sidebar.classList.add("open");
  overlay.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  document.body.classList.add("sidebar-open");
}

function closeSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const toggle = document.getElementById("sidebarToggle");
  if (!sidebar || !overlay || !toggle) return;
  sidebar.classList.remove("open");
  overlay.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
  document.body.classList.remove("sidebar-open");
}

function setupMobileSidebar() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const toggle = document.getElementById("sidebarToggle");
  if (!sidebar || !overlay || !toggle) return;

  toggle.addEventListener("click", () => {
    if (sidebar.classList.contains("open")) closeSidebar();
    else openSidebar();
  });

  overlay.addEventListener("click", closeSidebar);

  document.querySelectorAll(".sidebar-nav a").forEach((link) => {
    link.addEventListener("click", () => {
      if (window.matchMedia("(max-width: 900px)").matches) closeSidebar();
    });
  });

  window.addEventListener("resize", () => {
    if (!window.matchMedia("(max-width: 900px)").matches) closeSidebar();
  });
}

function titleCase(value) {
  return String(value || "")
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

async function refreshShellDeviceStatus() {
  try {
    const status = await apiGet("/device-status");
    if (!status) return;
    const bleStatus = titleCase(status.ble_status || "Connected");
    setText("deviceOnlineLabel", titleCase(status.online || "online"));
    setText("sensorStateLabel", titleCase(status.sensor_status || "active"));
    setText("oledStateLabel", titleCase(status.oled_status || "active"));
    setText("sidebarBuzzerLabel", String(status.buzzer_status || "OFF").toUpperCase());
    setText("sidebarBluetoothLabel", bleStatus);
    setText("mobileBluetoothLabel", bleStatus === "Connected" ? "BLE On" : "BLE Off");
    setText("lastSeenLabel", status.last_seen ? "Recently" : "Waiting");
  } catch (error) {
    console.warn("Shell device status unavailable", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setupMobileSidebar();
  refreshShellDeviceStatus();
  setInterval(refreshShellDeviceStatus, 30000);
});
