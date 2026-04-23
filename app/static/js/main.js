const API_BASE = "/api";

function formatDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function riskBadge(risk) {
  if (risk === "Low") return '<span class="badge badge-low">Low</span>';
  if (risk === "Moderate") return '<span class="badge badge-moderate">Moderate</span>';
  return '<span class="badge badge-high">High</span>';
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
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
