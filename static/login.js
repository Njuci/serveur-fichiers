"use strict";

const $ = (selector) => document.querySelector(selector);

function showError(message) {
  const element = $("#login-error");
  element.textContent = message || "";
  element.hidden = !message;
}

async function errorMessage(response) {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") return data.detail;
  } catch (_) { /* réponse non JSON */ }
  return `Erreur ${response.status}`;
}

function saveSession(data) {
  sessionStorage.setItem("session", JSON.stringify({
    token: data.access_token,
    username: data.username,
    role: data.role,
  }));
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  try {
    const response = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#username").value.trim(),
        password: $("#password").value,
      }),
    });
    if (!response.ok) {
      showError(await errorMessage(response));
      return;
    }
    saveSession(await response.json());
    window.location.assign("/app");
  } catch (_) {
    showError("Le serveur est inaccessible. Réessayez.");
  }
});

try {
  const session = JSON.parse(sessionStorage.getItem("session") || "null");
  if (session && session.token) window.location.replace("/app");
} catch (_) { /* session absente ou invalide */ }
