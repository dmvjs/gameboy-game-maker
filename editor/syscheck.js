import { runRomFrames, checkSelftestFrame, SCREEN_W, SCREEN_H } from './emucheck.js';

const $ = id => document.getElementById(id);
const MARKS = { ok: '✓', warn: '!', error: '✗', skipped: '–', running: '…' };

async function getJSON(url, options) {
  const res = await fetch(url, options);
  return res.json();
}

// ---- status chips ----------------------------------------------------------

async function refreshStatus() {
  let s;
  try {
    s = await getJSON('/api/status');
  } catch {
    setChip($('chipRgbds'), 'error', 'Server not running', 'Start it with: python3 -m gbstage serve');
    setChip($('chipEmu'), 'error', 'Emulator ?', '');
    return null;
  }
  $('appVersion').textContent = 'v' + s.app.version;

  const r = s.rgbds;
  if (!r.found) {
    setChip($('chipRgbds'), 'error', 'RGBDS missing', r.error);
  } else if (r.error) {
    setChip($('chipRgbds'), 'error', 'RGBDS broken', r.error);
  } else {
    const state = { tested: 'ok', untested: 'warn', unsupported: 'error' }[r.compat];
    setChip($('chipRgbds'), state, `RGBDS v${r.version}`,
      `${r.compat_message}\nFrom: ${r.source}\n${r.dir}\nSupported: ${r.supported}\nTested: ${r.tested.join(', ')}`);
  }

  const e = s.emulator;
  setChip($('chipEmu'), e.installed ? 'ok' : 'error',
    e.installed ? `${e.name} ${e.commit}` : 'Emulator missing', e.installed ? e.dir : e.error);
  return s;
}

function setChip(el, state, text, title) {
  el.className = 'chip ' + state;
  el.textContent = text;
  el.title = title || '';
}

// ---- system check ----------------------------------------------------------

let binjgbPromise = null;

export function loadBinjgb() {
  if (!binjgbPromise) {
    binjgbPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/emulator/binjgb.js';
      script.onload = () => window.Binjgb ? resolve(window.Binjgb) : reject(new Error('binjgb.js loaded but defined nothing'));
      script.onerror = () => reject(new Error('Could not load /emulator/binjgb.js (is the emulator installed?)'));
      document.head.appendChild(script);
    }).catch(err => { binjgbPromise = null; throw err; });
  }
  return binjgbPromise;
}

function renderChecks(checks) {
  const list = $('checkList');
  list.innerHTML = '';
  for (const c of checks) {
    const li = document.createElement('li');
    li.className = c.status;
    li.innerHTML = '<span class="mark"></span><span class="label"></span><span class="detail"></span>';
    li.querySelector('.mark').textContent = MARKS[c.status];
    li.querySelector('.label').textContent = c.label;
    li.querySelector('.detail').textContent = c.detail;
    if (c.fix) {
      const fix = document.createElement('span');
      fix.className = 'fix';
      fix.textContent = 'fix: ' + c.fix;
      li.appendChild(fix);
    }
    list.appendChild(li);
  }
}

function summarize(checks) {
  const statuses = new Set(checks.map(c => c.status));
  const overall = statuses.has('error') ? 'error' : statuses.has('warn') ? 'warn' : 'ok';
  const badge = $('overall');
  badge.className = 'badge ' + overall;
  badge.textContent = { ok: 'all good', warn: 'warnings', error: 'problems found' }[overall];
  $('installBtn').hidden = !checks.some(c => c.status === 'error' && c.fix && c.fix.includes('gbstage install'));
}

async function browserEmulatorCheck(serverChecks) {
  const label = 'Emulator run';
  const ready = id => serverChecks.find(c => c.id === id)?.status === 'ok';
  if (!ready('build') || !ready('emulator')) {
    return { id: 'emu-run', label, status: 'skipped', detail: 'needs a working test build and emulator files' };
  }
  try {
    const [Binjgb, rom] = await Promise.all([
      loadBinjgb(),
      fetch('/api/selftest.gb').then(async r => {
        if (!r.ok) throw new Error((await r.json()).error);
        return new Uint8Array(await r.arrayBuffer());
      }),
    ]);
    const frame = await runRomFrames(Binjgb, rom, 120);
    const img = new ImageData(new Uint8ClampedArray(frame.buffer), SCREEN_W, SCREEN_H);
    $('screen').getContext('2d').putImageData(img, 0, 0);
    $('emuResult').hidden = false;
    const result = checkSelftestFrame(frame);
    return result.ok
      ? { id: 'emu-run', label, status: 'ok', detail: 'booted the test ROM in the browser and saw all 4 shades' }
      : { id: 'emu-run', label, status: 'error',
          detail: `the screen didn't show the expected bands (brightness ${result.bands.join(', ')})`,
          fix: 'python3 -m gbstage install emulator' };
  } catch (err) {
    return { id: 'emu-run', label, status: 'error', detail: String(err.message || err),
             fix: 'python3 -m gbstage install emulator' };
  }
}

async function runSystemCheck() {
  $('rerunBtn').disabled = true;
  $('emuResult').hidden = true;
  $('overall').className = 'badge';
  $('overall').textContent = 'checking…';
  renderChecks([{ label: 'Checking', status: 'running', detail: 'building the test ROM…' }]);
  try {
    let checks;
    try {
      checks = (await getJSON('/api/doctor')).checks;
    } catch {
      checks = [{ label: 'Server', status: 'error', detail: "can't reach the gbstage server",
                  fix: 'python3 -m gbstage serve' }];
    }
    renderChecks([...checks, { label: 'Emulator run', status: 'running', detail: 'booting test ROM…' }]);
    if (checks.length > 1) checks.push(await browserEmulatorCheck(checks));
    renderChecks(checks);
    summarize(checks);
  } finally {
    $('rerunBtn').disabled = false;
    refreshStatus();
  }
}

async function installMissing() {
  const btn = $('installBtn');
  const log = $('installLog');
  btn.disabled = true;
  btn.textContent = 'Installing…';
  log.hidden = false;
  log.textContent = 'Downloading and verifying…';
  try {
    const res = await getJSON('/api/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Gbstage': '1' },
      body: JSON.stringify({ what: 'all' }),
    });
    log.textContent = res.log.join('\n');
  } catch (err) {
    log.textContent = 'Install request failed: ' + err;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Install missing';
  }
  await runSystemCheck();
}

export function openCheck() {
  $('installLog').hidden = true;
  if (!$('checkDialog').open) $('checkDialog').showModal();
  runSystemCheck();
}

export function initSystemCheck() {
  $('checkBtn').onclick = openCheck;
  $('chipRgbds').onclick = openCheck;
  $('chipEmu').onclick = openCheck;
  $('rerunBtn').onclick = runSystemCheck;
  $('installBtn').onclick = installMissing;
  $('closeBtn').onclick = () => $('checkDialog').close();

  refreshStatus().then(s => {
    const broken = !s || !s.rgbds.found || s.rgbds.error || s.rgbds.compat === 'unsupported' || !s.emulator.installed;
    if (broken) openCheck();
  });
}
