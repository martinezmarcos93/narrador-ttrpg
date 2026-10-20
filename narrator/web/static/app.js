"use strict";
// Cliente mínimo de la API v1: crea sesión, envía turnos por SSE y muestra el mundo.
const $ = (id) => document.getElementById(id);
let sessionId = null;

function headers() {
  const h = { "Content-Type": "application/json" };
  const key = $("api-key").value.trim();
  if (key) h.Authorization = `Bearer ${key}`;
  return h;
}

function showError(message) { $("error").textContent = message || ""; }

function addLine(text, cls) {
  const li = document.createElement("li");
  li.className = cls;
  li.textContent = text;
  $("log").appendChild(li);
  li.scrollIntoView({ block: "end" });
  return li;
}

async function api(path, body, method = "POST") {
  const res = await fetch(path, { method, headers: headers(), body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error ? data.error.message : `HTTP ${res.status}`);
  return data;
}

$("session-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  showError("");
  try {
    const data = await api("/api/v1/sessions", { campaign: $("campaign").value, system: $("system").value });
    sessionId = data.session_id;
    $("session-status").textContent = `${data.campaign} · ${data.system}`;
    for (const id of ["action", "send", "world-btn"]) $(id).disabled = false;
    $("action").focus();
  } catch (err) { showError(err.message); }
});

$("world-btn").addEventListener("click", async () => {
  try {
    const res = await fetch(`/api/v1/sessions/${sessionId}/world`, { headers: headers() });
    const data = await res.json();
    $("world").textContent = data.status || "(sin novedades)";
  } catch (err) { showError(err.message); }
});

$("turn-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("action").value.trim();
  if (!text || !sessionId) return;
  showError("");
  addLine(text, "user");
  $("action").value = "";
  $("send").disabled = true;
  const out = addLine("…", "narrator");
  let streamed = "";
  try {
    const res = await fetch("/api/v1/turns/stream", {
      method: "POST", headers: headers(), body: JSON.stringify({ session_id: sessionId, text }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const event = /event: (\w+)/.exec(block);
        const data = /data: (.*)/s.exec(block);
        if (!event || !data) continue;
        const payload = JSON.parse(data[1]);
        if (event[1] === "chunk") { streamed += payload.text; out.textContent = streamed; }
        if (event[1] === "done") { out.textContent = payload.text; }
        if (event[1] === "error") { showError("El turno falló; revisá los logs del servidor."); }
      }
    }
  } catch (err) {
    showError(err.message);
  } finally {
    $("send").disabled = false;
    $("action").focus();
  }
});
