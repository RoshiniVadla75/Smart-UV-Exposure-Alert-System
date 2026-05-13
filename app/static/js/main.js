const API_BASE = "/api";

function formatDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatLux(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numericValue = Number(value);
  if (Number.isNaN(numericValue)) return "-";
  return `${numericValue.toLocaleString(undefined, { maximumFractionDigits: 2 })} lx`;
}

function escapeHtml(value) {
  return String(value ?? "-")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function lightLevelBadge(level) {
  const classes = {
    "Too Dark": "badge-too-dark",
    Dim: "badge-dim",
    Ideal: "badge-ideal",
    Bright: "badge-bright",
    "Very Bright": "badge-very-bright",
  };
  const className = classes[level] || "badge-neutral";
  return `<span class="badge ${className}">${escapeHtml(level)}</span>`;
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`Request failed: ${path}`);
  return response.json();
}

async function apiPost(path) {
  const response = await fetch(`${API_BASE}${path}`, { method: "POST" });
  if (!response.ok) throw new Error(`Request failed: ${path}`);
  return response.json();
}

document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  document.querySelectorAll(".header nav a").forEach((link) => {
    const href = link.getAttribute("href");
    if (
      href === path ||
      (href !== "/" && path.startsWith(href)) ||
      (href === "/" && path === "/")
    ) {
      link.style.background = "rgba(255,255,255,0.16)";
      link.style.color = "#ffffff";
    }
  });
});
