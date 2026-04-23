async function loadHistory() {
  const limit = document.getElementById("limitInput").value || "50";
  try {
    const rows = await apiGet(`/readings/recent?limit=${encodeURIComponent(limit)}`);
    const body = document.getElementById("historyBody");
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td>${formatDateTime(r.timestamp)}</td>
          <td>${r.uv_index}</td>
          <td>${riskBadge(r.risk_level)}</td>
        </tr>`
      )
      .join("");
  } catch (error) {
    console.error("History load failed", error);
  }
}

document.getElementById("loadHistoryBtn").addEventListener("click", loadHistory);
loadHistory();
