async function refreshDashboard() {
  try {
    const [latest, recent, status] = await Promise.all([
      apiGet("/readings/latest"),
      apiGet("/readings/recent?limit=10"),
      apiGet("/device-status"),
    ]);

    document.getElementById("uvIndexValue").textContent = latest ? latest.uv_index : "-";
    document.getElementById("riskLevelValue").textContent = latest ? latest.risk_level : "-";
    document.getElementById("deviceStatus").textContent = status.online;

    const body = document.getElementById("recentReadingsBody");
    body.innerHTML = recent
      .map(
        (r) => `<tr>
          <td>${formatDateTime(r.timestamp)}</td>
          <td>${r.uv_index}</td>
          <td>${riskBadge(r.risk_level)}</td>
          <td>${r.wifi_signal ?? "-"}</td>
          <td>${r.source}</td>
        </tr>`
      )
      .join("");
  } catch (error) {
    console.error("Dashboard refresh failed", error);
  }
}

refreshDashboard();
setInterval(refreshDashboard, 5000);
