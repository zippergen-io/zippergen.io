// The preview changes only simulated shell state. Live decisions arrive only from the API.
let apiBase = null;
let liveToken = null;
let telegramUrl = null;
let pollTimer;
let requestGeneration = 0;
let liveBusy = false;
let liveState = null;
const liveDialog = document.querySelector('#live-dialog');
const liveStatus = document.querySelector('#live-status');
const liveLink = document.querySelector('#telegram-link');
const liveDetails = document.querySelector('#live-details');
const liveKey = 'zippergen-live-demo-v1';
const qrDetails = document.querySelector('#telegram-qr');
const qrCanvas = document.querySelector('#telegram-qr-code');
const qrHelp = document.querySelector('#telegram-qr-help');
let qrUrl = null;

function clearQR() {
  qrDetails.hidden = true;
  qrDetails.open = false;
  qrCanvas.hidden = true;
  qrCanvas.width = qrCanvas.height = 0;
  qrUrl = null;
}

async function showQR() {
  if (!qrDetails.open || qrDetails.hidden || !telegramUrl) return;
  const url = telegramUrl;
  const generation = requestGeneration;
  if (qrUrl === url) return;
  qrHelp.textContent = 'Preparing the QR code…';
  try {
    const { qrcode } = await import('./vendor/qrcode-generator-2.0.4.mjs');
    if (generation !== requestGeneration || url !== telegramUrl || qrDetails.hidden || !qrDetails.open) return;
    const code = qrcode(0, 'M');
    code.addData(url, 'Byte');
    code.make();
    const modules = code.getModuleCount();
    const scale = 6;
    const margin = 4;
    qrCanvas.width = qrCanvas.height = (modules + 2 * margin) * scale;
    const context = qrCanvas.getContext('2d');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, qrCanvas.width, qrCanvas.height);
    context.fillStyle = '#000000';
    for (let row = 0; row < modules; row++) {
      for (let col = 0; col < modules; col++) {
        if (code.isDark(row, col)) context.fillRect((col + margin) * scale, (row + margin) * scale, scale, scale);
      }
    }
    qrUrl = url;
    qrCanvas.hidden = false;
    qrHelp.textContent = 'Scan with your camera, then press Start in Telegram.';
  } catch {
    if (generation !== requestGeneration || url !== telegramUrl || qrDetails.hidden || !qrDetails.open) return;
    qrHelp.textContent = 'The QR code could not load. Use the Telegram link above.';
  }
}


export function liveReview() {
  return { active: Boolean(liveToken) || liveBusy, state: liveState };
}

function changed() {
  document.dispatchEvent(new Event('live-review-change'));
}

export function resetTelegram() {
  requestGeneration++;
  clearTimeout(pollTimer);
  liveToken = telegramUrl = liveState = null;
  liveBusy = false;
  try { localStorage.removeItem(liveKey); } catch { /* Storage is optional. */ }
  const url = new URL(location.href);
  const hash = new URLSearchParams(url.hash.slice(1));
  hash.delete('live');
  url.hash = hash.toString();
  history.replaceState(null, '', url);
  liveDialog.close();
  liveLink.hidden = true;
  liveLink.removeAttribute('href');
  clearQR();
  liveStatus.textContent = liveDetails.textContent = '';
  document.querySelector('#resume-live').hidden = true;
  document.querySelector('#new-live-session').hidden = true;
  changed();
}

function remember() {
  try { localStorage.setItem(liveKey, JSON.stringify({ token: liveToken, telegramUrl })); } catch { /* The URL still restores the run. */ }
  const url = new URL(location.href);
  url.hash = new URLSearchParams({ live: liveToken }).toString();
  history.replaceState(null, '', url);
}

async function api(path, options = {}) {
  const response = await fetch(apiBase + path, { ...options, cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(12000) });
  const body = await response.json();
  if (!response.ok) throw Object.assign(new Error(body.error || 'The live demo is unavailable.'), { status: response.status });
  return body;
}

function showLive() {
  if (!liveDialog.open) liveDialog.showModal();
}

function safeTelegramLink(value) {
  try {
    const url = new URL(value);
    return url.origin === 'https://t.me' && /^\/[A-Za-z0-9_]{5,32}$/.test(url.pathname) && /^[A-Za-z0-9_-]{32}$/.test(url.searchParams.get('start')) ? url.href : null;
  } catch { return null; }
}

async function poll() {
  clearTimeout(pollTimer);
  if (!liveToken || !apiBase) return;
  const generation = requestGeneration;
  let again = true;
  try {
    const state = await api('/api/session', { headers: { Authorization: `Bearer ${liveToken}` } });
    if (generation !== requestGeneration) return;
    if (liveState !== state.state) {
      liveState = state.state;
      changed();
    }
    const expires = new Date(state.expires_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    liveDetails.textContent = `This run is kept until ${expires}. Its draft is fixed. No model is called and no email is sent.`;
    liveLink.hidden = state.state !== 'connecting' || !telegramUrl;
    if (telegramUrl) liveLink.href = telegramUrl;
    if (liveLink.hidden) clearQR();
    else qrDetails.hidden = false;
    const messages = {
      connecting: telegramUrl ? 'Open the demo bot and press Start to connect this run.' : 'Waiting for the Telegram chat connected through your original link.',
      starting: 'Connected. The workflow is preparing your approval request.',
      waiting: 'Your workflow is waiting on the demo server. You can close this page and approve from Telegram before the session expires.',
      continuing: 'Your decision is saved. The workflow is continuing on the server.',
      approved: 'Approved. The workflow released the example reply and completed.',
      rejected: 'Rejected. The workflow discarded the example reply and completed.',
      error: 'This workflow could not continue. Start over to try again.',
    };
    liveStatus.textContent = messages[state.state] || 'Checking the saved workflow state.';
    if (!state.available && !['approved', 'rejected', 'error'].includes(state.state)) {
      liveStatus.textContent += ' The Telegram connection is temporarily unavailable. The saved run will be retried.';
    }
    if (['approved', 'rejected', 'error'].includes(state.state)) again = false;
  } catch (error) {
    if (generation !== requestGeneration) return;
    if (error.status === 410) {
      liveState = 'expired';
      changed();
      liveStatus.textContent = 'This live session has expired. Start a new live session or start over.';
      liveLink.hidden = true;
      clearQR();
      liveDetails.textContent = '';
      document.querySelector('#new-live-session').hidden = false;
      again = false;
    } else {
      liveStatus.textContent = 'The server cannot be reached right now. Your last saved run may still be waiting. We will check again.';
    }
  }
  if (again && generation === requestGeneration) pollTimer = setTimeout(poll, 3000);
}

async function startLive() {
  showLive();
  if (liveBusy) return;
  if (liveToken) { await poll(); return; }
  if (!apiBase) {
    liveStatus.textContent = 'The live server is not connected to this preview yet. You can approve or reject in the simulated Telegram view.';
    return;
  }
  liveBusy = true;
  const generation = requestGeneration;
  changed();
  liveStatus.textContent = 'Creating a separate workflow on the demo server…';
  try {
    const session = await api('/api/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (generation !== requestGeneration) return;
    if (!/^[A-Za-z0-9_-]{32}$/.test(session.token)) throw new Error('Invalid session');
    liveToken = session.token;
    liveState = 'connecting';
    changed();
    telegramUrl = safeTelegramLink(session.telegram_url);
    remember();
    document.querySelector('#resume-live').hidden = false;
    await poll();
  } catch (error) {
    if (generation !== requestGeneration) return;
    liveStatus.textContent = error.status === 429 ? error.message : 'The live demo is unavailable. Please try again later or use the simulated preview.';
    document.querySelector('#new-live-session').hidden = false;
  } finally {
    if (generation === requestGeneration) { liveBusy = false; changed(); }
  }
}

export function renderTelegram(state, data, runCommand) {
  const latest = state.entries.at(-1);
  const commands = ['zg deploy tasks', 'zg deploy start', 'zg deploy approve --task 1 --yes', 'zg deploy approve --task 1 --no'];
  const visible = !state.agent && state.taskSeen && (commands.includes(latest?.command) || latest?.text.startsWith('A fresh simulation'));
  const preview = document.querySelector('#telegram-preview');
  preview.hidden = !visible;
  if (!visible) return false;
  document.querySelector('#preview-draft').textContent = data.reply;
  const decision = state.decision;
  const live = liveReview();
  preview.setAttribute('aria-label', live.active ? 'Live Telegram approval' : 'Simulated Telegram conversation');
  document.querySelector('#preview-message').textContent = decision === true ? 'Approved. The example reply was sent in the simulation.' : decision === false ? 'Rejected. No reply was sent.' : state.service === 'stopped' ? 'The service is stopped. Your approval request is saved.' : 'Send this reply?';
  if (live.active) {
    document.querySelector('#preview-message').textContent = live.state === 'approved' ? 'Approved in Telegram. The live workflow has completed.' : live.state === 'rejected' ? 'Rejected in Telegram. The live workflow has completed.' : live.state === 'expired' ? 'This live session has expired. Start over to try again.' : live.state === 'error' ? 'The live workflow could not continue. Start over to try again.' : 'This request is handled in Telegram. Open your live run to continue.';
  }
  document.querySelector('#try-live').hidden = !apiBase || live.active;
  for (const [id, yes] of [['preview-approve', true], ['preview-reject', false]]) {
    const button = document.querySelector(`#${id}`);
    button.disabled = live.active || state.service !== 'running' || decision !== null;
    button.onclick = () => runCommand(`zg deploy approve --task 1 --${yes ? 'yes' : 'no'}`);
  }
  return true;
}

export async function initTelegram() {
  qrDetails.addEventListener('toggle', showQR);
  document.querySelector('#try-live').addEventListener('click', startLive);
  document.querySelector('#resume-live').addEventListener('click', startLive);
  document.querySelector('#new-live-session').addEventListener('click', () => {
    resetTelegram();
    startLive();
  });
  try {
    const config = await (await fetch('./live-config.json', { cache: 'no-store' })).json();
    if (config.api_base) {
      const url = new URL(config.api_base, location.href);
      if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname))) throw new Error('HTTPS required');
      if (url.username || url.password || url.search || url.hash) throw new Error('Invalid API base');
      apiBase = url.href.replace(/\/$/, '');
    }
  } catch { /* The default simulated journey works without the backend. */ }
  document.querySelector('#try-live').hidden = !apiBase || liveReview().active;
  const hashToken = new URLSearchParams(location.hash.slice(1)).get('live');
  let saved;
  try { saved = JSON.parse(localStorage.getItem(liveKey)); } catch { /* Optional browser storage. */ }
  const token = hashToken || saved?.token;
  if (/^[A-Za-z0-9_-]{32}$/.test(token || '')) {
    liveToken = token;
    changed();
    telegramUrl = saved?.token === token ? safeTelegramLink(saved.telegramUrl) : null;
    document.querySelector('#resume-live').hidden = false;
    if (apiBase) {
      if (hashToken) showLive();
      poll();
    }
  }
}
