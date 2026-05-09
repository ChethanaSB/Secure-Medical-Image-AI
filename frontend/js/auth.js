/* ─── Auth page logic — Login + Register (Supabase-backed) ──────────────── */

// Already logged in → go straight to upload
if (localStorage.getItem('jwt_token')) {
  window.location.href = 'upload.html';
}

const API_BASE = 'http://localhost:5000';

// ── Tab switching ────────────────────────────────────────────────────────────

const tabs      = document.querySelectorAll('.auth-tab');
const panels    = document.querySelectorAll('.auth-panel');

function switchTab(tabName) {
  tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
  panels.forEach(p => p.classList.toggle('active', p.id === `panel-${tabName}`));
  // Clear errors
  hideErr('login');
  hideErr('reg');
}

tabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));
document.getElementById('switch-to-register')?.addEventListener('click', (e) => { e.preventDefault(); switchTab('register'); });
document.getElementById('switch-to-login')?.addEventListener('click', (e) => { e.preventDefault(); switchTab('login'); });
document.getElementById('go-to-login-btn')?.addEventListener('click', () => {
  switchTab('login');
  document.getElementById('register-success').classList.add('hidden');
  document.getElementById('register-form').classList.remove('hidden');
});


// ── Error helpers ────────────────────────────────────────────────────────────

function showErr(prefix, msg) {
  const box = document.getElementById(`${prefix}-err-box`);
  const txt = document.getElementById(`${prefix}-err-text`);
  if (box && txt) { txt.textContent = msg; box.classList.remove('hidden'); }
}

function hideErr(prefix) {
  const box = document.getElementById(`${prefix}-err-box`);
  if (box) box.classList.add('hidden');
}

function setLoading(prefix, on) {
  const btn    = document.getElementById(`${prefix}-btn`);
  const text   = document.getElementById(`${prefix}-btn-text`);
  const spin   = document.getElementById(`${prefix}-btn-spinner`);
  if (btn)  btn.disabled = on;
  if (text) text.textContent = on
    ? (prefix === 'login' ? 'Signing in…' : 'Creating account…')
    : (prefix === 'login' ? 'Sign In' : 'Create Account');
  if (spin) spin.classList.toggle('hidden', !on);
}


// ── LOGIN ────────────────────────────────────────────────────────────────────

const loginForm = document.getElementById('login-form');

loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideErr('login');

  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;

  if (!email || !password) {
    showErr('login', 'Please enter both email and password.');
    return;
  }

  setLoading('login', true);

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();

    if (res.ok) {
      localStorage.setItem('jwt_token', data.token);
      localStorage.setItem('user', JSON.stringify(data.user));
      window.location.href = 'upload.html';
    } else {
      showErr('login', data.error || 'Invalid email or password.');
    }
  } catch {
    showErr('login', 'Cannot reach server. Make sure Flask is running on port 5000.');
  } finally {
    setLoading('login', false);
  }
});


// ── REGISTER ─────────────────────────────────────────────────────────────────

const registerForm = document.getElementById('register-form');

// Role selector
const roleOptions = document.querySelectorAll('.role-option');
roleOptions.forEach(opt => {
  opt.addEventListener('click', () => {
    roleOptions.forEach(o => o.classList.remove('selected'));
    opt.classList.add('selected');
  });
});

// Password strength
const regPw      = document.getElementById('reg-password');
const pwFill     = document.getElementById('pw-strength-fill');

regPw.addEventListener('input', () => {
  const pw = regPw.value;
  pwFill.className = 'pw-strength-fill';
  if (pw.length >= 10 && /[A-Z]/.test(pw) && /[0-9]/.test(pw) && /[^a-zA-Z0-9]/.test(pw)) {
    pwFill.classList.add('strong');
  } else if (pw.length >= 6) {
    pwFill.classList.add('medium');
  } else if (pw.length > 0) {
    pwFill.classList.add('weak');
  }
});

registerForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideErr('reg');

  const name     = document.getElementById('reg-name').value.trim();
  const email    = document.getElementById('reg-email').value.trim();
  const phone    = document.getElementById('reg-phone').value.trim();
  const password = document.getElementById('reg-password').value;
  const role     = document.querySelector('input[name="role"]:checked')?.value || 'doctor';

  // Validation
  if (!name)     { showErr('reg', 'Name is required.'); return; }
  if (!email)    { showErr('reg', 'Email is required.'); return; }
  if (!phone)    { showErr('reg', 'Phone number is required.'); return; }
  if (!password) { showErr('reg', 'Password is required.'); return; }
  if (name.length < 2) { showErr('reg', 'Name must be at least 2 characters.'); return; }
  if (password.length < 6) { showErr('reg', 'Password must be at least 6 characters.'); return; }
  if (phone.length < 10)   { showErr('reg', 'Enter a valid phone number (min 10 digits).'); return; }

  const fullPhone = document.getElementById('reg-phone-prefix').value + phone;

  setLoading('reg', true);

  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password, phone: fullPhone, role }),
    });
    const data = await res.json();

    if (res.ok) {
      // Show success state
      registerForm.classList.add('hidden');
      document.getElementById('register-success').classList.remove('hidden');
    } else {
      showErr('reg', data.error || 'Registration failed. Please try again.');
    }
  } catch {
    showErr('reg', 'Cannot reach server. Make sure Flask is running on port 5000.');
  } finally {
    setLoading('reg', false);
  }
});
