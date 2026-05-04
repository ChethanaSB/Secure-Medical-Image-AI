/**
 * viewer.js  —  Three.js Medical Image Viewer (ES Module)
 *
 * Pipeline:
 *   1. Auth-guard + parse ?image_id from URL
 *   2. Call GET /images/view/<id>  (decrypt + AI analysis on backend)
 *   3. Load base64 image as Three.js texture on a PlaneGeometry
 *   4. OrbitControls: drag-to-rotate, scroll-to-zoom, right-click-to-pan
 *   5. Toolbar: reset, zoom ±, wireframe, auto-rotate toggle
 *   6. Right panel: integrity badge, confidence bar, Claude report
 *   7. "Re-run Prediction" calls endpoint with ?force_reanalyze=true
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/* ── Auth ──────────────────────────────────────────────── */
const TOKEN = localStorage.getItem('jwt_token');
const USER  = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } })();
const API   = 'http://localhost:5000';

if (!TOKEN) window.location.href = 'index.html';

/* Nav */
const $  = (id) => document.getElementById(id);
if ($('nav-avatar'))   $('nav-avatar').textContent  = (USER.username || '?').charAt(0).toUpperCase();
if ($('nav-username')) $('nav-username').textContent = USER.username || '—';
if ($('nav-role'))     $('nav-role').textContent     = USER.role     || '—';

/* image_id from URL */
const imageId = new URLSearchParams(window.location.search).get('image_id');
if (!imageId) showPanelState('error', 'No image_id in URL. Go back and upload an image.');

/* ── Three.js setup ────────────────────────────────────── */
const canvas      = $('three-canvas');
const canvasPanel = canvas.parentElement;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping        = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.shadowMap.enabled  = true;
renderer.shadowMap.type     = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x020812);
scene.fog        = new THREE.FogExp2(0x020812, 0.06);

/* Camera */
const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 100);
camera.position.set(0, 0, 3.8);

/* Controls */
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping    = true;
controls.dampingFactor    = 0.065;
controls.minDistance      = 0.4;
controls.maxDistance      = 12;
controls.autoRotate       = true;
controls.autoRotateSpeed  = 0.5;

renderer.domElement.addEventListener('pointerdown', () => {
  controls.autoRotate = false;
  $('btn-autorotate').classList.remove('on');
});

/* Lights */
const ambient = new THREE.AmbientLight(0x182848, 2.2);
scene.add(ambient);

const keyLight = new THREE.DirectionalLight(0x40c8ff, 2.8);
keyLight.position.set(2.5, 3, 5);
keyLight.castShadow = true;
keyLight.shadow.mapSize.width = keyLight.shadow.mapSize.height = 1024;
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0x0048b0, 0.9);
fillLight.position.set(-3, -1, 1.5);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0x00aaff, 0.55);
rimLight.position.set(0, -4, -2);
scene.add(rimLight);

/* Grid floor */
const grid = new THREE.GridHelper(40, 48, 0x0a1c3c, 0x060e20);
grid.position.y = -2.4;
scene.add(grid);

/* ── Image plane ───────────────────────────────────────── */
let plane    = null;
let edgeMesh = null;
let texture  = null;

function buildPlane(tex) {
  if (plane) { scene.remove(plane); plane.geometry.dispose(); plane.material.dispose(); }
  if (edgeMesh) { scene.remove(edgeMesh); edgeMesh.geometry.dispose(); edgeMesh.material.dispose(); }

  const aspect = tex.image.height / tex.image.width;
  const W = 3.0, H = W * aspect;

  const geo = new THREE.PlaneGeometry(W, H, 1, 1);
  const mat = new THREE.MeshStandardMaterial({
    map: tex, roughness: 0.08, metalness: 0.04, side: THREE.FrontSide,
  });
  plane = new THREE.Mesh(geo, mat);
  plane.receiveShadow = true;
  scene.add(plane);

  /* Glowing cyan border */
  const eGeo = new THREE.EdgesGeometry(new THREE.PlaneGeometry(W + 0.025, H + 0.025));
  const eMat = new THREE.LineBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.48 });
  edgeMesh   = new THREE.LineSegments(eGeo, eMat);
  edgeMesh.position.z = -0.002;
  plane.add(edgeMesh);

  /* Subtle corner markers */
  const corners = [
    [-W / 2 - 0.04,  H / 2 + 0.04],
    [ W / 2 + 0.04,  H / 2 + 0.04],
    [-W / 2 - 0.04, -H / 2 - 0.04],
    [ W / 2 + 0.04, -H / 2 - 0.04],
  ];
  corners.forEach(([x, y]) => {
    const cGeo  = new THREE.PlaneGeometry(0.06, 0.06);
    const cMat  = new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.7 });
    const cMesh = new THREE.Mesh(cGeo, cMat);
    cMesh.position.set(x, y, 0.002);
    scene.add(cMesh);
  });
}

/* ── Resize ────────────────────────────────────────────── */
function resize() {
  const w = canvasPanel.clientWidth;
  const h = canvasPanel.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

/* ── Animate ───────────────────────────────────────────── */
(function animate() {
  requestAnimationFrame(animate);
  controls.update();

  /* Edge glow pulse */
  if (edgeMesh) {
    edgeMesh.material.opacity = 0.3 + 0.18 * Math.sin(Date.now() * 0.002);
  }

  renderer.render(scene, camera);
})();

/* ── Toolbar ───────────────────────────────────────────── */
$('btn-reset').addEventListener('click', () => {
  camera.position.set(0, 0, 3.8);
  controls.target.set(0, 0, 0);
  controls.update();
});
$('btn-zoom-in').addEventListener('click',  () => camera.position.multiplyScalar(0.82));
$('btn-zoom-out').addEventListener('click', () => camera.position.multiplyScalar(1.22));

let wireOn = false;
$('btn-wireframe').addEventListener('click', () => {
  wireOn = !wireOn;
  if (plane) plane.material.wireframe = wireOn;
  $('btn-wireframe').classList.toggle('on', wireOn);
});

$('btn-autorotate').addEventListener('click', () => {
  controls.autoRotate = !controls.autoRotate;
  $('btn-autorotate').classList.toggle('on', controls.autoRotate);
});

/* ── Panel state ───────────────────────────────────────── */
function showPanelState(state, errMsg = '') {
  $('panel-loading').classList.toggle('hidden', state !== 'loading');
  $('panel-content').classList.toggle('hidden', state !== 'content');
  $('panel-error').classList.toggle('hidden', state !== 'error');
  if (state === 'error' && errMsg) $('panel-err-msg').textContent = errMsg;
}

function setLoadingLabel(txt) { $('canvas-loading-text').textContent = txt; }

/* ── Load image + analysis ─────────────────────────────── */
async function loadView(forceReanalyze = false) {
  showPanelState('loading');
  $('canvas-loading').style.display = '';
  setLoadingLabel('Decrypting image from database…');

  const url = `${API}/images/view/${imageId}${forceReanalyze ? '?force_reanalyze=true' : ''}`;

  try {
    const res  = await fetch(url, { headers: { 'Authorization': `Bearer ${TOKEN}` } });
    const data = await res.json();

    if (res.status === 409) {
      hideCanvasLoading();
      showPanelState('error', data.detail || 'Integrity failure — image may be tampered.');
      markIntegrity(false);
      return;
    }
    if (!res.ok) {
      hideCanvasLoading();
      showPanelState('error', data.error || 'Failed to load image data.');
      return;
    }

    setLoadingLabel('Building 3D scene…');
    await injectTexture(data.image_base64, data.image_type);
    hideCanvasLoading();
    populatePanel(data);
    showPanelState('content');

  } catch (err) {
    hideCanvasLoading();
    showPanelState('error', 'Network error — is Flask running on port 5000?');
  }
}

/* Load base64 → Three.js texture */
function injectTexture(b64, imgType) {
  return new Promise((resolve, reject) => {
    const mime = imgType === 'png' ? 'image/png' : 'image/jpeg';
    const img  = new Image();
    img.onload = () => {
      if (texture) texture.dispose();
      texture = new THREE.Texture(img);
      texture.colorSpace   = THREE.SRGBColorSpace;
      texture.needsUpdate  = true;
      buildPlane(texture);
      resolve();
    };
    img.onerror = () => reject(new Error('Failed to decode image data'));
    img.src      = `data:${mime};base64,${b64}`;
  });
}

/* ── Populate right panel ──────────────────────────────── */
function populatePanel(data) {
  /* Info strip */
  $('panel-image-id').textContent   = `#${data.image_id}`;
  $('panel-image-type').textContent = (data.image_type || '').toUpperCase();

  /* Integrity */
  markIntegrity(data.integrity_verified);

  /* Prediction */
  const pred = data.prediction || {};
  $('pred-label').textContent = pred.label || 'Unknown';
  const pct = Math.round((pred.confidence || 0) * 100);
  $('pred-pct').textContent   = `${pct}%`;
  $('pred-model').textContent = pred.model_used || '—';

  /* Animate bar */
  setTimeout(() => { $('conf-fill').style.width = `${pct}%`; }, 200);

  /* Cached badge */
  $('cached-chip').classList.toggle('hidden', !data.cached_prediction);

  /* Canvas HUD */
  $('canvas-hud').innerHTML =
    `IMG #${data.image_id} · ${(data.image_type || '').toUpperCase()}<br>` +
    `<span style="color:var(--success)">✓ SHA-256 Verified</span><br>` +
    `DRAG rotate · SCROLL zoom · RIGHT-DRAG pan`;

  /* Clinical report — render markdown if marked.js loaded */
  const reportEl = $('clinical-report');
  const report   = data.clinical_report || '_No report available._';
  if (window.marked) {
    reportEl.innerHTML = window.marked.parse(report);
  } else {
    reportEl.textContent = report;
  }
}

function markIntegrity(ok) {
  const badge = $('integrity-badge');
  if (ok) {
    badge.className = 'badge badge-success';
    badge.innerHTML = '<span class="badge-dot"></span>SHA-256 Verified';
  } else {
    badge.className = 'badge badge-danger';
    badge.innerHTML = '<span class="badge-dot"></span>INTEGRITY FAILED';
  }
}

function hideCanvasLoading() { $('canvas-loading').style.display = 'none'; }

/* ── Re-run prediction ─────────────────────────────────── */
window.rerunPrediction = async () => {
  const btn = $('rerun-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>&nbsp;Re-analysing…';
  await loadView(true);
  btn.disabled = false;
  btn.innerHTML = '🔄&nbsp;&nbsp;Re-run Prediction';
};

/* ── Logout ────────────────────────────────────────────── */
window.logout = () => {
  localStorage.removeItem('jwt_token');
  localStorage.removeItem('user');
  window.location.href = 'index.html';
};

/* ── Boot ──────────────────────────────────────────────── */
if (imageId) loadView(false);
