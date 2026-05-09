/* ─── Shared API helpers ─────────────────────────────────────────────────── */
const API = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://localhost:5000' : '';

const getToken  = () => localStorage.getItem('jwt_token') || '';
const getUser   = () => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } };

function logout() {
  localStorage.removeItem('jwt_token');
  localStorage.removeItem('user');
  window.location.href = 'index.html';
}

function requireAuth() {
  if (!getToken()) { window.location.href = 'index.html'; return false; }
  return true;
}

function populateNav() {
  const u = getUser();
  const displayName = u.name || u.email;
  if (!displayName) return;
  const avatar   = document.getElementById('nav-avatar');
  const nameEl   = document.getElementById('nav-username');
  const roleEl   = document.getElementById('nav-role');
  if (avatar)  avatar.textContent  = displayName.charAt(0).toUpperCase();
  if (nameEl)  nameEl.textContent  = displayName;
  if (roleEl)  roleEl.textContent  = u.role;
}

async function apiGet(path) {
  return fetch(`${API}${path}`, {
    headers: { 'Authorization': `Bearer ${getToken()}` },
  });
}

async function apiPost(path, body) {
  return fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${getToken()}` },
    body: JSON.stringify(body),
  });
}

async function apiPostForm(path, formData) {
  return fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${getToken()}` },
    body: formData,
  });
}
