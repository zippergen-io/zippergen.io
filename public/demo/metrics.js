// First-party milestone totals. Never send commands, URLs, live tokens or identities.
const events = new Set(['demo_opened', 'first_command', 'deployment_reached',
  'simulation_completed', 'telegram_requested', 'github_clicked']);
const storageKey = 'zippergen-demo-counts-v1';
const optOutKey = 'zippergen-demo-counts-off';
const lifetime = 24 * 60 * 60 * 1000;
let base = null;
let ready = false;
let optedOut = false;
let attempt;
const inFlight = new Set();
const pending = new Set();
const button = document.querySelector('#usage-counts');
try { optedOut = localStorage.getItem(optOutKey) === '1'; } catch { /* Optional preference storage. */ }

function allowed() {
  return location.origin === 'https://zippergen.io' && !navigator.webdriver &&
    navigator.doNotTrack !== '1' && navigator.globalPrivacyControl !== true && !optedOut;
}
function fresh() {
  return { id: crypto.randomUUID().replaceAll('-', ''), created: Date.now(), sent: [] };
}
function save() {
  if (!allowed()) return;
  try { sessionStorage.setItem(storageKey, JSON.stringify(attempt)); } catch { /* Deduplicate in memory. */ }
}
function current() {
  if (!attempt) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey));
      if (/^[a-f0-9]{32}$/.test(saved?.id || '') && Number.isFinite(saved.created) &&
          saved.created <= Date.now() && Date.now() - saved.created < lifetime &&
          Array.isArray(saved.sent) && saved.sent.length <= events.size && saved.sent.every(e => events.has(e))) attempt = saved;
    } catch { /* Start without a stored attempt. */ }
  }
  if (!attempt || Date.now() - attempt.created >= lifetime) {
    attempt = fresh();
    pending.add('demo_opened');
    save();
  }
  return attempt;
}
export function measurementQuery() {
  return allowed() ? '' : '?measurement=off';
}
function paint() {
  if (!button) return;
  button.textContent = `Usage counts: ${allowed() ? 'on' : 'off'}`;
  button.setAttribute('aria-pressed', String(allowed()));
}
export function count(event) {
  if (!events.has(event) || !allowed()) return;
  pending.add(event);
  if (ready) flush();
}
function flush() {
  if (!ready || !allowed()) return;
  const record = current();
  for (const event of pending) {
    if (record.sent.includes(event)) { pending.delete(event); continue; }
    const key = record.id + ':' + event;
    if (inFlight.has(key)) continue;
    inFlight.add(key);
    fetch(base + '/api/metrics', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event, attempt: record.id }), credentials: 'omit',
      referrerPolicy: 'no-referrer', keepalive: true, signal: AbortSignal.timeout(5000),
    }).then(response => {
      if (response.ok && record === attempt && allowed()) {
        record.sent.push(event);
        pending.delete(event);
        save();
      }
    }).catch(() => { /* Measurement must never interrupt the demo. */ })
      .finally(() => inFlight.delete(key));
  }
}
export function newCountedAttempt() {
  pending.clear();
  attempt = null;
  try { sessionStorage.removeItem(storageKey); } catch { /* Optional storage. */ }
  count('demo_opened');
}
export async function initMetrics(apiBase) {
  base = apiBase;
  // Local previews and automated browsers never contact the counting endpoint.
  if (location.origin !== 'https://zippergen.io' || navigator.webdriver || !base) return;
  try {
    const response = await fetch(base + '/api/config', {
      credentials: 'omit', referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(5000),
    });
    const config = await response.json();
    if (!response.ok || !config.metrics_enabled) return;
    ready = true;
    button.hidden = false;
    paint();
    count('demo_opened');
  } catch { /* The simulation works even when metrics are unavailable. */ }
}
button?.addEventListener('click', () => {
  optedOut = !optedOut;
  try {
    if (optedOut) localStorage.setItem(optOutKey, '1');
    else localStorage.removeItem(optOutKey);
  } catch { /* Apply within this page even without storage. */ }
  newCountedAttempt();
  paint();
  document.dispatchEvent(new Event('demo-measurement-change'));
});
window.addEventListener('online', flush);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
document.addEventListener('click', event => {
  const link = event.target.closest('a[href]');
  if (link && new URL(link.href).origin === 'https://github.com') count('github_clicked');
});
