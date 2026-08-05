const $ = id => document.getElementById(id);
const api = async (path, opts = {}) => {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  return res.json();
};

const SHOP = [
  { type: "nitro", name: "Discord Nitro", icon: "💎" },
  { type: "discord_account", name: "Discord Account", icon: "🎮" },
  { type: "robux", name: "Robux", icon: "💰" },
  { type: "roblox_account", name: "Roblox Account", icon: "🧱" },
  { type: "youtube_account", name: "YouTube Account", icon: "▶️" },
  { type: "tiktok_account", name: "TikTok Account", icon: "🎵" },
];

const CHARSET_META = {
  letters: { desc: "a-z", combo: "aaaa → zzzz" },
  letters_and_numbers: { desc: "a-z, 0-9", combo: "aaaa → 9zz9" },
  all: { desc: "a-z, 0-9, - (GitHub rules)", combo: "aa-a → 9-9z" },
};

let state = {
  charset: "letters_and_numbers",
  premium: false,
  running: false,
  lastEventCount: 0,
  spark: [],
  redeemType: "nitro",
};

/* ---------- boot ---------- */
async function boot() {
  const s = await api("/api/status");
  if (s.logged_in) { state.premium = s.premium; showApp(s); }
  else showAuth();
  renderShop();
  bindEvents();
}

function showAuth() {
  $("app-screen").classList.add("hidden");
  $("auth-screen").classList.remove("hidden");
}
function showApp(s) {
  $("auth-screen").classList.add("hidden");
  $("app-screen").classList.remove("hidden");
  $("user-name").textContent = "@" + s.username;
  setLicense(s.premium, s.time_left);
  $("worker-cap").textContent = `(max ${s.workers})`;
  $("threads-input").max = s.workers;
  $("threads-input").value = s.workers;
  $("threads-val").textContent = s.workers;
  pollStats();
  setInterval(pollStats, 500);
}

/* ---------- license ---------- */
function setLicense(premium, timeLeft) {
  const badge = $("license-badge");
  badge.className = "badge " + (premium ? "premium" : "trial");
  badge.textContent = premium ? "PREMIUM" : "TRIAL";
  const el = $("time-left");
  if (premium || timeLeft == null) { el.textContent = "∞"; el.style.color = "var(--green)"; }
  else {
    el.style.color = "var(--yellow)";
    const mm = String(Math.floor(timeLeft / 60)).padStart(2, "0");
    const ss = String(Math.floor(timeLeft % 60)).padStart(2, "0");
    el.textContent = `${mm}:${ss}`;
  }
}

/* ---------- stats polling ---------- */
let lastSpark = 0;
async function pollStats() {
  const d = await api("/api/stats");
  const s = d.stats;
  if (!s) {
    setState("IDLE", "idle");
    if (state.running) { state.running = false; setButtons(false); }
    return;
  }
  setState(s.state, stateClass(s.state));
  $("mode-text").textContent = s.mode;
  $("cps-num").textContent = s.cps.toFixed(1);
  $("stat-checks").textContent = s.total_checks.toLocaleString();
  $("stat-avail").textContent = s.available;
  $("stat-taken").textContent = s.taken;
  $("stat-errors").textContent = s.errors;
  $("stat-ratelimit").textContent = s.rate_limited;
  $("stat-workers").textContent = s.workers ? `${s.busy}/${s.workers}` : "0/0";
  $("stat-proxies").textContent = s.proxies;
  $("stat-claims").textContent = s.claims_success;

  if (s.license) setLicense(s.license === "PREMIUM", s.time_left);
  if (Date.now() - lastSpark > 400) {
    state.spark.push(s.cps);
    if (state.spark.length > 120) state.spark.shift();
    drawSpark();
    lastSpark = Date.now();
  }
  if (s.events && s.events.length !== state.lastEventCount) {
    state.lastEventCount = s.events.length;
    renderEvents(s.events);
  }
  renderHits(s.available_names || []);

  if (d.running !== state.running) {
    state.running = d.running;
    setButtons(state.running);
    if (!state.running) toast("Run stopped — state: " + s.state, s.state === "SUCCESS" ? "" : "err");
  }
}

function stateClass(st) {
  if (st.includes("CLAIM") || st.includes("ATTEMPT")) return "claiming";
  if (st === "SEARCHING") return "searching";
  if (st === "SUCCESS") return "success";
  if (st === "DONE") return "done";
  if (st.includes("FAILED") || st.includes("EXPIRED")) return "failed";
  return "idle";
}
function setState(text, cls) {
  $("state-text").textContent = text;
  $("state-badge").className = "state-badge " + cls;
}
function setButtons(running) {
  $("btn-start").disabled = running;
  $("btn-stop").disabled = !running;
}

/* ---------- sparkline ---------- */
function drawSpark() {
  const c = $("spark"), ctx = c.getContext("2d");
  const W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);
  const data = state.spark;
  if (data.length < 2) return;
  const max = Math.max(...data, 1);
  ctx.beginPath();
  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - (v / max) * (H - 8) - 4;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#00e5ff";
  ctx.lineWidth = 2;
  ctx.shadowColor = "#00e5ff";
  ctx.shadowBlur = 12;
  ctx.stroke();
  ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath();
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, "rgba(0,229,255,0.35)");
  g.addColorStop(1, "rgba(0,229,255,0)");
  ctx.fillStyle = g; ctx.fill();
}

/* ---------- lists ---------- */
function renderEvents(events) {
  const log = $("event-log");
  log.innerHTML = "";
  events.forEach(([ts, msg, kind]) => {
    const div = document.createElement("div");
    div.innerHTML = `<span class="ts">[${ts}]</span><span class="${kind}">${esc(msg)}</span>`;
    log.appendChild(div);
  });
  log.scrollTop = log.scrollHeight;
}
function renderHits(names) {
  const list = $("hits-list");
  list.innerHTML = "";
  names.forEach(n => {
    const div = document.createElement("div");
    div.textContent = "@" + n;
    list.appendChild(div);
  });
  $("hits-count").textContent = `(${names.length})`;
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------- actions ---------- */
async function startRun() {
  const minLen = parseInt($("min-len").value) || 3;
  const maxLen = parseInt($("max-len").value) || 5;
  if (minLen > maxLen) return msg("min length can't be bigger than max", "err");
  const body = {
    min_len: minLen,
    max_len: maxLen,
    charset: state.charset,
    auto_claim: $("auto-claim").checked,
  };
  const res = await api("/api/run", { method: "POST", body: JSON.stringify(body) });
  msg(res.msg || (res.ok ? "sniping started" : "error"), res.ok ? "ok" : "err");
  if (res.ok) { state.running = true; setButtons(true); }
}
async function stopRun() {
  await api("/api/stop", { method: "POST" });
  toast("Stop signal sent", "");
}
function msg(text, kind) {
  const el = $("run-msg");
  el.textContent = text;
  el.className = "auth-msg " + kind;
}
function toast(text, kind) {
  const el = $("toast");
  el.textContent = text;
  el.className = "toast " + kind;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3500);
}

/* ---------- auth + bind ---------- */
function bindEvents() {
  let authMode = "login";
  $("tab-login").onclick = () => { authMode = "login"; $("tab-login").classList.add("active"); $("tab-signup").classList.remove("active"); $("auth-btn").textContent = "ENTER THE GRID"; $("auth-hint").style.display = "block"; };
  $("tab-signup").onclick = () => { authMode = "signup"; $("tab-signup").classList.add("active"); $("tab-login").classList.remove("active"); $("auth-btn").textContent = "CREATE ACCOUNT"; $("auth-hint").style.display = "none"; };
  $("auth-form").onsubmit = async e => {
    e.preventDefault();
    const body = { username: $("auth-user").value, password: $("auth-pass").value };
    const res = await api("/api/" + authMode, { method: "POST", body: JSON.stringify(body) });
    const el = $("auth-msg");
    el.textContent = res.msg;
    el.className = "auth-msg " + (res.ok ? "ok" : "err");
    if (res.ok) setTimeout(async () => { const s = await api("/api/status"); state.premium = s.premium; showApp(s); }, 400);
  };

  // charset question
  const setCharset = (cs, btn) => {
    state.charset = cs;
    ["cs-letters", "cs-alnum", "cs-all"].forEach(id => $(id).classList.remove("active"));
    btn.classList.add("active");
    const meta = CHARSET_META[cs];
    $("charset-desc").textContent = `${meta.desc}  ·  ${meta.combo}`;
  };
  $("cs-letters").onclick = e => setCharset("letters", e.currentTarget);
  $("cs-alnum").onclick = e => setCharset("letters_and_numbers", e.currentTarget);
  $("cs-all").onclick = e => setCharset("all", e.currentTarget);

  $("btn-start").onclick = startRun;
  $("btn-stop").onclick = stopRun;
  $("threads-input").oninput = () => $("threads-val").textContent = $("threads-input").value;
  $("btn-logout").onclick = async () => { await api("/api/logout", { method: "POST" }); location.reload(); };
  $("btn-copy").onclick = () => {
    const names = $("hits-list").innerText;
    if (names) { navigator.clipboard.writeText(names); toast("copied", ""); }
  };

  $("btn-shop").onclick = () => $("shop-modal").classList.remove("hidden");
  $("shop-close").onclick = () => $("shop-modal").classList.add("hidden");
  $("shop-modal").onclick = e => { if (e.target === $("shop-modal")) $("shop-modal").classList.add("hidden"); };
  $("btn-redeem").onclick = async () => {
    const res = await api("/api/redeem", { method: "POST", body: JSON.stringify({ code: $("redeem-code").value, type: state.redeemType }) });
    const el = $("redeem-msg");
    el.textContent = res.msg;
    el.className = "auth-msg " + (res.ok ? "ok" : "err");
    if (res.ok) setTimeout(() => { $("shop-modal").classList.add("hidden"); location.reload(); }, 800);
  };
}

function renderShop() {
  $("shop-grid").innerHTML = "";
  SHOP.forEach(item => {
    const div = document.createElement("div");
    div.className = "shop-item" + (item.type === state.redeemType ? " selected" : "");
    div.innerHTML = `<div class="icon">${item.icon}</div><div class="name">${item.name}</div>`;
    div.onclick = () => { state.redeemType = item.type; renderShop(); };
    $("shop-grid").appendChild(div);
  });
}

boot();
