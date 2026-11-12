// Dependency-free browser integration tests. Requires Node >=22 and Chrome/Edge.
// Mock responses and state transitions follow Klaskacz/api.h and Klaskacz.ino.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const root = resolve(import.meta.dirname, '..');
let available = false, invalidStatus = false, failTime = false, delay = 0;
let timeDelay = 0, longHistory = false;
let config = { sensitivity: 'manual', threshold: 60, start_mode: 'first_clap' };
let phase = 'idle', synced = false;
const calls = [];
const sessions = [null, '2026-11-12T10:00:00Z'].map((started_at, i) => ({
  id: `session-${i + 1}`, started_at, duration_ms: 1600, clap_count: 3,
  cps: 1.88, avg_interval_ms: 600, claps: [{ offset_ms: 0 }, { offset_ms: 500 }, { offset_ms: 1200 }],
}));
const status = () => ({ state: phase, elapsed_ms: phase === 'running' || phase === 'finished' ? 1600 : 0,
  clap_count: phase === 'running' || phase === 'finished' ? 3 : 0, cps: phase === 'running' ? 1.88 : 0,
  avg_interval_ms: phase === 'running' ? 600 : null, last_interval_ms: phase === 'running' ? 700 : null,
  intervals_ms: phase === 'running' ? [500, 700] : [], wifi_enabled: true, time_synced: synced, config });
const server = createServer(async (req, res) => {
  try {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    if (pathname.startsWith('/api/')) {
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      const text = Buffer.concat(chunks).toString();
      const body = text ? JSON.parse(text) : undefined;
      calls.push({ path: pathname, method: req.method, body, at: Date.now() });
      res.setHeader('Content-Type', 'application/json');
      const send = (data, code = 200) => { res.statusCode = code; res.end(JSON.stringify(data)); };
      const sendSlow = async (data, ms) => {
        const json = JSON.stringify(data), middle = Math.floor(json.length / 2);
        res.write(json.slice(0, middle));
        await new Promise(r => setTimeout(r, ms));
        res.end(json.slice(middle));
      };
      if (!available) return send({ ok: false, error: 'not found' }, 404);
      if (pathname === '/api/status') {
        const value = invalidStatus ? { state: 'running' } : status();
        if (delay) await new Promise(r => setTimeout(r, delay));
        return send(value);
      }
      if (pathname === '/api/config') {
        if (req.method === 'PUT') config = body;
        else assert.equal(req.method, 'GET');
        return send(config);
      }
      if (pathname === '/api/time') {
        assert.equal(req.method, 'POST');
        assert.ok(Math.abs(Date.now() - body.epoch_ms) < 10000);
        const shouldFail = failTime;
        if (timeDelay) await new Promise(r => setTimeout(r, timeDelay));
        if (res.destroyed) return;
        if (shouldFail) return send({ ok: false, error: 'epoch_ms invalid' }, 400);
        synced = true; return send({ ok: true });
      }
      if (pathname === '/api/sessions') {
        assert.equal(req.method, 'GET');
        if (longHistory) return sendSlow({ sessions: Array.from({ length: 50 }, (_, i) => ({
          ...sessions[0], id: `session-${i + 1}`, claps: undefined,
        })) }, 6000);
        return send({ sessions: sessions.map(({ claps, ...summary }) => summary) });
      }
      if (pathname.startsWith('/api/sessions/')) {
        assert.equal(req.method, 'GET');
        if (longHistory) return sendSlow({ ...sessions[0], clap_count: 10000,
          claps: Array.from({ length: 10000 }, (_, i) => ({ offset_ms: i * 500 })),
        }, 7000);
        const session = sessions.find(s => pathname.endsWith('/' + s.id));
        return session ? send(session) : send({ ok: false, error: 'no such session' }, 404);
      }
      if (pathname.startsWith('/api/session/')) {
        assert.equal(req.method, 'POST');
        const action = pathname.split('/').pop();
        if (action === 'start' && ['idle', 'finished'].includes(phase)) phase = config.start_mode === 'signal' ? 'running' : 'armed';
        if (action === 'stop') phase = phase === 'armed' ? 'idle' : phase === 'running' ? 'finished' : phase;
        if (action === 'reset') phase = 'idle';
        return send({ ok: true });
      }
      return send({ ok: false, error: 'not found' }, 404);
    }
    const name = pathname === '/' ? 'index.html' : pathname.slice(1);
    if (!['index.html', 'app.js', 'styles.css'].includes(name)) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', name.endsWith('.js') ? 'application/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html');
    res.end(await readFile(join(root, 'wykrywacz_klaskania_www', name)));
  } catch (error) { res.writeHead(500).end(String(error)); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`;
const profile = await mkdtemp(join(tmpdir(), 'claplab-browser-'));
const chrome = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const browser = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
let socket;
const pause = ms => new Promise(r => setTimeout(r, ms));
async function until(fn, label, timeout = 12000) {
  const start = Date.now();
  while (Date.now() - start < timeout) { if (await fn()) return; await pause(50); }
  throw Error(`Timeout: ${label}`);
}
try {
  let port;
  await until(async () => {
    try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); return !!port; } catch { return false; }
  }, 'Chrome startup');
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((r, reject) => { socket.onopen = r; socket.onerror = reject; });
  let sequence = 0; const pending = new Map(); const errors = [];
  socket.onmessage = event => {
    const msg = JSON.parse(event.data);
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails);
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); msg.error ? p.reject(Error(msg.error.message)) : p.resolve(msg.result); }
  };
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params }));
  });
  await cdp('Runtime.enable'); await cdp('Page.enable');
  const run = async expression => {
    const result = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const check = async (expression, label) => { assert.ok(await run(expression), label); console.log(`PASS ${label}`); };
  const wait = (expression, label = expression, timeout) => until(() => run(expression), label, timeout);
  const navigate = async url => {
    await cdp('Page.navigate', { url });
    await wait('typeof state !== "undefined" && document.readyState === "complete"', 'page loaded');
  };
  const source = async value => run(`document.querySelector('input[name="source"][value="${value}"]').checked = true; applySource()`);

  // Audit every static ID reference, including the intentionally optional old footer.
  const js = await readFile(join(root, 'wykrywacz_klaskania_www/app.js'), 'utf8');
  const html = await readFile(join(root, 'wykrywacz_klaskania_www/index.html'), 'utf8');
  const ids = [...js.matchAll(/\$\('([^']+)'\)/g)].map(m => m[1]);
  for (const id of ids) assert.ok(id === 'footer-source' || html.includes(`id="${id}"`), `DOM id ${id}`);
  console.log('PASS static DOM references');

  await navigate(pathToFileURL(join(root, 'wykrywacz_klaskania_www/index.html')).href);
  await check('state.source === "demo" && $("mode-label").textContent === "DEMO"', 'file startup in DEMO');
  await check('(()=>{navigate("settings"); return !$("view-settings").hidden && $("view-live").hidden})()', 'tabs');
  await run('navigate("live"); $("btn-start").click()');
  await check('state.status.state === "armed"', 'DEMO start armed');
  await wait('state.status.state === "running"');
  await run('$("btn-stop").click()');
  await check('state.status.state === "finished" && state.history[0].id.startsWith("demo-")', 'DEMO stop saves history');
  await run('$("btn-reset").click()');
  await check('state.status.state === "idle" && state.status.clap_count === 0', 'DEMO reset');
  await run('document.querySelector("input[name=sensitivity][value=manual]").click(); $("threshold").value="82"; $("start-mode").value="signal"; saveConfig({preventDefault(){}}); control("start")');
  await check('state.status.state === "running" && state.config.threshold === 82 && !$("threshold").disabled', 'DEMO manual sensitivity and signal start');
  await run('control("stop"); control("reset")');
  assert.equal(calls.filter(c => c.path === '/api/time').length, 0);
  console.log('PASS no time sync in DEMO');

  await navigate(origin);
  await wait('$("notice").textContent.includes("Nie wykryto")');
  await check('state.source === "demo"', 'HTTP static server remains DEMO');
  available = true; invalidStatus = true;
  await run('detectDevice()');
  await check('state.source === "demo"', 'invalid JSON status does not identify device');
  invalidStatus = false;
  await run('localStorage.setItem("claplab-settings", JSON.stringify({origin:"http://127.0.0.1:1"}))');
  await navigate(origin + '/?device');
  await wait('state.source === "esp32" && state.connectionOk && state.status.time_synced');
  await check('state.origin === "" && $("mode-label").textContent === "ESP32"', 'same-origin device detection overrides old saved address');
  await check('state.history.length === 2 && !$("history-rows").textContent.includes("demo-")', 'real history replaces demo rows');
  await check('state.config.threshold === 60 && $("threshold").value === "60"', 'GET config');
  await run('$("threshold").value="73"');
  await pause(1100);
  await check('$("threshold").value === "73"', 'polling preserves unsaved form input');
  assert.equal(calls.filter(c => c.path === '/api/time').length, 1);
  console.log('PASS exactly one time sync across repeated polls');
  await run('saveConfig({preventDefault(){}})');
  assert.deepEqual(config, { sensitivity: 'manual', threshold: 73, start_mode: 'first_clap' });
  console.log('PASS PUT configuration');
  await run('document.querySelector("input[name=sensitivity][value=auto]").click(); $("start-mode").value="signal"; saveConfig({preventDefault(){}})');
  await run('control("start")');
  await wait('state.status.state === "running"');
  assert.equal(config.sensitivity, 'auto'); assert.equal(config.start_mode, 'signal');
  await check('$("threshold").disabled && $("detail-start").textContent.includes("sygnał")', 'API auto sensitivity and signal start');
  await run('control("reset");');
  await wait('state.status.state === "idle"');
  await run('$("start-mode").value="first_clap"; saveConfig({preventDefault(){}})');
  await run('control("start")');
  await wait('state.status.state === "armed"');
  await run('control("stop")');
  await wait('state.status.state === "idle"');
  console.log('PASS POST start and cancellation while armed');
  phase = 'running';
  await run('pollStatus()');
  await wait('state.status.state === "running"');
  await check('$("stat-claps").textContent === "3" && $("stat-last").textContent === "700 ms" && $("interval-chart").children.length === 2', 'status metrics and running state');
  await run('control("stop")');
  await wait('state.status.state === "finished"');
  await run('control("reset")');
  await wait('state.status.state === "idle"');
  await check('$("stat-average").textContent === "—" && $("stat-last").textContent === "—"', 'null intervals');
  console.log('PASS POST stop/reset and finished/idle states');
  await run('navigate("history"); refreshHistory()');
  await check('$("history-rows").children.length === 2', 'history wrapper');
  await run('showSession("session-1")');
  await check('$("selected-session-title").textContent.includes("Data nieznana") && $("clap-rows").children.length === 3', 'details and unknown start date');
  await check('[null, undefined, "", "  ", "bad-date", {}, false].every(v => prettyDate(v) === "Data nieznana" && isoOffset(v,500) === "")', 'invalid and empty dates');
  await check('isoOffset("2026-11-12T10:00:00Z", 500) === "2026-11-12T10:00:00.500Z" && isoOffset("2026-11-12T10:00:00Z",1e30) === ""', 'valid ISO offset and overflow');
  await run('window.csvBlob=null; window.csvName=null; URL.createObjectURL = b => {window.csvBlob=b;return "blob:test"}; HTMLAnchorElement.prototype.click=function(){window.csvName=this.download}; exportCsv()');
  await check('(async()=>{const text=await csvBlob.text(); return text.includes("1;;0;") && text.includes("3;;1200;700") && !text.includes("1970") && !text.includes("Invalid") && csvName==="klaskanie_session-1.csv"})()', 'CSV without date retains offsets');
  await run('(async()=>{await showSession("session-2"); exportCsv()})()');
  await check('(async()=> (await csvBlob.text()).includes("2026-11-12T10:00:01.200Z"))()', 'CSV with absolute time');

  available = false;
  await wait('!state.connectionOk');
  await check('state.source === "esp32" && $("btn-start").disabled && $("connection-label").textContent.includes("Brak połączenia") && $("hero-caption").textContent.includes("nie są aktualizowane")', 'connection loss with no DEMO fallback');
  available = true; synced = false;
  await wait('state.connectionOk && state.status.time_synced');
  assert.equal(calls.filter(c => c.path === '/api/time').length, 2);
  console.log('PASS reconnection and new time sync');
  available = false; await wait('!state.connectionOk');
  available = true; failTime = true; synced = false;
  await wait('state.connectionOk && $("notice").textContent.includes("zsynchronizować")');
  await pause(1100);
  assert.equal(calls.filter(c => c.path === '/api/time').length, 3);
  await check('state.connectionOk && !state.status.time_synced && $("connection-label").title.includes("nie jest")', 'time sync failure is nonblocking and does not flood requests');
  await wait('state.timeSync.attempts === 3 && !state.timeSync.busy', 'bounded retries', 26000);
  const failedCalls = calls.filter(c => c.path === '/api/time').slice(2);
  assert.equal(failedCalls.length, 3);
  assert.ok(failedCalls[1].at - failedCalls[0].at >= 4900);
  assert.ok(failedCalls[2].at - failedCalls[1].at >= 14900);
  await pause(5500);
  assert.equal(calls.filter(c => c.path === '/api/time').length, 5);
  await check('state.connectionOk && state.timeSync.attempts === 3', 'three-attempt cap with 5s/15s retry spacing while status stays available');

  // A transient error must recover without forcing a status disconnect.
  await source('esp32');
  await wait('state.timeSync.attempts === 1 && !state.timeSync.busy');
  failTime = false;
  await wait('state.status.time_synced');
  await check('state.timeSync.attempts === 2', 'transient time sync failure retries successfully on live connection');

  // A time already set by another client cancels pending retries.
  synced = false; failTime = true;
  await source('esp32');
  await wait('state.timeSync.attempts === 1 && !state.timeSync.busy');
  synced = true;
  await wait('state.status.time_synced');
  const confirmedCount = calls.filter(c => c.path === '/api/time').length;
  await pause(5500);
  assert.equal(calls.filter(c => c.path === '/api/time').length, confirmedCount);
  await source('esp32');
  await wait('state.connectionOk');
  assert.equal(calls.filter(c => c.path === '/api/time').length, confirmedCount);
  console.log('PASS synced status cancels retry and skips POST on reconnect');

  // Simultaneous calls and a slow POST must not produce concurrent sync requests.
  failTime = false; synced = false; timeDelay = 1500;
  await source('esp32');
  await wait('state.timeSync.busy');
  const busyCount = calls.filter(c => c.path === '/api/time').length;
  await run('Promise.all([syncTime(state.sourceVersion), syncTime(state.sourceVersion), syncTime(state.sourceVersion)])');
  await pause(650);
  assert.equal(calls.filter(c => c.path === '/api/time').length, busyCount);
  await source('demo');
  await check('!state.timeSync.busy && state.timeSync.attempts === 0', 'source change aborts pending sync and resets its state');
  await pause(1700);
  assert.equal(calls.filter(c => c.path === '/api/time').length, busyCount);
  assert.equal(synced, false);
  console.log('PASS no overlapping time requests or stale retries in DEMO');
  timeDelay = 0;
  await source('esp32');
  await wait('state.connectionOk && state.status.time_synced');

  // Large chunked bodies arrive beyond the old 4s timeout; UI remains interactive.
  longHistory = true;
  const historyStart = calls.length;
  await run('window.historyDone=false; void refreshHistory().then(()=>window.historyDone=true)');
  await until(() => calls.slice(historyStart).some(c => c.path === '/api/sessions'), 'long list request');
  await pause(4500);
  await check('!window.historyDone && state.connectionOk && (()=>{navigate("settings");return !$("view-settings").hidden})()', 'UI and status remain responsive during long history download');
  await wait('window.historyDone && state.history.length === 50');
  await check('$("history-rows").children.length === 50', '50-session history body succeeds after 6s');
  await run('window.detailsDone=false; void showSession("session-1").then(()=>window.detailsDone=true)');
  await pause(4500);
  await check('!window.detailsDone && (()=>{navigate("live");return !$("view-live").hidden})()', 'UI remains responsive during long detail download');
  await wait('window.detailsDone && state.selected.claps.length === 10000');
  await check('$("clap-rows").children.length === 10000', '10000-clap detail body succeeds after 7s');
  longHistory = false;

  // A stuck request must release pollBusy and permit the next connection.
  delay = 6000;
  await wait('!state.connectionOk', 'status timeout');
  delay = 0;
  await wait('state.connectionOk && state.status.time_synced', 'recovery after timeout');
  console.log('PASS request timeout and recovery');

  // Switch devices while an old status request is in flight (same source name).
  await run('stopPolling()');
  await wait('!state.pollBusy');
  delay = 800; phase = 'running';
  const before = calls.length;
  await run('void pollStatus()');
  await until(() => calls.length > before, 'delayed request sent');
  await source('demo');
  await check('$("history-rows").textContent !== "" && $("session-detail").hidden', 'source switch resets selected details');
  delay = 0; phase = 'idle';
  await source('esp32');
  await wait('state.connectionOk');
  await pause(1100);
  await check('state.status.state === "idle"', 'old device response cannot replace new source state');
  await source('demo');
  const syncCount = calls.filter(c => c.path === '/api/time').length;
  await pause(1100);
  assert.equal(calls.filter(c => c.path === '/api/time').length, syncCount);
  console.log('PASS no sync after manual DEMO selection');

  // A delayed startup probe must not override a manual source selection.
  delay = 800;
  const detection = run('detectDevice()');
  await pause(100);
  await source('demo');
  await detection;
  await check('state.source === "demo"', 'manual source choice wins over delayed auto detection');
  delay = 0;

  for (const width of [390, 320]) {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height: 844, deviceScaleFactor: 1, mobile: true });
    for (const view of ['live', 'history', 'settings']) {
      await run(`navigate('${view}')`);
      await check('document.documentElement.scrollWidth <= window.innerWidth', `mobile ${width}px ${view} has no page overflow`);
    }
  }
  // Save a reproducible screenshot outside the source tree.
  const shot = await cdp('Page.captureScreenshot', { format: 'png' });
  await writeFile(join(profile, 'mobile.png'), Buffer.from(shot.data, 'base64'));
  console.log(`Screenshot: ${join(profile, 'mobile.png')}`);
  assert.equal(errors.length, 0, `Uncaught browser errors: ${JSON.stringify(errors)}`);
  console.log('PASS no uncaught JavaScript exceptions');
  for (const name of ['app.js', 'index.html', 'styles.css']) {
    assert.deepEqual(await readFile(join(root, 'wykrywacz_klaskania_www', name)), await readFile(join(root, 'Klaskacz/data', name)));
  }
  console.log('PASS identical frontend assets in both directories');
  console.log('All browser/mock tests passed. Physical ESP32 and phone tests were NOT run.');
} finally {
  socket?.close(); browser.kill(); server.closeAllConnections(); server.close();
}
