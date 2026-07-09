const API = {
  token() {
    return localStorage.getItem("nm_token");
  },
  setToken(t) {
    localStorage.setItem("nm_token", t);
  },
  clearToken() {
    localStorage.removeItem("nm_token");
  },
  async request(path, options = {}) {
    const headers = options.headers || {};
    const token = this.token();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (options.body) headers["Content-Type"] = "application/json";

    const resp = await fetch(path, { ...options, headers });

    if (resp.status === 401) {
      this.clearToken();
      window.location.href = "/login.html";
      throw new Error("Não autenticado");
    }

    if (!resp.ok) {
      let detail = "Erro na requisição";
      try {
        const data = await resp.json();
        detail = data.detail || detail;
      } catch (e) {}
      throw new Error(detail);
    }

    if (resp.status === 204) return null;
    return resp.json();
  },
  get(path) {
    return this.request(path, { method: "GET" });
  },
  post(path, body) {
    return this.request(path, { method: "POST", body: JSON.stringify(body) });
  },
  put(path, body) {
    return this.request(path, { method: "PUT", body: JSON.stringify(body) });
  },
  del(path) {
    return this.request(path, { method: "DELETE" });
  },
};

function requireAuth() {
  if (!API.token()) {
    window.location.href = "/login.html";
  }
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (d > 0) return `${d}d ${h % 24}h`;
  if (h > 0) return `${h}h ${m % 60}min`;
  return `${m}min`;
}

function timeAgo(isoString) {
  if (!isoString) return "-";
  const then = new Date(isoString + "Z");
  const seconds = Math.floor((Date.now() - then.getTime()) / 1000);
  if (seconds < 0) return "agora";
  return `há ${formatDuration(seconds)}`;
}

function formatDateTime(isoString) {
  if (!isoString) return "-";
  const d = new Date(isoString + "Z");
  return d.toLocaleString("pt-BR");
}
