/* ─── Login page logic ───────────────────────────────────────────────────── */

// Already logged in → go straight to upload
if (localStorage.getItem('jwt_token')) {
  window.location.href = 'upload.html';
}

const form     = document.getElementById('login-form');
const errBox   = document.getElementById('err-box');
const errText  = document.getElementById('err-text');
const loginBtn = document.getElementById('login-btn');

function setLoading(on) {
  loginBtn.disabled = on;
  document.getElementById('btn-text').textContent    = on ? 'Signing in…' : 'Sign In';
  document.getElementById('btn-spinner').classList.toggle('hidden', !on);
}

function showErr(msg) {
  errText.textContent = msg;
  errBox.classList.remove('hidden');
}

function hideErr() {
  errBox.classList.add('hidden');
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideErr();

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  if (!username || !password) {
    showErr('Please enter both username and password.');
    return;
  }

  setLoading(true);

  try {
    const res  = await fetch('http://localhost:5000/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();

    if (res.ok) {
      localStorage.setItem('jwt_token', data.token);
      localStorage.setItem('user', JSON.stringify(data.user));
      window.location.href = 'upload.html';
    } else {
      showErr(
        res.status === 429
          ? (data.error || 'Too many attempts. Please wait.')
          : (data.error || 'Invalid username or password.')
      );
    }
  } catch {
    showErr('Cannot reach server. Make sure Flask is running on port 5000.');
  } finally {
    setLoading(false);
  }
});
