requireAuth();

document.getElementById("logout-btn").addEventListener("click", () => {
  API.clearToken();
  window.location.href = "/login.html";
});

let devices = [];
let availChart, latChart;

function getParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function init() {
  devices = await API.get("/api/monitoring/status");
  const select = document.getElementById("device-select");
  select.innerHTML = devices
    .map((d) => `<option value="${d.id}">${d.name} (${d.ip})</option>`)
    .join("");

  const initialId = getParam("id") || (devices[0] && devices[0].id);
  if (initialId) {
    select.value = initialId;
    await loadDevice();
  }

  select.addEventListener("change", loadDevice);
  document.getElementById("days-select").addEventListener("change", loadDevice);
}

async function loadDevice() {
  const id = document.getElementById("device-select").value;
  const days = document.getElementById("days-select").value;
  if (!id) return;

  const d = devices.find((x) => String(x.id) === String(id));
  document.getElementById("device-info").innerHTML = d
    ? `<b>${d.name}</b> — IP <span class="mono">${d.ip}</span> ${d.location ? "— " + d.location : ""} · Disponibilidade 24h: <b>${d.availability_24h_pct ?? "-"}%</b>`
    : "";

  const points = await API.get(`/api/monitoring/devices/${id}/availability?days=${days}`);
  const labels = points.map((p) =>
    new Date(p.period_start + "Z").toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit" })
  );
  const availData = points.map((p) => p.availability_pct);
  const latData = points.map((p) => p.avg_rtt_ms);

  if (availChart) availChart.destroy();
  if (latChart) latChart.destroy();

  const ctx1 = document.getElementById("chart-availability").getContext("2d");
  availChart = new Chart(ctx1, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Disponibilidade (%)",
          data: availData,
          borderColor: "#16a34a",
          backgroundColor: "rgba(22,163,74,0.1)",
          fill: true,
          tension: 0.2,
          pointRadius: 0,
        },
      ],
    },
    options: {
      scales: { y: { min: 0, max: 100 } },
      plugins: { legend: { display: false } },
    },
  });

  const ctx2 = document.getElementById("chart-latency").getContext("2d");
  latChart = new Chart(ctx2, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Latência média (ms)",
          data: latData,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37,99,235,0.1)",
          fill: true,
          tension: 0.2,
          pointRadius: 0,
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
    },
  });
}

init();
