'use strict';

const $ = (id) => document.getElementById(id);
const PL = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const saved = loadLocal('claplab-settings') || {};
const TIME_SYNC_RETRY_DELAYS = [5000, 15000];

const state = {
  source: 'demo',
  origin: typeof saved.origin === 'string' ? saved.origin : '',
  config: { sensitivity: 'auto', threshold: 50, start_mode: 'first_clap' },
  demo: { phase: 'idle', startedAt: null, endedAt: null, claps: [], nextClapAt: 0 },
  status: blankStatus(),
  history: makeSeedHistory(),
  selected: null,
  pollTimer: null,
  pollBusy: false,
  connectionOk: false,
  sourceVersion: 0,
  timeSync: { attempts: 0, nextAt: 0, busy: false, controller: null },
  detailRequest: 0,
  noticeTimer: null,
};

function loadLocal(key) { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } }
function writeLocal(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* no storage in some browsers */ } }
function blankStatus() { return { state: 'idle', elapsed_ms: 0, clap_count: 0, cps: 0, avg_interval_ms: null, last_interval_ms: null, intervals_ms: [], wifi_enabled: false, time_synced: false }; }
function clamp(n, min, max) { return Math.max(min, Math.min(max, n)); }
function numeric(value, fallback = 0) { const n = Number(value); return Number.isFinite(n) ? n : fallback; }
function prettyTime(ms) {
  const cs = Math.floor(Math.max(0, numeric(ms)) / 10);
  const min = Math.floor(cs / 6000).toString().padStart(2, '0');
  const sec = Math.floor((cs % 6000) / 100).toString().padStart(2, '0');
  const hundredths = (cs % 100).toString().padStart(2, '0');
  return `${min}:${sec}.${hundredths}`;
}
function prettyMs(n) { return n === null || n === undefined || !Number.isFinite(Number(n)) ? '—' : `${Math.round(Number(n))} ms`; }
function sessionDate(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}
function prettyDate(iso) {
  const date = sessionDate(iso);
  return date ? date.toLocaleString('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }) : 'Data nieznana';
}
function isoOffset(iso, ms) {
  const date = sessionDate(iso);
  if (!date || typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '';
  const result = new Date(date.getTime() + ms);
  return Number.isFinite(result.getTime()) ? result.toISOString() : '';
}
function intervalData(claps) { return claps.slice(1).map((clap, index) => clap.offset_ms - claps[index].offset_ms); }
function avg(values) { return values.length ? values.reduce((a,b) => a+b, 0) / values.length : null; }

function makeSeedHistory() {
  const now = Date.now();
  const input = [
    [26, [0, 610, 1320, 1920, 2600, 3340, 3980, 4660, 5300, 6050]],
    [49, [0, 900, 1820, 2700, 3620, 4580, 5460]],
    [78, [0, 430, 870, 1310, 1750, 2180, 2620, 3070, 3510, 3960, 4420, 4840]],
  ];
  return input.map(([hoursAgo, offsets], i) => buildSession(`demo-${i+1}`, new Date(now - hoursAgo * 3600000).toISOString(), offsets, offsets[offsets.length-1] + 950));
}
function buildSession(id, startedAt, offsets, duration) {
  const intervals = offsets.slice(1).map((v, i) => v - offsets[i]);
  return {
    id, started_at: startedAt, duration_ms: duration, clap_count: offsets.length,
    cps: duration > 0 ? offsets.length / (duration / 1000) : 0,
    avg_interval_ms: avg(intervals),
    claps: offsets.map(offset_ms => ({ offset_ms })),
  };
}

function notify(message, ok = true) {
  const node = $('notice');
  node.textContent = message;
  node.classList.toggle('ok', ok);
  node.hidden = false;
  clearTimeout(state.noticeTimer);
  state.noticeTimer = setTimeout(() => { node.hidden = true; }, 7000);
}

function navigate(view) {
  document.querySelectorAll('.view').forEach(el => { el.hidden = el.id !== `view-${view}`; });
  document.querySelectorAll('.nav-button').forEach(btn => {
    const active = btn.dataset.view === view;
    btn.classList.toggle('active', active);
    if (active) btn.setAttribute('aria-current', 'page'); else btn.removeAttribute('aria-current');
  });
  if (view === 'history') refreshHistory();
}

function renderConnection() {
  const demo = state.source === 'demo';
  $('mode-label').textContent = demo ? 'DEMO' : 'ESP32';
  $('mode-label').classList.toggle('real', !demo);
  $('connection-label').lastChild.textContent = demo ? ' Dane symulowane' : state.connectionOk ? ' Połączono z ESP32' : ' Brak połączenia';
  $('connection-label').title = demo ? 'Dane symulowane' : !state.connectionOk ? 'Brak połączenia. Ponawianie automatyczne.' : state.status.time_synced === true ? 'Czas ESP32 zsynchronizowany' : 'Czas ESP32 nie jest zsynchronizowany';
  $('connection-dot').className = `status-dot ${demo ? '' : state.connectionOk ? 'connected' : 'disconnected'}`;
  const footer = $('footer-source');
  if (footer) footer.textContent = demo ? 'Tryb demonstracyjny' : 'Tryb ESP32';
}

function renderStatus() {
  const s = state.status;
  const phase = s.state || 'idle';
  const offline = state.source === 'esp32' && !state.connectionOk;
  const label = { idle:'Gotowość', armed:'Oczekiwanie', running:'Pomiar trwa', finished:'Zakończona' }[phase] || 'Nieznany stan';
  $('session-label').textContent = label;
  document.querySelector('.session-pill').classList.toggle('running', phase === 'running');
  $('elapsed').textContent = prettyTime(s.elapsed_ms);
  $('stat-claps').textContent = String(numeric(s.clap_count));
  $('stat-cps').textContent = PL.format(numeric(s.cps));
  $('stat-average').textContent = prettyMs(s.avg_interval_ms);
  $('stat-last').textContent = prettyMs(s.last_interval_ms);
  $('hero-caption').textContent = ({
    idle:'Urządzenie gotowe do pomiaru',
    armed:'Czekanie na pierwsze klaśnięcie',
    running:'Zbieranie danych o klaśnięciach',
    finished:'Pomiar zakończony; wyniki zapisane',
  })[phase] || 'Sprawdź stan ESP32';
  if (offline) $('hero-caption').textContent = 'Brak połączenia z ESP32. Wyświetlane dane nie są aktualizowane.';
  $('btn-start').disabled = offline || phase === 'running' || phase === 'armed';
  $('btn-stop').disabled = offline || (phase !== 'running' && phase !== 'armed');
  $('btn-reset').disabled = offline;
  const c = state.config;
  $('detail-start').textContent = c.start_mode === 'signal' ? 'Na sygnał dźwiękowy' : 'Po pierwszym klaśnięciu';
  $('detail-threshold').textContent = c.sensitivity === 'manual' ? `Manualny (${c.threshold}/100)` : 'Automatyczny';
  $('detail-wifi').textContent = state.source === 'demo' ? 'Tryb demonstracyjny' : state.connectionOk ? 'Połączono' : 'Brak połączenia';
  $('detail-history').textContent = state.source === 'demo' ? 'Dane przykładowe' : 'Pamięć ESP32';
  renderChart(Array.isArray(s.intervals_ms) ? s.intervals_ms : []);
}

function renderChart(values) {
  const root = $('interval-chart');
  root.replaceChildren();
  const recent = values.map(Number).filter(n => Number.isFinite(n) && n >= 0).slice(-12);
  if (!recent.length) {
    const label = document.createElement('div');
    label.className = 'empty';
    label.textContent = 'Wykres pojawi się po wykryciu kolejnych klaśnięć.';
    root.append(label); return;
  }
  const max = Math.max(...recent, 1);
  recent.forEach(n => {
    const group = document.createElement('div'); group.className = 'bar-group';
    const bar = document.createElement('div'); bar.className = 'bar';
    bar.style.height = `${clamp(n / max * 100, 4, 100)}%`;
    bar.title = `${Math.round(n)} ms`;
    const caption = document.createElement('small'); caption.textContent = `${Math.round(n)}`;
    group.append(bar, caption); root.append(group);
  });
}

function renderConfigForm() {
  document.querySelector(`input[name="sensitivity"][value="${state.config.sensitivity}"]`).checked = true;
  $('threshold').value = String(state.config.threshold);
  $('threshold-value').textContent = String(state.config.threshold);
  $('threshold').disabled = state.config.sensitivity !== 'manual';
  $('start-mode').value = state.config.start_mode;
}

function syncDemoStatus() {
  const demo = state.demo;
  const elapsed = demo.startedAt ? (demo.endedAt || Date.now()) - demo.startedAt : 0;
  const intervals = intervalData(demo.claps);
  state.status = {
    state: demo.phase,
    elapsed_ms: Math.max(0, elapsed),
    clap_count: demo.claps.length,
    cps: elapsed > 0 ? demo.claps.length / (elapsed / 1000) : 0,
    avg_interval_ms: avg(intervals),
    last_interval_ms: intervals.length ? intervals[intervals.length-1] : null,
    intervals_ms: intervals.slice(-12),
    wifi_enabled: false,
  };
  renderStatus();
}

function demoStart() {
  const d = state.demo;
  d.claps = []; d.endedAt = null; d.startedAt = null;
  d.phase = state.config.start_mode === 'first_clap' ? 'armed' : 'running';
  if (d.phase === 'running') d.startedAt = Date.now();
  d.nextClapAt = Date.now() + 850;
  syncDemoStatus();
}
function demoStop() {
  const d = state.demo;
  if (d.phase !== 'armed' && d.phase !== 'running') return;
  if (d.phase === 'running') {
    d.endedAt = Date.now();
    const duration = Math.max(1, d.endedAt - d.startedAt);
    const session = buildSession(`demo-${Date.now()}`, new Date(d.startedAt).toISOString(), d.claps.map(x => x.offset_ms), duration);
    state.history.unshift(session);
    writeLocal('claplab-demo-history', state.history);
  }
  d.phase = 'finished';
  syncDemoStatus();
  notify('Sesja zakończona. Wyniki są dostępne w historii (DEMO).');
}
function demoReset() {
  const d = state.demo;
  d.phase = 'idle'; d.startedAt = null; d.endedAt = null; d.claps = []; d.nextClapAt = 0;
  syncDemoStatus();
}
function demoTick() {
  if (state.source !== 'demo') return;
  const d = state.demo;
  const now = Date.now();
  if ((d.phase === 'running' || d.phase === 'armed') && now >= d.nextClapAt) {
    if (d.phase === 'armed') { d.phase = 'running'; d.startedAt = now; }
    d.claps.push({ offset_ms: now - d.startedAt });
    d.nextClapAt = now + 500 + Math.floor(Math.random() * 550);
  }
  if (d.phase === 'running' || d.phase === 'armed') syncDemoStatus();
}

function apiUrl(path, origin = state.origin) { return `${origin.replace(/\/$/, '')}${path}`; }
function apiTimeout(path) {
  if (path === '/api/sessions') return 15000;
  if (path.startsWith('/api/sessions/')) return 30000;
  return 4000;
}
async function api(path, method='GET', body=undefined, origin=state.origin, options={}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) abort();
  const timeout = setTimeout(abort, apiTimeout(path));
  const init = { method, cache: 'no-store', signal: controller.signal, headers: { Accept: 'application/json' } };
  if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  try {
    const response = await fetch(apiUrl(path, origin), init);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const text = await response.text();
    const result = text ? JSON.parse(text) : {};
    if (result?.ok === false) throw new Error(result.error || 'Błąd API');
    return result;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abort);
  }
}
function validStatus(s) {
  return s && ['idle', 'armed', 'running', 'finished'].includes(s.state)
    && ['elapsed_ms', 'clap_count', 'cps'].every(key => typeof s[key] === 'number' && Number.isFinite(s[key]) && s[key] >= 0)
    && ['avg_interval_ms', 'last_interval_ms'].every(key => s[key] === null || (typeof s[key] === 'number' && Number.isFinite(s[key]) && s[key] >= 0))
    && Array.isArray(s.intervals_ms) && s.intervals_ms.every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0)
    && typeof s.time_synced === 'boolean' && typeof s.wifi_enabled === 'boolean';
}
function isCurrent(version) { return state.source === 'esp32' && state.sourceVersion === version; }
function resetTimeSync() {
  state.timeSync.controller?.abort();
  state.timeSync = { attempts: 0, nextAt: 0, busy: false, controller: null };
}
async function syncTime(version) {
  const sync = state.timeSync;
  if (!isCurrent(version) || !state.connectionOk || state.status.time_synced === true
      || sync.busy || sync.attempts >= TIME_SYNC_RETRY_DELAYS.length + 1 || performance.now() < sync.nextAt) return;
  sync.busy = true;
  sync.attempts++;
  sync.nextAt = Infinity;
  sync.controller = new AbortController();
  try {
    await api('/api/time', 'POST', { epoch_ms: Date.now() }, state.origin, { signal: sync.controller.signal });
    // The next status response confirms time_synced; a POST alone is not confirmation.
  } catch (error) {
    if (isCurrent(version) && state.timeSync === sync && state.connectionOk && state.status.time_synced !== true) {
      const delay = TIME_SYNC_RETRY_DELAYS[sync.attempts - 1];
      sync.nextAt = delay === undefined ? Infinity : performance.now() + delay;
      const next = delay === undefined ? 'Osiągnięto limit 3 prób. Ponowna próba po ponownym połączeniu.' : `Ponowna próba za ${delay / 1000} s.`;
      notify(`Nie udało się zsynchronizować czasu ESP32: ${error.message}. ${next}`, false);
    }
  } finally {
    sync.busy = false;
    sync.controller = null;
  }
}
function acceptStatus(result, version) {
  const reconnected = !state.connectionOk;
  state.status = { ...blankStatus(), ...result };
  if (result.config) adoptConfig(result.config);
  state.connectionOk = true;
  if (reconnected) {
    void fetchConfig();
    void refreshHistory();
  }
  if (result.time_synced === true) state.timeSync.nextAt = Infinity;
  void syncTime(version);
}
async function pollStatus() {
  if (state.source !== 'esp32' || state.pollBusy) return;
  const version = state.sourceVersion;
  state.pollBusy = true;
  try {
    const result = await api('/api/status');
    if (!isCurrent(version)) return;
    if (!validStatus(result)) throw new Error('Nieprawidłowa odpowiedź /api/status');
    acceptStatus(result, version);
  } catch {
    if (!isCurrent(version)) return;
    state.connectionOk = false;
    resetTimeSync();
    // Do not replace missing ESP32 data with simulated measurements.
  } finally {
    if (isCurrent(version)) {
      state.pollBusy = false;
      renderConnection(); renderStatus();
    }
  }
}
async function fetchConfig() {
  const version = state.sourceVersion;
  try { const c = await api('/api/config'); if (isCurrent(version)) { adoptConfig(c); renderStatus(); } }
  catch (error) { if (isCurrent(version)) notify(`Nie udało się pobrać konfiguracji: ${error.message}`, false); }
}
function adoptConfig(c) {
  if (!c || !['auto', 'manual'].includes(c.sensitivity) || !['first_clap', 'signal'].includes(c.start_mode)
      || !Number.isInteger(c.threshold) || c.threshold < 1 || c.threshold > 100) throw new Error('Nieprawidłowa konfiguracja API');
  const changed = ['sensitivity', 'threshold', 'start_mode'].some(key => state.config[key] !== c[key]);
  state.config = {
    sensitivity: c.sensitivity === 'manual' ? 'manual' : 'auto',
    threshold: clamp(Math.round(numeric(c.threshold, 50)), 1, 100),
    start_mode: c.start_mode === 'signal' ? 'signal' : 'first_clap',
  };
  if (changed) renderConfigForm();
}
function stopPolling() { if (state.pollTimer) clearInterval(state.pollTimer); state.pollTimer = null; }
function applySource() {
  const choice = document.querySelector('input[name="source"]:checked').value;
  const origin = $('api-origin').value.trim();
  if (choice === 'esp32' && origin) {
    try { const url = new URL(origin); if (!['http:', 'https:'].includes(url.protocol)) throw Error(); }
    catch { notify('Podaj poprawny adres http:// lub https:// do ESP32.', false); return; }
  }
  if (choice === 'esp32' && !origin && location.protocol === 'file:') {
    notify('Otwórz stronę przez serwer HTTP lub wpisz adres ESP32. Przy otwarciu pliku bezpośrednio użyj trybu DEMO.', false); return;
  }
  state.origin = origin.replace(/\/$/, '');
  state.source = choice;
  state.sourceVersion++;
  state.pollBusy = false;
  resetTimeSync();
  stopPolling();
  state.connectionOk = false;
  state.selected = null;
  $('session-detail').hidden = true;
  if (choice === 'esp32') {
    state.status = blankStatus();
    state.history = [];
    pollStatus();
    state.pollTimer = setInterval(pollStatus, 500);
    notify('Włączono tryb ESP32. Połącz telefon z Wi-Fi urządzenia i sprawdź dostępność API.');
  } else {
    const previous = loadLocal('claplab-demo-history');
    state.history = Array.isArray(previous) ? previous : makeSeedHistory();
    demoReset();
    notify('Włączono tryb DEMO. Dane pomiarowe są symulowane.');
  }
  writeLocal('claplab-settings', { origin: state.origin });
  renderConnection(); renderStatus(); renderHistory();
}

async function detectDevice() {
  if (!['http:', 'https:'].includes(location.protocol)) return;
  const version = state.sourceVersion;
  try {
    // Probe the page's own server, regardless of an address saved during earlier use.
    const result = await api('/api/status', 'GET', undefined, '');
    if (state.sourceVersion !== version) return;
    if (!validStatus(result)) throw new Error('To nie jest API ESP32');
    $('api-origin').value = '';
    document.querySelector('input[name="source"][value="esp32"]').checked = true;
    applySource();
  } catch {
    if (state.sourceVersion === version) notify('Nie wykryto ESP32 pod adresem strony. Tryb DEMO — dane symulowane. Adres urządzenia możesz ustawić w ustawieniach.', false);
  }
}

async function control(action) {
  if (state.source === 'demo') {
    if (action === 'start') demoStart();
    else if (action === 'stop') demoStop();
    else demoReset();
    return;
  }
  if (!state.connectionOk) { notify('Brak połączenia z ESP32 – polecenie nie zostało wysłane.', false); return; }
  const version = state.sourceVersion;
  try { await api(`/api/session/${action}`, 'POST'); if (isCurrent(version)) await pollStatus(); }
  catch (error) { if (isCurrent(version)) notify(`Nie udało się wykonać polecenia: ${error.message}`, false); }
}

function renderHistory() {
  const root = $('history-rows'); root.replaceChildren();
  const sessions = Array.isArray(state.history) ? state.history : [];
  $('history-empty').hidden = sessions.length > 0;
  sessions.forEach(session => {
    const row = document.createElement('tr');
    [prettyDate(session.started_at), prettyTime(session.duration_ms), String(numeric(session.clap_count)), PL.format(numeric(session.cps))].forEach(text => {
      const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
    });
    const action = document.createElement('td');
    const button = document.createElement('button'); button.className = 'table-action'; button.type = 'button'; button.textContent = 'Szczegóły';
    button.addEventListener('click', () => showSession(session.id)); action.append(button); row.append(action);
    root.append(row);
  });
}
async function refreshHistory() {
  if (state.source === 'demo') { renderHistory(); return; }
  const version = state.sourceVersion;
  try {
    const result = await api('/api/sessions');
    if (!isCurrent(version)) return;
    if (!result || !Array.isArray(result.sessions)) throw new Error('Nieprawidłowa lista sesji');
    state.history = result.sessions;
    renderHistory();
  } catch (error) { if (isCurrent(version)) notify(`Nie udało się pobrać historii: ${error.message}`, false); }
}
async function showSession(id) {
  const version = state.sourceVersion;
  const request = ++state.detailRequest;
  try {
    const session = state.source === 'demo' ? state.history.find(s => String(s.id) === String(id)) : await api(`/api/sessions/${encodeURIComponent(id)}`);
    if (state.sourceVersion !== version || request !== state.detailRequest) return;
    if (!session || !Array.isArray(session.claps)) throw Error('Nieprawidłowe szczegóły sesji');
    state.selected = session;
    $('session-detail').hidden = false;
    $('selected-session-title').textContent = `Rozpoczęta: ${prettyDate(session.started_at)}`;
    $('selected-claps').textContent = String(numeric(session.clap_count));
    $('selected-duration').textContent = prettyTime(session.duration_ms);
    $('selected-average').textContent = prettyMs(session.avg_interval_ms);
    const root = $('clap-rows'); root.replaceChildren();
    (session.claps || []).forEach((clap,i,all) => {
      const offset = numeric(clap.offset_ms);
      const previous = i > 0 ? numeric(all[i-1].offset_ms) : null;
      const row = document.createElement('tr');
      [String(i+1), prettyTime(offset), previous === null ? '—' : prettyMs(offset-previous)].forEach(value => {
        const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
      });
      root.append(row);
    });
    $('session-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) { if (state.sourceVersion === version && request === state.detailRequest) notify(`Błąd pobierania szczegółów sesji: ${error.message}`, false); }
}
function csvCell(value) { const x = String(value ?? ''); return /[;\r\n"]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x; }
function exportCsv() {
  const session = state.selected;
  if (!session) return;
  const lines = [
    ['Nr klaśnięcia','Data i czas ISO','Czas od startu [ms]','Odstęp od poprzedniego [ms]'],
  ];
  const claps = session.claps || [];
  claps.forEach((clap,i) => {
    const offset = numeric(clap.offset_ms);
    const previous = i > 0 ? numeric(claps[i-1].offset_ms) : null;
    lines.push([i + 1, isoOffset(session.started_at, offset), offset, previous === null ? '' : offset - previous]);
  });
  const csv = '\ufeff' + lines.map(row => row.map(csvCell).join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
  const a = document.createElement('a'); a.href = url;
  a.download = `klaskanie_${String(session.id).replace(/[^a-zA-Z0-9_-]/g, '_')}.csv`;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function saveConfig(event) {
  event.preventDefault();
  const config = {
    sensitivity: document.querySelector('input[name="sensitivity"]:checked').value,
    threshold: Math.round(numeric($('threshold').value, 50)),
    start_mode: $('start-mode').value,
  };
  if (state.source === 'demo') {
    state.config = config; renderStatus();
    notify('Ustawienia zapisane w trybie DEMO. Nie wysłano ich do urządzenia.');
  } else {
    if (!state.connectionOk) { notify('Nie można zapisać konfiguracji: brak połączenia z ESP32.', false); return; }
    const version = state.sourceVersion;
    try {
      const returned = await api('/api/config', 'PUT', config);
      if (!isCurrent(version)) return;
      adoptConfig(returned.sensitivity ? returned : config);
      renderStatus(); notify('Konfiguracja zapisana na ESP32.');
    } catch (error) { if (isCurrent(version)) notify(`Błąd zapisywania konfiguracji: ${error.message}`, false); }
  }
}

function init() {
  const previous = loadLocal('claplab-demo-history');
  if (Array.isArray(previous)) state.history = previous;
  $('api-origin').value = state.origin;
  document.querySelectorAll('.nav-button').forEach(btn => btn.addEventListener('click', () => navigate(btn.dataset.view)));
  $('btn-start').addEventListener('click', () => control('start'));
  $('btn-stop').addEventListener('click', () => control('stop'));
  $('btn-reset').addEventListener('click', () => control('reset'));
  $('refresh-history').addEventListener('click', refreshHistory);
  $('export-csv').addEventListener('click', exportCsv);
  $('apply-source').addEventListener('click', applySource);
  $('config-form').addEventListener('submit', saveConfig);
  document.querySelectorAll('input[name="sensitivity"]').forEach(el => el.addEventListener('change', () => {
    $('threshold').disabled = document.querySelector('input[name="sensitivity"]:checked').value !== 'manual';
  }));
  $('threshold').addEventListener('input', () => { $('threshold-value').textContent = $('threshold').value; });
  renderConfigForm(); syncDemoStatus(); renderHistory(); renderConnection();
  setInterval(demoTick, 80);
  void detectDevice();
}

init();
