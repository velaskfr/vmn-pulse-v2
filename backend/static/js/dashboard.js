requireAuth();

let allDevices = [];
let sortKey = "name";
let sortDir = 1;
const REFRESH_MS = 15000;

const STATUS_LABEL = {
  online: "Ativo",
  warning: "Lento",
  offline: "Offline",
  unknown: "Sem dados",
};

async function loadStatus() {
  try {
    const data = await API.get("/api/monitoring/status");
    allDevices = data;
    render();
    document.getElementById("last-update").textContent =
      "Atualizado às " + new Date().toLocaleTimeString("pt-BR");
  } catch (err) {
    console.error(err);
  }
}

function applyFilter(list) {
  const q = document.getElementById("search").value.trim().toLowerCase();
  if (!q) return list;
  return list.filter((d) =>
    [d.name, d.ip, d.mac, d.location].filter(Boolean).some((f) => f.toLowerCase().includes(q))
  );
}

function applySort(list) {
  return [...list].sort((a, b) => {
    let va = a[sortKey];
    let vb = b[sortKey];
    if (va === null || va === undefined) va = -Infinity;
    if (vb === null || vb === undefined) vb = -Infinity;
    if (typeof va === "string") va = va.toLowerCase();
    if (typeof vb === "string") vb = vb.toLowerCase();
    if (va < vb) return -1 * sortDir;
    if (va > vb) return 1 * sortDir;
    return 0;
  });
}

function statusPill(status) {
  return `<span class="status-pill status-${status}"><span class="dot dot-${status}"></span>${STATUS_LABEL[status] || status}</span>`;
}

function render() {
  const filtered = applySort(applyFilter(allDevices));
  const tbody = document.getElementById("grid-body");
  const empty = document.getElementById("empty-state");

  document.getElementById("count-online").textContent = allDevices.filter((d) => d.current_status === "online").length;
  document.getElementById("count-warning").textContent = allDevices.filter((d) => d.current_status === "warning").length;
  document.getElementById("count-offline").textContent = allDevices.filter((d) => d.current_status === "offline").length;

  if (allDevices.length === 0) {
    tbody.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  tbody.innerHTML = filtered
    .map(
      (d) => `
    <tr>
      <td>${d.name}</td>
      <td class="mono">${d.ip}</td>
      <td class="mono text-muted">${d.mac || "-"}</td>
      <td>${d.location || "-"}</td>
      <td>${statusPill(d.current_status)}</td>
      <td class="mono">${d.last_rtt_ms ?? "-"}</td>
      <td class="mono">${d.avg_rtt_1h_ms ?? "-"}</td>
      <td class="mono">${d.min_rtt_1h_ms ?? "-"}</td>
      <td class="mono">${d.max_rtt_1h_ms ?? "-"}</td>
      <td class="mono">${d.avg_loss_1h_pct ?? "-"}</td>
      <td class="mono">${d.availability_24h_pct !== null && d.availability_24h_pct !== undefined ? d.availability_24h_pct + "%" : "-"}</td>
      <td class="text-muted">${timeAgo(d.last_state_change_at)}</td>
      <td class="mono">${d.current_status === "offline" ? formatDuration(d.offline_since_seconds) : "-"}</td>
      <td><button class="link-btn" onclick="openLog(${d.id}, '${d.name.replace(/'/g, "\\'")}')">Ver log</button></td>
      <td>
        <button class="btn btn-small" onclick="openEdit(${d.id})">Editar</button>
        <button class="btn btn-small btn-danger" onclick="deleteDevice(${d.id})">Excluir</button>
      </td>
    </tr>`
    )
    .join("");
}

// --- ordenação por clique no cabeçalho ---
document.querySelectorAll("th[data-key]").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (sortKey === key) sortDir *= -1;
    else {
      sortKey = key;
      sortDir = 1;
    }
    render();
  });
});

document.getElementById("search").addEventListener("input", render);

document.getElementById("logout-btn").addEventListener("click", () => {
  API.clearToken();
  window.location.href = "/login.html";
});

// --- modal de cadastro/edição ---
const deviceModal = document.getElementById("device-modal-backdrop");

function openAdd() {
  document.getElementById("device-modal-title").textContent = "Novo equipamento";
  document.getElementById("device-form").reset();
  document.getElementById("device-id").value = "";
  deviceModal.style.display = "flex";
}

function openEdit(id) {
  const d = allDevices.find((x) => x.id === id);
  if (!d) return;
  document.getElementById("device-modal-title").textContent = "Editar equipamento";
  document.getElementById("device-id").value = d.id;
  document.getElementById("device-name").value = d.name;
  document.getElementById("device-ip").value = d.ip;
  document.getElementById("device-mac").value = d.mac || "";
  document.getElementById("device-location").value = d.location || "";
  deviceModal.style.display = "flex";
}

document.getElementById("add-device-btn").addEventListener("click", openAdd);
document.getElementById("device-cancel-btn").addEventListener("click", () => (deviceModal.style.display = "none"));
document.getElementById("device-modal-close").addEventListener("click", () => (deviceModal.style.display = "none"));

document.getElementById("device-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("device-id").value;
  const payload = {
    name: document.getElementById("device-name").value.trim(),
    ip: document.getElementById("device-ip").value.trim(),
    mac: document.getElementById("device-mac").value.trim() || null,
    location: document.getElementById("device-location").value.trim() || null,
  };
  const latencyWarn = document.getElementById("device-latency-warn").value;
  const lossWarn = document.getElementById("device-loss-warn").value;
  if (latencyWarn) payload.latency_warn_ms = parseInt(latencyWarn);
  if (lossWarn) payload.loss_warn_pct = parseInt(lossWarn);

  try {
    if (id) {
      await API.put(`/api/devices/${id}`, payload);
    } else {
      await API.post("/api/devices", payload);
    }
    deviceModal.style.display = "none";
    await loadStatus();
  } catch (err) {
    alert(err.message);
  }
});

async function deleteDevice(id) {
  const d = allDevices.find((x) => x.id === id);
  if (!confirm(`Excluir "${d?.name}"? Isso apaga também o histórico de ping dele.`)) return;
  try {
    await API.del(`/api/devices/${id}`);
    await loadStatus();
  } catch (err) {
    alert(err.message);
  }
}

// --- modal de log ---
const logModal = document.getElementById("log-modal-backdrop");

async function openLog(id, name) {
  document.getElementById("log-modal-title").textContent = `Log — ${name}`;
  logModal.style.display = "flex";
  document.getElementById("tab-pings").innerHTML = "Carregando...";
  document.getElementById("tab-events").innerHTML = "Carregando...";

  try {
    const [pings, events] = await Promise.all([
      API.get(`/api/monitoring/devices/${id}/history?limit=100`),
      API.get(`/api/monitoring/devices/${id}/alerts?limit=50`),
    ]);

    document.getElementById("tab-pings").innerHTML = `
      <table class="log-table">
        <thead><tr><th>Data/hora</th><th>Status</th><th>RTT médio</th><th>Mín</th><th>Máx</th><th>Perda</th></tr></thead>
        <tbody>
          ${pings
            .map(
              (p) => `<tr>
                <td>${formatDateTime(p.timestamp)}</td>
                <td>${statusPill(p.status)}</td>
                <td class="mono">${p.rtt_avg_ms ?? "-"}</td>
                <td class="mono">${p.rtt_min_ms ?? "-"}</td>
                <td class="mono">${p.rtt_max_ms ?? "-"}</td>
                <td class="mono">${p.loss_pct}%</td>
              </tr>`
            )
            .join("") || `<tr><td colspan="6" class="text-muted">Sem registros ainda.</td></tr>`}
        </tbody>
      </table>`;

    document.getElementById("tab-events").innerHTML = `
      <table class="log-table">
        <thead><tr><th>Data/hora</th><th>De</th><th>Para</th><th>Detalhes</th></tr></thead>
        <tbody>
          ${events
            .map(
              (ev) => `<tr>
                <td>${formatDateTime(ev.timestamp)}</td>
                <td>${ev.from_status ? statusPill(ev.from_status) : "-"}</td>
                <td>${statusPill(ev.to_status)}</td>
                <td class="text-muted">${ev.message || "-"}</td>
              </tr>`
            )
            .join("") || `<tr><td colspan="4" class="text-muted">Sem mudanças de status registradas.</td></tr>`}
        </tbody>
      </table>`;
  } catch (err) {
    document.getElementById("tab-pings").innerHTML = `<p class="text-muted">Erro ao carregar: ${err.message}</p>`;
  }
}

document.getElementById("log-modal-close").addEventListener("click", () => (logModal.style.display = "none"));

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("tab-pings").style.display = tab === "pings" ? "block" : "none";
    document.getElementById("tab-events").style.display = tab === "events" ? "block" : "none";
  });
});

// --- start ---
loadStatus();
setInterval(loadStatus, REFRESH_MS);
