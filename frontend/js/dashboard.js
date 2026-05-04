/* ─── Admin Dashboard Logic ──────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  requireAuth();
  const u = getUser();
  if (u.role !== 'admin') {
    showToast('error', 'Admin access required.');
    setTimeout(() => window.location.href = 'upload.html', 1500);
    return;
  }
  populateNav();
  refreshAll();
});

/* ── State ─────────────────────────────────────────────── */
let currentPage  = 1;
let totalPages   = 1;
let chartInstance = null;

const CHART_PALETTE = [
  '#00d4ff','#0091ea','#00e676','#ffaa00','#ff3d71',
  '#ce93d8','#80cbc4','#ff8a65','#a5d6a7','#90caf9',
];

/* ── Refresh all ───────────────────────────────────────── */
async function refreshAll() {
  await Promise.all([loadStats(), loadLogs(1)]);
}
window.refreshAll = refreshAll;

/* ── Stats ─────────────────────────────────────────────── */
async function loadStats() {
  try {
    const res  = await apiGet('/admin/dashboard');
    if (!res.ok) { showToast('error', 'Failed to load stats.'); return; }
    const data = await res.json();

    $id('stat-total').textContent  = fmt(data.total_logs);
    $id('stat-today').textContent  = fmt(data.today_logs);
    $id('stat-users').textContent  = fmt(data.active_users_24h);
    $id('stat-alerts').textContent = fmt(data.integrity_alerts);
    $id('stat-images').textContent = fmt(data.total_images);
    $id('stat-week').textContent   = fmt(data.week_logs);

    renderChart(data.action_breakdown || {});
  } catch { showToast('error', 'Network error loading stats.'); }
}

/* ── Chart ─────────────────────────────────────────────── */
function renderChart(breakdown) {
  const labels = Object.keys(breakdown);
  const values = Object.values(breakdown);
  if (!labels.length) return;

  const ctx = $id('action-chart').getContext('2d');

  if (chartInstance) chartInstance.destroy();

  chartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: CHART_PALETTE.slice(0, labels.length).map(c => c + '99'),
        borderColor:     CHART_PALETTE.slice(0, labels.length),
        borderWidth: 1.5,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          display: false,          // legend would be too cluttered — tooltip is enough
        },
        tooltip: {
          backgroundColor: 'rgba(5,11,24,.95)',
          borderColor: 'rgba(0,212,255,.3)',
          borderWidth: 1,
          titleColor: '#00d4ff',
          bodyColor: '#8ab4d8',
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.parsed}`,
          },
        },
      },
    },
  });
}

/* ── Log table ─────────────────────────────────────────── */
async function loadLogs(page = 1) {
  currentPage = page;
  showTableLoading(true);

  const params = buildFilterParams();
  params.set('page', page);
  params.set('per_page', 25);

  try {
    const res  = await apiGet(`/admin/logs?${params}`);
    if (!res.ok) { showToast('error', 'Failed to load logs.'); return; }
    const data = await res.json();

    totalPages = data.pages || 1;
    $id('total-badge').textContent = `${fmt(data.total)} records`;
    $id('pager-info').textContent  = `Page ${data.page} of ${totalPages}`;
    $id('btn-prev').disabled       = data.page <= 1;
    $id('btn-next').disabled       = data.page >= totalPages;

    renderTable(data.logs || []);
  } catch { showToast('error', 'Network error loading logs.'); }
  finally { showTableLoading(false); }
}

function renderTable(logs) {
  const tbody  = $id('log-body');
  const empty  = $id('empty-state');
  const wrap   = $id('table-wrap');

  tbody.innerHTML = '';

  if (!logs.length) {
    wrap.style.display  = 'none';
    empty.classList.remove('hidden');
    return;
  }
  wrap.style.display = '';
  empty.classList.add('hidden');

  logs.forEach(log => {
    const tr  = document.createElement('tr');
    const ts  = new Date(log.timestamp);
    const trId = `row-${log.log_id}`;
    tr.id = trId;

    tr.innerHTML = `
      <td>
        <span class="ts-date">${ts.toLocaleDateString()}</span>
        <span class="ts-time"> ${ts.toLocaleTimeString()}</span>
      </td>
      <td>
        <span style="color:var(--text-primary);font-weight:500;">${esc(log.username || '—')}</span>
        ${log.performed_by ? `<br><span class="text-xs text-muted mono">#${log.performed_by}</span>` : ''}
      </td>
      <td>${actionBadge(log.action)}</td>
      <td>
        ${log.target_type
          ? `<span class="text-xs text-muted">${esc(log.target_type)}</span>${log.target_id ? ` <span class="mono" style="color:var(--text-secondary);">#${log.target_id}</span>` : ''}`
          : '<span class="text-muted">—</span>'}
      </td>
      <td class="mono text-xs" style="color:var(--text-muted);">${esc(log.ip_address || '—')}</td>
      <td>
        ${log.details
          ? `<button class="detail-btn" onclick="toggleDetail(${log.log_id})">View</button>`
          : '<span class="text-muted text-xs">—</span>'}
      </td>
    `;
    tbody.appendChild(tr);

    // Detail row (hidden by default)
    if (log.details) {
      const dtr = document.createElement('tr');
      dtr.id    = `detail-${log.log_id}`;
      dtr.className = 'detail-row hidden';
      dtr.innerHTML = `<td colspan="6">
        <pre class="detail-pre">${esc(JSON.stringify(JSON.parse(log.details), null, 2))}</pre>
      </td>`;
      tbody.appendChild(dtr);
    }
  });
}

window.toggleDetail = function (logId) {
  const dtr = $id(`detail-${logId}`);
  if (dtr) dtr.classList.toggle('hidden');
};

/* ── Pagination ────────────────────────────────────────── */
window.goPrev = () => { if (currentPage > 1)          loadLogs(currentPage - 1); };
window.goNext = () => { if (currentPage < totalPages) loadLogs(currentPage + 1); };

/* ── Filters ───────────────────────────────────────────── */
function buildFilterParams() {
  const p = new URLSearchParams();
  const action = $id('f-action').value;
  const userId = $id('f-user').value;
  const from   = $id('f-from').value;
  const to     = $id('f-to').value;
  if (action) p.set('action',    action);
  if (userId) p.set('user_id',   userId);
  if (from)   p.set('date_from', new Date(from).toISOString());
  if (to)     p.set('date_to',   new Date(to).toISOString());
  return p;
}

window.applyFilters = () => loadLogs(1);

window.clearFilters = () => {
  $id('f-action').value = '';
  $id('f-user').value   = '';
  $id('f-from').value   = '';
  $id('f-to').value     = '';
  loadLogs(1);
};

/* ── Export CSV ────────────────────────────────────────── */
window.exportCSV = (e) => {
  e.preventDefault();
  const params = buildFilterParams();
  const token  = getToken();
  // Trigger download via a hidden anchor (can't set auth header with href)
  fetch(`${API}/admin/logs/export?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  })
    .then(r => {
      if (!r.ok) { showToast('error', 'Export failed.'); return; }
      return r.blob();
    })
    .then(blob => {
      if (!blob) return;
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `audit_log_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast('success', 'CSV downloaded successfully.');
    })
    .catch(() => showToast('error', 'Network error during export.'));
};

/* ── UI helpers ────────────────────────────────────────── */
function showTableLoading(on) {
  $id('table-loading').style.display = on ? '' : 'none';
}

function $id(id) { return document.getElementById(id); }
function fmt(n)  { return (n ?? '—').toLocaleString(); }
function esc(s)  { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function actionBadge(action) {
  const cls = {
    login_success:          'action-login-success',
    login_failed:           'action-login-failed',
    login_locked:           'action-login-locked',
    user_registered:        'action-user',
    user_deleted:           'action-user',
    image_upload:           'action-image-upload',
    image_upload_failed:    'action-error',
    image_view:             'action-image-view',
    image_integrity_failure:'action-image-integrity',
    image_decrypt_failure:  'action-image-integrity',
    hf_analysis_failure:    'action-error',
    gemini_report_failure:  'action-error',
    prediction_created:     'action-image-view',
  }[action] || 'action-default';
  return `<span class="action-badge ${cls}">${esc(action)}</span>`;
}

/* ── Toast notification ────────────────────────────────── */
let toastContainer = null;

function showToast(type, msg) {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.className = 'toast-container';
    document.body.appendChild(toastContainer);
  }
  const el  = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
window.showToast = showToast;
