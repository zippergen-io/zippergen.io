import { renderTelegram, initTelegram, resetTelegram, liveReview } from './telegram.js';

// A finite command simulation. Nothing here invokes a shell, model, or service.
const STORAGE_KEY = 'zippergen-shell-demo-v1';
const fresh = () => ({ initialized: false, agent: null, workflow: false, inspected: false, configured: false, service: 'idle', decision: null, taskSeen: false, restarted: false, entries: [] });
let state = fresh();
let data;
const output = document.querySelector('#output');
const input = document.querySelector('#command');
const suggestions = document.querySelector('#suggestions');
const announcement = document.querySelector('#announcement');
let historyIndex = 0;

function validEntry(entry) {
  return entry && typeof entry.command === 'string' && entry.command.length < 600 &&
    ['shell', 'agent', 'user', 'note'].includes(entry.speaker) &&
    ['text', 'code', 'download'].includes(entry.kind) &&
    typeof entry.text === 'string' && entry.text.length < 30000 &&
    typeof entry.note === 'string' && entry.note.length < 600;
}
try {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
  if (saved && ['initialized', 'workflow', 'inspected', 'configured', 'taskSeen', 'restarted'].every(key => typeof saved[key] === 'boolean') &&
      [null, 'codex', 'claude'].includes(saved.agent) && ['idle', 'running', 'stopped'].includes(saved.service) && [null, true, false].includes(saved.decision) &&
      Array.isArray(saved.entries) && saved.entries.length <= 40 && saved.entries.every(validEntry) &&
      (!saved.workflow || saved.initialized) && (saved.service === 'idle' || saved.workflow) && (saved.decision === null || saved.service !== 'idle') && (!saved.agent || saved.initialized)) {
    state = saved;
  }
} catch { /* Browser storage is optional. */ }
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function save() {
  state.entries = state.entries.slice(-40);
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* Continue without persistence. */ }
}
function highlight(source) {
  const tokens = /(#.*$|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:def|if|else|while|return|is|not|None|True|False|from|import|as|with)\b|@\w+|\b\d+\b|\b[A-Za-z_]\w*(?=\())/gm;
  let result = '';
  let offset = 0;
  for (const match of source.matchAll(tokens)) {
    result += escape(source.slice(offset, match.index));
    const word = match[0];
    let kind = 'function';
    if (word.startsWith('#')) kind = 'comment';
    else if (/^["']/.test(word)) kind = 'string';
    else if (/^\d+$/.test(word)) kind = 'number';
    else if (/^(def|if|else|while|return|is|not|None|True|False|from|import|as|with)$/.test(word) || word.startsWith('@')) kind = 'keyword';
    result += `<span class="syntax-${kind}">${escape(word)}</span>`;
    offset = match.index + word.length;
  }
  return result + escape(source.slice(offset));
}
function add(command, text, { kind = 'text', note = '', speaker = 'shell' } = {}) {
  state.entries.push({ command, text, kind, note, speaker });
}
function commandButton(command, label = command, secondary = false) {
  return `<button type="button" data-command="${escape(command)}"${secondary ? ' class="secondary"' : ''}>${escape(label)}</button>`;
}
function choices() {
  if (!state.initialized) return ['Start with an empty project.', [commandButton('zg init')]];
  if (state.agent) return ['Or press Enter.', ['<button type="submit" form="agent-form">Send this request ↵</button>']];
  if (liveReview().active && state.taskSeen) return [
    ['approved', 'rejected'].includes(liveReview().state) ? 'Your Telegram decision is saved. Start over to try a new request.' : 'Continue in Telegram, or open your live run.',
    [],
  ];
  if (!state.workflow) return ['Open the coding agent you usually use.', [commandButton('codex'), commandButton('claude')]];
  if (state.service === 'stopped') return [state.decision === null ? 'The approval is saved. Start the service to continue.' : 'The service is stopped. Your decision is recorded.', [commandButton('zg deploy start'), commandButton('zg deploy tasks'), commandButton('zg deploy status')]];
  if (state.decision !== null) {
    return ['Try the project yourself, or explore what happened.', [
      '<a href="./approval-example.zip" download>Download the example</a>',
      commandButton('zg deploy logs'),
      '<button type="button" data-replay class="secondary">Try the other decision</button>',
    ]];
  }
  if (state.service === 'running') {
    if (state.taskSeen) return ['Your choice changes the outcome. You can also stop before deciding.', [commandButton('zg deploy approve --task 1 --yes'), commandButton('zg deploy approve --task 1 --no'), commandButton('zg deploy stop')]];
    return ['A request is waiting for you. Look at the pending approval.', [commandButton('zg deploy tasks'), commandButton('zg deploy stop'), commandButton('zg deploy status')]];
  }
  if (!state.inspected) return ['Read the workflow, or focus on just one participant.', [commandButton('zg show'), commandButton('zg show --agent Writer'), commandButton('zg show --agent Mailbox')]];
  if (!state.configured) return ['Check the setup, or explore another view.', [commandButton('zg config'), commandButton('zg show --agent Writer'), commandButton('zg show --agent Mailbox')]];
  return ['These defaults need no API key. You can deploy now.', [commandButton('zg deploy'), '<button type="button" data-setup>Setup in your project</button>', commandButton('zg validate')]];
}
function renderProgress() {
  const milestones = [
    ['Project', state.initialized],
    ['Workflow', state.workflow],
    ['Inspect', state.inspected],
    ['Setup', state.configured],
    ['Deploy', state.service !== 'idle'],
    ['Decide', liveReview().active ? ['approved', 'rejected'].includes(liveReview().state) : state.decision !== null],
  ];
  // Optional inspection can be skipped. A later achievement must not imply it happened.
  const furthest = milestones.reduce((last, item, index) => item[1] ? index : last, -1);
  const current = furthest + 1;
  document.querySelector('#milestones').innerHTML = milestones.map(([label, done], index) => {
    const skipped = !done && index < furthest;
    const status = done ? 'complete' : index === current ? 'next' : skipped ? 'not explored' : 'pending';
    return `<li class="milestone${done ? ' done' : ''}" data-milestone="${index}" aria-label="${label}: ${status}"${index === current ? ' aria-current="step"' : ''}><span class="desktop-label">${label}</span><span class="mobile-label" aria-hidden="true">${['Init', 'Write', 'Read', 'Setup', 'Run', 'Decide'][index]}</span>${index === current ? '<small>Next</small>' : skipped ? '<small>Not explored</small>' : ''}</li>`;
  }).join('');
}
function render({ focus = false } = {}) {
  const latest = state.entries.at(-1);
  // The screen is fixed. Replace its result instead of appending a transcript.
  // Keep command history in state for the arrow keys and refresh.
  if (latest) {
    const body = latest.kind === 'code' ? `<pre class="code" tabindex="0" aria-label="Python code"><code>${highlight(latest.text)}</code></pre>` : `<pre>${escape(latest.text)}</pre>`;
    const download = latest.kind === 'download' ? '<a class="download" href="./approval-example.zip" download>Download the runnable example</a>' : '';
    output.innerHTML = `<div class="entry">${body}${download}</div>`;
  } else {
    output.innerHTML = `<p class="note">${state.workflow ? 'Run a command to inspect this project.' : 'Build a workflow that drafts replies and waits for your approval.'}</p>`;
  }
  const telegramVisible = renderTelegram(state, data, runCommand);
  output.hidden = Boolean(state.agent) || telegramVisible;
  document.querySelector('#result-label').textContent = telegramVisible ? (liveReview().active ? 'Telegram' : 'Telegram preview') : state.agent ? 'Request' : latest?.speaker === 'note' ? 'About' : !latest ? 'Example' : 'Output';
  const stepNote = document.querySelector('#step-note');
  stepNote.hidden = Boolean(state.agent) || !latest?.note;
  stepNote.open = false;
  stepNote.querySelector('p').textContent = latest?.note || '';
  document.querySelector('#result-command').textContent = latest ? latest.speaker === 'shell' ? latest.command : latest.speaker === 'agent' ? 'Coding agent' : 'Demo' : '';
  if (telegramVisible) document.querySelector('#result-command').textContent = liveReview().active ? 'Live on our demo server' : 'Simulated';
  output.scrollTop = 0;
  const [hint, buttons] = choices();
  document.querySelector('#hint').textContent = hint;
  document.querySelector('#hint').hidden = !hint;
  suggestions.innerHTML = buttons.join('');
  suggestions.hidden = liveReview().active;
  document.querySelector('#resume-live').hidden = !liveReview().active;
  document.querySelector('.terminal').classList.toggle('agent-mode', Boolean(state.agent));
  if (state.agent) input.value = state.agent;
  else if (input.disabled) input.value = '';
  input.disabled = Boolean(state.agent);
  document.querySelector('#command-form button').disabled = Boolean(state.agent);
  document.querySelector('#agent-form').hidden = !state.agent;
  document.querySelector('#controls').hidden = false;
  if (state.agent) {
    const prompt = document.querySelector('#agent-prompt');
    prompt.value = data.prompt;
    prompt.style.height = 'auto';
    prompt.style.height = `${prompt.scrollHeight}px`;
    if (focus) prompt.focus({ preventScroll: true });
  }
  renderProgress();
  save();
  historyIndex = commandHistory().length;
  if (focus && !state.agent && !matchMedia('(max-width: 700px)').matches) input.focus({ preventScroll: true });
  announcement.textContent = latest ? `${latest.kind === 'code' ? 'Code displayed.' : latest.text.slice(0, 240)} ${hint}` : hint;
}
function commandHistory() { return state.entries.filter(entry => entry.speaker === 'shell').map(entry => entry.command); }
function requireWorkflow(command) {
  if (state.workflow) return true;
  add(command, 'Create the workflow with a coding agent first.');
  return false;
}
function requireService(command) {
  if (!requireWorkflow(command)) return false;
  if (state.service !== 'idle') return true;
  add(command, 'No service yet. Start it with zg deploy.');
  return false;
}
function taskText() {
  return `Task 1 · Mailbox · awaiting approval\n\n${data.reply}\n\nSend this reply?`;
}
function statusText() {
  const pending = state.decision === null;
  return `Service            ${state.service === 'stopped' ? 'stopped' : 'running'}\nPending approvals  ${pending ? 1 : 0}\nDrafts prepared    1\nSimulated sends    ${state.decision === true ? 1 : 0}`;
}
function runCommand(raw) {
  if (!data) return;
  const command = raw.trim().replace(/\s+/g, ' ');
  if (!command || state.agent) return;
  input.value = '';
  if (command === 'clear') {
    state.entries = [];
    render({ focus: true });
    return;
  }
  if (command === 'help') {
    add(command, [
      'zg init                         create the project',
      'codex / claude                  open a coding agent',
      'zg show                         read the global workflow',
      'zg show --agent Writer          inspect one participant',
      'zg show --agent Mailbox         inspect the other',
      'zg show --communications       show only the messages',
      'zg show --detail full          include action definitions',
      'zg validate                     check the workflow',
      'zg config                       inspect the setup',
      'zg deploy                       start the service',
      'zg deploy tasks                 see pending approvals',
      'zg deploy approve --task 1 --yes approve the reply',
      'zg deploy approve --task 1 --no  reject it',
      'zg deploy stop / start          stop or resume the service',
      'zg deploy status / logs         see what happened',
      'clear                           clear this terminal',
    ].join('\n'), { note: 'Click a suggestion or type a supported command. All commands run only in this simulation.' });
  } else if (command === 'zg init') {
    if (state.initialized) add(command, 'Project already initialized.');
    else {
      state.initialized = true;
      add(command, 'Created zippergen.toml, specification.md, AGENTS.md, and CLAUDE.md.', { note: 'The agent instructions point to the ZipperGen workflow skill.' });
    }
  } else if (['codex', 'claude'].includes(command)) {
    if (!state.initialized) add(command, 'Initialize the project with zg init first.');
    else if (state.workflow) add(command, 'The example workflow is already written. Use zg show to inspect it.', { note: 'In your own project, continue working with the agent to change the workflow.' });
    else {
      state.agent = command;
      add(command, '');
    }
  } else if (command === 'zg skill') {
    add(command, 'The workflow skill teaches the coding agent how to write,\nvalidate, inspect, and configure ZipperGen workflows.', { note: 'In a real project, this command prints the complete authoring instructions.' });
  } else if (command.startsWith('zg show')) {
    if (requireWorkflow(command)) {
      const views = {
        'zg show': [data.workflow, 'Each >> sends a value. @ Mailbox says who owns the decision.'],
        'zg show --agent Writer': [data.writer, 'Writer drafts and returns the reply. It has no work in the approval branch.'],
        'zg show --agent Mailbox': [data.mailbox, 'Mailbox reads requests, asks for approval, and handles either outcome.'],
        'zg show --communications': [data.communications, 'The same workflow, showing only cross-participant communication.'],
        'zg show --detail full': [data.full, 'The action definitions include the model prompt, human question, and local effects.'],
      };
      if (views[command]) {
        state.inspected = true;
        add(command, views[command][0], { kind: 'code', note: views[command][1] });
      } else add(command, 'This view is not part of the demo. Type help to see the available commands.');
    }
  } else if (command === 'zg validate') {
    if (requireWorkflow(command)) add(command, data.provenance.validation, { note: 'These checks ran against the real example when this demo was prepared.' });
  } else if (command === 'zg config') {
    if (requireWorkflow(command)) {
      state.configured = true;
      add(command, 'Model       Fixed example draft    No model call\nRequests    Local folder           mailbox/ (simulated)\nApproval    Telegram preview       Simulated\nDelivery    Example reply          No email sent', { note: 'These are the demo defaults. The downloadable project uses a mock model and terminal approval. Telegram is selected through connector configuration.' });
    }
  } else if (command === 'zg deploy') {
    if (requireWorkflow(command)) {
      if (state.service !== 'idle') add(command, 'This example is already deployed. Use its stop, start, or status command.');
      else {
        state.configured = true;
        state.service = 'running';
        add(command, 'Mailbox directory: /demo/mailbox (example)\nService started.\n\nRead 01.txt. Drafted a reply. Saved the pending approval.', { note: 'Guided deployment asks for the folder on your machine. The service then runs independently of your terminal.' });
      }
    }
  } else if (command === 'zg deploy tasks') {
    if (requireService(command)) {
      if (state.decision === null) {
        state.taskSeen = true;
        add(command, taskText());
      } else add(command, 'No pending approvals. Waiting for the next request.');
    }
  } else if (command === 'zg deploy status') {
    if (requireService(command)) add(command, statusText(), { note: 'A shortened status view for this simulation.' });
  } else if (command === 'zg deploy stop') {
    if (requireService(command)) {
      if (state.service === 'running') {
        state.service = 'stopped';
        add(command, state.decision === null ? 'Service stopped. Task 1 and its draft are still saved.' : 'Service stopped. The completed request remains recorded.');
      } else if (state.service === 'stopped') add(command, 'Service is already stopped.');
      else add(command, 'This request is already complete. Use “Try the other decision” to explore a fresh simulation.');
    }
  } else if (command === 'zg deploy start') {
    if (requireService(command)) {
      if (state.service === 'stopped') {
        state.service = 'running';
        state.restarted = true;
        state.taskSeen = true;
        if (state.decision === null) {
          add(command, `Service restarted. Same task. Same saved draft.\nNo new draft needed.\n\n${taskText()}`, { note: 'The draft was already saved before this interruption.' });
        } else add(command, 'Service restarted. Waiting for the next request.');
      } else add(command, 'Service is already running.');
    }
  } else if (['zg deploy approve --task 1 --yes', 'zg deploy approve --task 1 --no'].includes(command)) {
    if (liveReview().active) {
      add(command, 'This request is handled in Telegram. Open your live run to see its status.');
    } else if (requireService(command)) {
      if (state.service === 'stopped') add(command, 'Restart the simulated service before answering here.');
      else if (state.decision !== null) add(command, 'Task 1 already has a decision. No additional send.');
      else {
        const yes = command.endsWith('--yes');
        state.decision = yes;
        add(command, `${yes ? 'Approved. Reply sent (simulated).' : 'Rejected. No reply sent.'}\n01.txt marked as handled. Waiting for the next request.`, { note: 'You have gone from a prompt to a running workflow. The download includes the same code and a scripted reply.' });
      }
    }
  } else if (command === 'zg deploy logs') {
    if (requireService(command)) {
      const lines = ['Mailbox read 01.txt', 'Writer drafted a reply', 'Draft and pending approval saved'];
      if (state.restarted) lines.push('Service restarted with the saved task');
      if (state.service === 'stopped') lines.push('Service stopped. Progress remains saved.');
      if (state.decision === true) lines.push('Approval recorded', 'Simulated send completed', '01.txt marked 01.done');
      if (state.decision === false) lines.push('Rejection recorded', 'Send skipped', '01.txt marked 01.done');
      add(command, lines.join('\n'), { note: 'Illustrative event summary. No real service is running in this browser.' });
    }
  } else {
    add(command.slice(0, 500), 'This command is not part of the simulation. Type help for the available commands.');
  }
  render({ focus: true });
}
function showInformation(title, body) {
  document.querySelector('#information-title').textContent = title;
  document.querySelector('#information-body').innerHTML = body;
  document.querySelector('#information').showModal();
}
function showAbout() {
  showInformation('About this demo', '<p>This is an interactive simulation of a ZipperGen project.</p><p>The Python code and participant views are real. The coding session and CLI output are illustrative. No commands run on your machine. No model is called. Approve and reject lead to different outcomes. The Telegram preview is simulated. When available, the optional live step creates a separate ZipperGen run on our server and waits for your real Telegram approval.</p><p>Demo progress stays in this browser when storage is available.</p><a href="./approval-example.zip" download>Download the runnable example</a>');
}
function replay() {
  if (state.decision === null) return;
  state.decision = null;
  state.service = 'running';
  state.restarted = false;
  state.taskSeen = true;
  add('', `A fresh simulation of the same request.\n\n${taskText()}`, { speaker: 'note' });
  render({ focus: true });
}

document.querySelector('#command-form').addEventListener('submit', event => {
  event.preventDefault();
  runCommand(input.value);
});
document.querySelector('#agent-prompt').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.isComposing && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey) {
    event.preventDefault();
    document.querySelector('#agent-form').requestSubmit();
  }
});
document.addEventListener('live-review-change', () => { if (data) render(); });
document.querySelector('#agent-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!state.agent || !data) return;
  state.workflow = true;
  state.agent = null;
  add(data.prompt, '', { speaker: 'user' });
  add('Done.', 'Wrote workflow.py and specification.md.\nValidated the workflow and both participant views.', {
    speaker: 'agent', note: 'Mailbox handles requests and approval. Writer drafts the replies.',
  });
  render();
  input.value = 'zg show';
  // Keep the next step keyboard-accessible without opening the mobile keyboard.
  const next = matchMedia('(max-width: 700px)').matches
    ? suggestions.querySelector('[data-command="zg show"]') : input;
  next.focus({ preventScroll: true });
});
suggestions.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if ('command' in button.dataset) runCommand(button.dataset.command);
  else if ('replay' in button.dataset) replay();
  else if ('setup' in button.dataset) showInformation('Setup in your project', '<p>The downloadable example works with a mock model and terminal approval. Telegram delivery uses your own bot and private chat.</p><pre>zg provider configure approval-bot telegram\nzg provider set-credential approval-bot\nzg connector configure approval-chat approval-bot\nzg connector assign Mailbox approval-chat\nzg config</pre><p>Run these in your own terminal. Enter the token only in the hidden credential prompt. The live website example uses our demo bot.</p><details><summary>Use a real model later</summary><pre>zg provider configure writer-provider openai\nzg provider set-credential writer-provider\nzg model configure writer writer-provider YOUR_MODEL\nzg model assign Writer writer</pre><p>Replace YOUR_MODEL with a model available to your account. This is optional and is not used by the public demo.</p></details>');
});
document.querySelector('#reset').addEventListener('click', () => {
  if (!data) return;
  state = fresh();
  resetTelegram();
  input.value = '';
  render({ focus: true });
});
document.querySelector('#about').addEventListener('click', showAbout);
document.querySelector('#help').addEventListener('click', () => {
  if (state.agent) {
    showInformation('Commands', '<p>Send the example request to continue. You can then type shell commands or choose one of the suggestions.</p>');
  } else runCommand('help');
});
input.addEventListener('keydown', event => {
  const history = commandHistory();
  if (event.key === 'ArrowUp') {
    event.preventDefault();
    historyIndex = Math.max(0, historyIndex - 1);
    input.value = history[historyIndex] || '';
  } else if (event.key === 'ArrowDown') {
    event.preventDefault();
    historyIndex = Math.min(history.length, historyIndex + 1);
    input.value = history[historyIndex] || '';
  } else if (event.key === 'Escape') input.value = '';
});

try {
  const response = await fetch('./content.json');
  if (!response.ok) throw new Error('Example content unavailable');
  data = await response.json();
  render();
  initTelegram();
} catch {
  output.innerHTML = '<p>The example could not load. Please reload the page.</p><p><a href="./approval-example.zip" download>Download the example instead</a></p>';
}
