async function refreshAlerts() {
  try {
    const alerts = await apiGet("/alerts");
    const body = document.getElementById("alertsBody");
    body.innerHTML = alerts
      .map(
        (a) => `<tr>
          <td>${formatDateTime(a.timestamp)}</td>
          <td>${a.uv_index}</td>
          <td>${riskBadge(a.risk_level)}</td>
          <td>${a.message}</td>
        </tr>`
      )
      .join("");
  } catch (error) {
    console.error("Alerts refresh failed", error);
  }
}

refreshAlerts();
setInterval(refreshAlerts, 5000);
