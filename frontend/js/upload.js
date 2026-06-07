/* ─── Upload page logic (updated) ───────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  requireAuth();
  populateNav();
  revealAdminLinks();
  loadPatients();
  initDropZone();
});

let selectedFile  = null;
let useManualPid  = false;

/* ── Admin-only & Doctor UI ────────────────────────────── */
function revealAdminLinks() {
  const u = getUser();
  if (u.role === 'admin') {
    document.getElementById('nav-dashboard-link')?.classList.remove('hidden');
  }
  if (u.role === 'admin' || u.role === 'doctor') {
    const addLink = document.getElementById('add-patient-link');
    if (addLink) addLink.style.display = '';
  }
}

/* ── Inline New Patient Form ───────────────────────────── */
window.toggleNewPatientForm = function () {
  const form = document.getElementById('new-patient-inline');
  const btn  = document.getElementById('toggle-new-patient-btn');
  const open = form.style.display === 'none';
  form.style.display = open ? 'block' : 'none';
  btn.textContent = open ? '✕ Cancel' : '+ Add New Patient';
  if (open) document.getElementById('np-name').focus();
};

window.submitInlinePatient = async function () {
  const name    = document.getElementById('np-name').value.trim();
  const dob     = document.getElementById('np-dob').value.trim();
  const gender  = document.getElementById('np-gender').value;
  const contact = document.getElementById('np-contact').value.trim();
  const alertEl = document.getElementById('inline-patient-alert');

  const showInlineAlert = (msg) => {
    alertEl.className = 'alert alert-danger';
    alertEl.innerHTML = `<span>⚠</span><span>${msg}</span>`;
    alertEl.classList.remove('hidden');
  };

  alertEl.classList.add('hidden');

  if (!name)   { showInlineAlert('Full name is required.'); return; }
  if (!dob)    { showInlineAlert('Date of birth is required.'); return; }
  if (!gender) { showInlineAlert('Please select a gender.'); return; }

  // Loading state
  const btn = document.getElementById('create-patient-btn');
  document.getElementById('create-patient-text').textContent = 'Creating…';
  document.getElementById('create-patient-spinner').classList.remove('hidden');
  btn.disabled = true;

  try {
    const res  = await apiPost('/patients', { name, dob, gender, contact_number: contact || null });
    const data = await res.json();

    if (!res.ok) {
      showInlineAlert(data.error || 'Failed to create patient.');
      return;
    }

    // Add new patient to dropdown and auto-select
    const p   = data.patient;
    const sel = document.getElementById('patient-select');
    const opt = document.createElement('option');
    opt.value       = p.patient_id;
    opt.textContent = `#${p.patient_id} — ${p.name} (${p.gender || '?'})`;
    sel.appendChild(opt);
    sel.value = p.patient_id;
    document.getElementById('patient-hint').textContent =
      `✓ Patient "${p.name}" created and selected.`;

    // Enable upload if file already selected
    if (selectedFile) document.getElementById('upload-btn').disabled = false;

    // Reset and close the inline form
    document.getElementById('np-name').value    = '';
    document.getElementById('np-dob').value     = '';
    document.getElementById('np-gender').value  = '';
    document.getElementById('np-contact').value = '';
    alertEl.classList.add('hidden');
    document.getElementById('new-patient-inline').style.display = 'none';
    document.getElementById('toggle-new-patient-btn').textContent = '+ Add New Patient';

  } catch {
    showInlineAlert('Network error. Please try again.');
  } finally {
    document.getElementById('create-patient-text').textContent = 'Create Patient';
    document.getElementById('create-patient-spinner').classList.add('hidden');
    btn.disabled = false;
  }
};


/* ── Patient dropdown ──────────────────────────────────── */
async function loadPatients() {
  const sel      = document.getElementById('patient-select');
  const spinner  = document.getElementById('patient-load-spin');
  const hint     = document.getElementById('patient-hint');
  const fallback = document.getElementById('manual-pid-wrap');

  try {
    const res  = await apiGet('/patients?per_page=200');
    spinner.style.display = 'none';

    if (!res.ok) throw new Error(`${res.status}`);
    const data = await res.json();

    const patients = data.patients || [];

    if (!patients.length) {
      sel.innerHTML = '<option value="">No patients found — enter ID manually</option>';
      fallback.classList.remove('hidden');
      useManualPid = true;
      hint.textContent = 'No patients exist yet. Enter the patient ID manually.';
    } else {
      sel.innerHTML = '<option value="">Select a patient…</option>';
      patients.forEach(p => {
        const opt   = document.createElement('option');
        opt.value   = p.patient_id;
        opt.textContent = `#${p.patient_id} — ${p.name} (${p.gender || '?'})`;
        sel.appendChild(opt);
      });
      hint.textContent = `${patients.length} patient(s) loaded. Select one above.`;
    }

    sel.addEventListener('change', () => {
      const ok = sel.value !== '';
      if (selectedFile && ok) document.getElementById('upload-btn').disabled = false;
      else document.getElementById('upload-btn').disabled = true;
    });

  } catch (err) {
    spinner.style.display = 'none';
    sel.innerHTML = '<option value="">Could not load patients</option>';
    fallback.classList.remove('hidden');
    useManualPid = true;
    hint.textContent = 'Patient API unavailable. Enter ID manually.';
  }

  // Always attach manual input listener
  const manualInput = document.getElementById('patient-id-manual');
  if (manualInput) {
    manualInput.addEventListener('input', () => {
      const ok = manualInput.value.trim() !== '';
      if (selectedFile && ok) document.getElementById('upload-btn').disabled = false;
      else document.getElementById('upload-btn').disabled = true;
    });
  }

  // Auto-select patient from query parameter if present (e.g. redirected from patient-new.html)
  const urlParams = new URLSearchParams(window.location.search);
  const newPatId = urlParams.get('new_patient_id');
  if (newPatId) {
    if (!useManualPid) {
      sel.value = newPatId;
      const ok = sel.value !== '';
      if (selectedFile && ok) document.getElementById('upload-btn').disabled = false;
    } else {
      if (manualInput) {
        manualInput.value = newPatId;
        const ok = manualInput.value.trim() !== '';
        if (selectedFile && ok) document.getElementById('upload-btn').disabled = false;
      }
    }
  }
}

/* ── Drop zone ─────────────────────────────────────────── */
function initDropZone() {
  const zone  = document.getElementById('drop-zone');
  const input = document.getElementById('file-input');

  input.addEventListener('change', (e) => {
    if (e.target.files[0]) handleFile(e.target.files[0]);
  });

  ['dragenter','dragover'].forEach(ev =>
    zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('drag-active'); })
  );
  ['dragleave','dragend'].forEach(ev =>
    zone.addEventListener(ev, () => zone.classList.remove('drag-active'))
  );
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-active');
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
}

function handleFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  const ok  = ['jpg','jpeg','png','dcm'].includes(ext);

  if (!ok) {
    showAlert('danger', `".${ext}" is not supported. Please use JPG, PNG, or DICOM.`);
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    showAlert('danger', 'File exceeds the 50 MB limit.');
    return;
  }

  selectedFile = file;
  hideAlert();

  const wrap = document.getElementById('preview-wrap');
  const img  = document.getElementById('preview-img');
  document.getElementById('preview-filename').textContent =
    `${file.name}  ·  ${(file.size / 1024).toFixed(1)} KB`;

  if (ext !== 'dcm') {
    const reader = new FileReader();
    reader.onload = (ev) => { img.src = ev.target.result; };
    reader.readAsDataURL(file);
    img.alt = file.name;
  } else {
    img.src = '';
    img.alt = 'DICOM preview not available';
  }
  wrap.classList.remove('hidden');

  // Enable upload button only if patient also selected
  const hasPat = useManualPid
    ? !!document.getElementById('patient-id-manual').value.trim()
    : document.getElementById('patient-select').value !== '';
  document.getElementById('upload-btn').disabled = !hasPat;

  document.getElementById('drop-icon').textContent  = '✅';
  document.getElementById('drop-title').textContent = file.name;
  document.getElementById('drop-sub').textContent   = 'File ready — select patient and upload';
}

/* ── Clear ─────────────────────────────────────────────── */
window.clearForm = function () {
  selectedFile = null;
  document.getElementById('file-input').value = '';
  document.getElementById('preview-wrap').classList.add('hidden');
  document.getElementById('preview-img').src = '';
  document.getElementById('patient-select').value = '';
  document.getElementById('patient-id-manual').value = '';
  document.getElementById('upload-btn').disabled = true;
  document.getElementById('drop-icon').textContent  = '📁';
  document.getElementById('drop-title').textContent = 'Drop your image here, or click to browse';
  document.getElementById('drop-sub').textContent   = 'Supported: JPG · PNG · DICOM (.dcm) — Max 50 MB';
  hideAlert();
};

/* ── Submit ────────────────────────────────────────────── */
window.submitUpload = async function () {
  if (!selectedFile) { showAlert('danger', 'Please select a file first.'); return; }

  let pid;
  if (useManualPid) {
    const raw = document.getElementById('patient-id-manual').value.trim();
    if (!raw || isNaN(parseInt(raw, 10)) || parseInt(raw, 10) < 1) {
      showAlert('danger', 'Please enter a valid numeric patient ID.'); return;
    }
    pid = raw;
  } else {
    pid = document.getElementById('patient-select').value;
    if (!pid) { showAlert('danger', 'Please select a patient.'); return; }
  }

  setLoading(true);
  hideAlert();

  const fd = new FormData();
  fd.append('file', selectedFile);
  fd.append('patient_id', pid);

  try {
    const res  = await apiPostForm('/images/upload', fd);
    const data = await res.json();

    if (res.status === 413) {
      showAlert('danger', 'File too large. Maximum is 50 MB.');
    } else if (res.status === 404) {
      showAlert('danger', `Patient #${pid} not found. Please verify the patient exists.`);
    } else if (res.ok && data.image) {
      showAlert('success', `✓ Encrypted & stored — Image #${data.image.image_id}. Redirecting to viewer…`);
      setTimeout(() => {
        window.location.href = `viewer.html?image_id=${data.image.image_id}`;
      }, 1300);
    } else {
      showAlert('danger', data.error || 'Upload failed. Check your inputs and try again.');
    }
  } catch {
    showAlert('danger', 'Network error. Make sure the Flask backend is running on port 5000.');
  } finally {
    setLoading(false);
  }
};

/* ── Helpers ───────────────────────────────────────────── */
function setLoading(on) {
  const btn = document.getElementById('upload-btn');
  btn.disabled = on;
  document.getElementById('upload-btn-text').textContent = on ? 'Encrypting…' : 'Upload & Encrypt';
  document.getElementById('upload-spinner').classList.toggle('hidden', !on);
}

function showAlert(type, msg) {
  const box = document.getElementById('upload-alert');
  box.className = `alert alert-${type}`;
  box.innerHTML  = `<span>${type === 'danger' ? '⚠' : '✓'}</span><span>${msg}</span>`;
  box.classList.remove('hidden');
}

function hideAlert() {
  document.getElementById('upload-alert').classList.add('hidden');
}
