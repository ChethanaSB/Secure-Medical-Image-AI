/* ─── New Patient page logic ────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  requireAuth();
  populateNav();
  revealAdminLinks();
});

/* ── Admin-only UI ─────────────────────────────────────── */
function revealAdminLinks() {
  const u = getUser();
  if (u.role === 'admin') {
    document.getElementById('nav-dashboard-link')?.classList.remove('hidden');
  }
}

/* ── Submit ────────────────────────────────────────────── */
window.submitNewPatient = async function (e) {
  e.preventDefault();
  
  const nameInput = document.getElementById('patient-name');
  const dobInput = document.getElementById('patient-dob');
  const genderInput = document.getElementById('patient-gender');
  const contactInput = document.getElementById('patient-contact');
  
  const name = nameInput.value.trim();
  const dob = dobInput.value;
  const gender = genderInput.value;
  const contact = contactInput.value.trim();
  
  if (!name || !dob || !gender) {
    showAlert('danger', 'Please fill in all required fields.');
    return;
  }
  
  setLoading(true);
  hideAlert();
  
  const payload = {
    name: name,
    dob: dob,
    gender: gender,
    contact_number: contact || null
  };
  
  try {
    const res = await apiPost('/patients', payload);
    const data = await res.json();
    
    if (res.ok && data.patient) {
      showAlert('success', `✓ Patient ${data.patient.name} registered successfully. Redirecting…`);
      setTimeout(() => {
        window.location.href = `upload.html?new_patient_id=${data.patient.patient_id}`;
      }, 1500);
    } else {
      showAlert('danger', data.error || 'Failed to create patient. Please try again.');
    }
  } catch (err) {
    showAlert('danger', 'Network error. Make sure the backend service is running.');
  } finally {
    setLoading(false);
  }
};

/* ── Helpers ───────────────────────────────────────────── */
function setLoading(on) {
  const btn = document.getElementById('save-btn');
  btn.disabled = on;
  document.getElementById('save-btn-text').textContent = on ? 'Registering…' : 'Create Patient';
  document.getElementById('save-spinner').classList.toggle('hidden', !on);
}

function showAlert(type, msg) {
  const box = document.getElementById('form-alert');
  box.className = `alert alert-${type}`;
  box.innerHTML = `<span>${type === 'danger' ? '⚠' : '✓'}</span><span>${msg}</span>`;
  box.classList.remove('hidden');
}

function hideAlert() {
  const box = document.getElementById('form-alert');
  if (box) box.classList.add('hidden');
}
