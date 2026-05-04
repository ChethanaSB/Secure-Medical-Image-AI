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

/* ── Admin-only UI ─────────────────────────────────────── */
function revealAdminLinks() {
  const u = getUser();
  if (u.role === 'admin') {
    document.getElementById('nav-dashboard-link')?.classList.remove('hidden');
    const addLink = document.getElementById('add-patient-link');
    if (addLink) addLink.style.display = '';
  }
}

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
      return;
    }

    sel.innerHTML = '<option value="">Select a patient…</option>';
    patients.forEach(p => {
      const opt   = document.createElement('option');
      opt.value   = p.patient_id;
      opt.textContent = `#${p.patient_id} — ${p.name} (${p.gender || '?'})`;
      sel.appendChild(opt);
    });

    hint.textContent = `${patients.length} patient(s) loaded. Select one above.`;

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
