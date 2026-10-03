"use strict";

const $ = (selector) => document.querySelector(selector);

const state = {
  token: null,
  username: null,
  role: null,
  socket: null,
  retryTimer: null,
  socketGeneration: 0,
};

// --- Session (sessionStorage : effacée à la fermeture de l'onglet) ----------

function saveSession() {
  try {
    sessionStorage.setItem("session", JSON.stringify({
      token: state.token, username: state.username, role: state.role,
    }));
  } catch (_) { /* stockage indisponible : la session reste en mémoire */ }
}

function loadSession() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("session") || "null");
    if (saved && saved.token) Object.assign(state, saved);
  } catch (_) { /* ignoré */ }
}

function clearSession() {
  try { sessionStorage.removeItem("session"); } catch (_) { /* ignoré */ }
  state.token = state.username = state.role = null;
}

// --- Utilitaires -------------------------------------------------------------

function showError(element, message) {
  element.textContent = message || "";
  element.hidden = !message;
}

async function errorMessage(response) {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") return data.detail;
  } catch (_) { /* corps non JSON */ }
  return `Erreur ${response.status}`;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
}

function toast(message) {
  const item = document.createElement("li");
  item.textContent = message;          // textContent : jamais d'HTML injecté
  $("#toasts").appendChild(item);
  setTimeout(() => item.remove(), 4000);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${state.token}`);
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    logout("Session expirée, reconnectez-vous.");
    throw new Error("401");
  }
  return response;
}

async function refreshUsers() {
  if (state.role !== "admin") return;
  const response = await api("/users");
  if (!response.ok) return showError($("#app-error"), await errorMessage(response));
  const list = $("#users-list");
  list.replaceChildren();
  for (const user of await response.json()) {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = user.username;
    const role = document.createElement("span");
    role.className = "role-badge";
    role.textContent = user.role === "admin" ? "Administrateur" : "Utilisateur";
    item.append(name, role);
    list.appendChild(item);
  }
}

function openDialog(id) {
  document.getElementById(id).showModal();
}

function closeDialog(id) {
  document.getElementById(id).close();
}

async function createUser(event) {
  event.preventDefault();
  showError($("#user-error"), "");
  const response = await api("/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: $("#new-username").value.trim(),
      password: $("#new-password").value,
      role: $("#new-role").value,
    }),
  });
  if (!response.ok) return showError($("#user-error"), await errorMessage(response));
  event.target.reset();
  await refreshUsers();
  closeDialog("user-dialog");
  toast("Compte créé avec succès.");
}

// --- Affichage ---------------------------------------------------------------

function showView() {
  $("#whoami").textContent = `${state.username} (${state.role})`;
  $("#admin-panel").hidden = state.role !== "admin";
  $("#users-nav").hidden = state.role !== "admin";
  $("#welcome-name").textContent = state.username;
}

function canDelete(file) {
  return state.role === "admin" || file.owner === state.username;
}

function renderFiles(files) {
  const body = $("#files");
  body.replaceChildren();
  $("#empty").hidden = files.length > 0;
  $("#file-count").textContent = files.length;
  $("#storage-used").textContent = formatSize(files.reduce((total, file) => total + file.size, 0));

  for (const file of files) {
    const row = document.createElement("tr");
    const cells = [
      file.name,
      formatSize(file.size),
      new Date(file.modified).toLocaleString("fr-FR"),
      file.owner || "—",
    ];
    for (const text of cells) {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.appendChild(cell);
    }

    const actions = document.createElement("td");
    actions.className = "actions";

    const download = document.createElement("button");
    download.type = "button";
    download.className = "secondary";
    download.textContent = "Télécharger";
    download.addEventListener("click", () => downloadFile(file.name));
    actions.appendChild(download);

    if (canDelete(file)) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "danger";
      remove.textContent = "Supprimer";
      remove.addEventListener("click", () => deleteFile(file.name));
      actions.appendChild(remove);
    }

    row.appendChild(actions);
    body.appendChild(row);
  }
}

// --- Actions -----------------------------------------------------------------

async function refreshFiles() {
  try {
    const response = await api("/files");
    if (!response.ok) {
      showError($("#app-error"), await errorMessage(response));
      return false;
    }
    showError($("#app-error"), "");
    renderFiles(await response.json());
    return true;
  } catch (_) {
    return false; // 401 déjà géré, ou réseau coupé
  }
}

async function downloadFile(name) {
  try {
    const response = await api(`/files/${encodeURIComponent(name)}`);
    if (!response.ok) return showError($("#app-error"), await errorMessage(response));
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  } catch (_) { /* ignoré */ }
}

async function deleteFile(name) {
  if (!confirm(`Supprimer « ${name} » ?`)) return;
  try {
    const response = await api(`/files/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (!response.ok) return showError($("#app-error"), await errorMessage(response));
    await refreshFiles();
  } catch (_) { /* ignoré */ }
}

async function uploadFile(event) {
  event.preventDefault();
  const input = $("#file-input");
  if (!input.files.length) return;
  const form = new FormData();
  form.append("file", input.files[0]);
  try {
    const response = await api("/files", { method: "POST", body: form });
    if (!response.ok) return showError($("#app-error"), await errorMessage(response));
    showError($("#app-error"), "");
    input.value = "";
    closeDialog("upload-dialog");
    await refreshFiles();
  } catch (_) { /* ignoré */ }
}

function logout() {
  stopSocket();
  clearSession();
  window.location.assign("/");
}

// --- WebSocket ----------------------------------------------------------------

function setLive(online) {
  const badge = $("#live");
  badge.textContent = online ? "en direct" : "hors ligne";
  badge.classList.toggle("off", !online);
}

function describe(event) {
  const verb = event.event === "uploaded" ? "a ajouté" : "a supprimé";
  return `${event.user} ${verb} ${event.file}`;
}

function connectSocket() {
  if (!state.token) return;
  if (state.socket && (
    state.socket.readyState === WebSocket.OPEN ||
    state.socket.readyState === WebSocket.CONNECTING
  )) return;

  const generation = ++state.socketGeneration;
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(
    `${scheme}://${location.host}/ws?token=${encodeURIComponent(state.token)}`
  );
  state.socket = socket;

  socket.addEventListener("open", () => setLive(true));
  socket.addEventListener("message", (message) => {
    try {
      toast(describe(JSON.parse(message.data)));
    } catch (_) { /* message inattendu */ }
    refreshFiles();                      // la liste se met à jour toute seule
  });
  socket.addEventListener("close", (event) => {
    setLive(false);
    if (state.socket === socket) state.socket = null;
    if (event.code === 1008 && state.token) {
      logout("Session expirée, reconnectez-vous.");
      return;
    }
    if (generation === state.socketGeneration && state.token) {
      state.retryTimer = setTimeout(connectSocket, 3000);   // reconnexion
    }
  });
}

function stopSocket() {
  clearTimeout(state.retryTimer);
  state.retryTimer = null;
  state.socketGeneration += 1;
  const socket = state.socket;
  state.socket = null;
  if (socket && socket.readyState < WebSocket.CLOSING) {
    socket.close(1000, "Session terminée");
  }
  setLive(false);
}

// --- Démarrage -----------------------------------------------------------------

async function start() {
  stopSocket();
  showView();
  const sessionValid = await refreshFiles();
  if (!sessionValid || !state.token) return;
  await refreshUsers();
  if (!state.token) return;
  connectSocket();
}

$("#upload-form").addEventListener("submit", uploadFile);
$("#user-form").addEventListener("submit", createUser);
$("#logout").addEventListener("click", () => logout());
$("#open-upload").addEventListener("click", () => openDialog("upload-dialog"));
$("#open-upload-dashboard").addEventListener("click", () => openDialog("upload-dialog"));
$("#open-upload-quick").addEventListener("click", () => openDialog("upload-dialog"));
$("#open-user").addEventListener("click", () => openDialog("user-dialog"));
document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => closeDialog(button.dataset.close));
});
document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".view-section").forEach((section) => {
      section.hidden = section.id !== button.dataset.view;
    });
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item === button));
    $("#view-title").textContent = button.textContent.trim();
  });
});

loadSession();
if (state.token) {
  start();
} else {
  window.location.replace("/");
}
