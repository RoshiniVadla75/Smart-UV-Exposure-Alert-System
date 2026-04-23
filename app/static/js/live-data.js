async function refreshLiveData() {
  try {
    const rows = await apiGet("/readings/recent?limit=50");
    const body = document.getElementById("liveDataBody");
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td>${formatDateTime(r.timestamp)}</td>
          <td>${r.device_id}</td>
          <td>${r.uv_index}</td>
          <td>${riskBadge(r.risk_level)}</td>
          <td>${r.wifi_signal ?? "-"}</td>
          <td>${r.source}</td>
        </tr>`
      )
      .join("");
  } catch (error) {
    console.error("Live data refresh failed", error);
  }
}

refreshLiveData();
setInterval(refreshLiveData, 5000);
