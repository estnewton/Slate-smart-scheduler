// Slate front end: plain JS, no build step. Talks to the FastAPI backend in src/server.py.
const $ = (sel) => document.querySelector(sel);
const HOURS = [8, 22];

const state = { date: null, status: null, data: null, openWhy: new Set() };
// Slate's clock comes from the server: in demo mode "today" is the first day of the demo week.
const nowDate = () => parseLocal(state.status?.now || isoDate(new Date()) + "T" + new Date().toTimeString().slice(0, 5));
const todayIso = () => state.status?.today || isoDate(new Date());

// ---------- date helpers ----------
function isoDate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function parseLocal(iso) { return new Date(iso.length === 10 ? iso + "T00:00" : iso); }
function addDays(iso, n) { const d = parseLocal(iso); d.setDate(d.getDate() + n); return isoDate(d); }
const fmtTime = (iso) => parseLocal(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
function fmtHour(h) { const d = new Date(); d.setHours(h, 0); return d.toLocaleTimeString([], { hour: "numeric" }); }
function relDue(iso) {
  if (!iso) return "no deadline";
  const due = parseLocal(iso), now = nowDate();
  const mins = Math.round((due - now) / 60000);
  if (mins < 0) return "overdue";
  if (mins < 60) return `due in ${mins} min`;
  const sameDay = isoDate(due) === isoDate(now);
  const tomorrow = isoDate(due) === addDays(isoDate(now), 1);
  const t = fmtTime(iso);
  if (sameDay) return `due today ${t}`;
  if (tomorrow) return `due tomorrow ${t}`;
  return `due ${due.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}`;
}
const fmtEffort = (m) => (m >= 60 ? `${+(m / 60).toFixed(1)} hr` : `${m} min`);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- API ----------
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.status === 204 ? null : res.json();
}

function flash(msg, kind = "info") {
  const el = $("#flash");
  el.textContent = msg;
  el.className = `flash ${kind}`;
  el.hidden = false;
  clearTimeout(flash.t);
  flash.t = setTimeout(() => (el.hidden = true), kind === "error" ? 9000 : 4000);
}

// ---------- rendering ----------
function renderConnection() {
  const { connected, has_credentials } = state.status;
  const el = $("#connection");
  if (connected) {
    el.innerHTML = `${state.status.demo ? `<span class="chip demo" title="Showing only the seeded demo week, not your real schedule">Demo week</span>` : ""}<span class="chip live"><span class="dot"></span>Google Calendar</span>
      <button class="ghost-btn" id="disconnect">Disconnect</button>`;
    $("#disconnect").onclick = async () => {
      if (!confirm("Disconnect Google Calendar? Slate will go back to demo data.")) return;
      await api("/auth/logout", { method: "POST" });
      await boot();
    };
  } else if (has_credentials) {
    el.innerHTML = `<span class="chip"><span class="dot"></span>Demo data</span>
      <a class="google-btn" href="/auth/login">${googleIcon()}Connect Google Calendar</a>`;
  } else {
    el.innerHTML = `<span class="chip"><span class="dot"></span>Demo data</span>`;
  }
  $("#setup").hidden = has_credentials || connected;
  $("#push-btn").hidden = !connected;
}

function renderDayTitle() {
  const today = todayIso();
  const d = parseLocal(state.date);
  let title = d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
  if (state.date === today) title = "Today";
  else if (state.date === addDays(today, 1)) title = "Tomorrow";
  else if (state.date === addDays(today, -1)) title = "Yesterday";
  $("#day-title").textContent = title;
  $("#today-btn").hidden = state.date === today;
}

function renderTimeline() {
  const { plan, all_day, hours } = state.data;
  const [h0, h1] = hours;
  const hourPx = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--hour"));
  const tl = $("#timeline");
  tl.style.height = `${(h1 - h0) * hourPx}px`;

  let html = "";
  for (let h = h0; h <= h1; h++) {
    html += `<div class="hourline" style="top:${(h - h0) * hourPx}px"><span>${fmtHour(h)}</span></div>`;
  }
  const dayStart = parseLocal(state.date); dayStart.setHours(h0, 0, 0, 0);
  const minsFrom = (iso) => (parseLocal(iso) - dayStart) / 60000;

  for (const item of layoutColumns(plan, minsFrom, hourPx)) {
    const { top, height } = item;
    const short = height < 34;
    const meta = `${fmtTime(item.start)}–${fmtTime(item.end)}${item.location ? " · " + esc(item.location) : ""}`;
    const width = `calc((100% - 10px) / ${item.cols} - 2px)`;
    const left = `calc(6px + (100% - 10px) / ${item.cols} * ${item.col})`;
    html += `<div class="block ${item.kind === "fixed" ? "b-fixed" : "b-task"}${short ? " short" : ""}"
      style="top:${top + 1}px;height:${height}px;left:${left};width:${width};right:auto" title="${esc(item.title)} — ${meta}">
      <span class="t">${esc(item.title)}</span><span class="m">${meta}</span></div>`;
  }

  if (state.date === todayIso()) {
    const now = (nowDate() - dayStart) / 60000;
    if (now >= 0 && now <= (h1 - h0) * 60) html += `<div class="nowline" style="top:${now * hourPx / 60}px"></div>`;
  }
  tl.innerHTML = html;
  $("#plan-empty").hidden = plan.length > 0;
  $("#allday").innerHTML = all_day.map((t) => `<span>${esc(t)}</span>`).join("");
}

// Overlapping events (a quiz inside a lecture, a call during class) sit side by side, like
// Google Calendar, instead of on top of each other. Overlap is judged on the drawn box, so
// short events that render taller than their real length don't collide either.
function layoutColumns(plan, minsFrom, hourPx) {
  const items = plan
    .map((p) => {
      const top = Math.max(0, minsFrom(p.start)) * hourPx / 60;
      const dur = Math.max(minsFrom(p.end) - minsFrom(p.start), 0);
      const bottom = (HOURS[1] - HOURS[0]) * hourPx;  // clip events that run past the last hour
      return { ...p, top, height: Math.max(Math.min(dur * hourPx / 60 - 2, bottom - top - 2), 17) };
    })
    .sort((a, b) => a.top - b.top || b.height - a.height);

  let cluster = [], colEnds = [], clusterEnd = -1;
  const flush = () => { cluster.forEach((it) => (it.cols = colEnds.length)); cluster = []; colEnds = []; };
  for (const it of items) {
    if (it.top >= clusterEnd) flush();
    let col = colEnds.findIndex((end) => end <= it.top);
    if (col === -1) { col = colEnds.length; colEnds.push(0); }
    colEnds[col] = it.top + it.height + 1;
    it.col = col;
    cluster.push(it);
    clusterEnd = Math.max(clusterEnd, it.top + it.height + 1);
  }
  flush();
  return items;
}

function taskRow(t, { max = 1, done = false } = {}) {
  const pct = t.score != null ? Math.max(4, Math.round((t.score / max) * 100)) : 0;
  const auto = t.source === "auto_generated" ? `<span class="badge">auto</span>` : "";
  const meta = [relDue(t.due), fmtEffort(t.effort_minutes), t.location].filter(Boolean).map(esc).join(" · ");
  const del = t.id.startsWith("manual-") ? `<button class="del" data-del="${esc(t.id)}">remove</button>` : "";
  const score = done ? del
    : `<div class="score"><b>${t.score.toFixed(2)}</b><div class="bar"><i style="width:${pct}%"></i></div>${del}</div>`;
  return `<li class="task">
    <input type="checkbox" class="check" data-done="${esc(t.id)}" ${done ? "checked" : ""} aria-label="Mark ${esc(t.title)} ${done ? "not done" : "done"}">
    <div><div class="task-title">${esc(t.title)}${auto}</div><div class="task-meta">${meta}</div>${done ? "" : whyBox(t)}</div>
    ${score}</li>`;
}

// "Why this rank?" -- shows the RICE-style formula with this task's actual numbers
function whyBox(t) {
  const b = t.breakdown;
  if (!b) return "";
  const open = state.openWhy.has(t.id) ? " open" : "";
  const n = (x) => (+x).toFixed(2);
  return `<details class="why" data-why="${esc(t.id)}"${open}><summary>Why this rank?</summary>
    <div class="formula">
      <span><b>${n(b.urgency)}</b>urgency</span><i>×</i>
      <span><b>${n(b.importance)}</b>importance</span><i>×</i>
      <span><b>${n(b.confidence)}</b>confidence</span><i>÷</i>
      <span><b>${n(b.effort_hours)}</b>hours</span><i>=</i>
      <span class="res"><b>${n(t.score)}</b>score</span>
    </div></details>`;
}

function renderLists() {
  const { ranked, generated, done } = state.data;
  const max = Math.max(...ranked.map((t) => t.score), 0.0001);
  $("#ranked").innerHTML = ranked.length
    ? ranked.map((t) => taskRow(t, { max })).join("")
    : `<li class="empty">All clear. Add a task below.</li>`;
  $("#done-wrap").hidden = done.length === 0;
  $("#done-count").textContent = `(${done.length})`;
  $("#done").innerHTML = done.map((t) => taskRow(t, { done: true })).join("");

  $("#generated").innerHTML = generated.length
    ? generated.map((g) => `<li><span>${esc(g.title)}</span><span class="when">${esc(relDue(g.due))}${g.location ? " · " + esc(g.location) : ""}</span></li>`).join("")
    : `<li class="empty">No quizzes or exams in the next two weeks.</li>`;

  const locs = new Set([...ranked, ...state.data.plan].map((t) => t.location).filter(Boolean));
  $("#locations").innerHTML = [...locs].map((l) => `<option value="${esc(l)}">`).join("");
}

function renderWeek() {
  const hot = /quiz|exam|midterm|final|test/i;
  $("#week").innerHTML = state.data.week.map((d) => {
    const dt = parseLocal(d.date);
    const evs = d.events.slice(0, 3).map((e) => `<span class="ev${hot.test(e.title) ? " hot" : ""}">${esc(e.title)}</span>`).join("");
    const more = d.events.length > 3 ? `<span class="ev">+${d.events.length - 3} more</span>` : "";
    return `<button class="day${d.date === state.date ? " sel" : ""}" data-day="${d.date}">
      <span class="dow">${dt.toLocaleDateString([], { weekday: "short" })}</span>
      <span class="num">${dt.getDate()}</span>${evs}${more}
      <span class="count">${d.events.length || ""}</span></button>`;
  }).join("");
}

async function load() {
  renderDayTitle();
  try {
    state.data = await api(`/api/dashboard?date=${state.date}&start_hour=${HOURS[0]}&end_hour=${HOURS[1]}`);
  } catch (e) {
    flash(e.message, "error");
    return;
  }
  renderTimeline();
  renderLists();
  renderWeek();
  $("#synced").textContent = `${state.data.source === "sample" ? "Updated" : "Synced"} ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
}

async function boot() {
  state.status = await api("/api/status");
  if (!state.date || !state.status.demo !== !boot.wasDemo) state.date = state.status.today;
  boot.wasDemo = state.status.demo;
  renderConnection();
  renderChat();
  await load();
}

// ---------- chat: type a sentence, get a calendar event ----------
const chat = { log: [], pending: null };

function fmtEventWhen(ev) {
  const d = parseLocal(ev.start);
  const day = d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  return ev.all_day ? `${day} · all day` : `${day} · ${fmtTime(ev.start)}–${fmtTime(ev.end)}`;
}

function renderChat() {
  const connected = state.status?.connected;
  $("#chat-input").placeholder = 'Try "Math quiz Tuesday 5-6pm in Wartik Lab"';
  $("#chat-log").innerHTML = chat.log.map((m) => {
    if (m.role === "you") return `<div class="msg you">${esc(m.text)}</div>`;
    if (m.role === "event") {
      const ev = m.event;
      const actions = m.status === "pending"
        ? `<div class="msg-actions">
             <button class="primary-btn" data-chat="add" ${connected ? "" : "disabled"}>Add to Google Calendar</button>
             <button class="ghost-btn" data-chat="cancel">Cancel</button></div>
           ${connected ? "" : `<div class="msg-note">Connect Google Calendar to add events.</div>`}`
        : m.status === "added" ? `<div class="msg-done">✓ Added to Google Calendar${m.link ? ` · <a href="${esc(m.link)}" target="_blank" rel="noopener">open</a>` : ""}</div>`
        : `<div class="msg-note">Not added.</div>`;
      return `<div class="msg slate">
        <div class="ev-card"><div class="ev-title">${esc(ev.title)}</div>
          <div class="ev-meta">${esc(fmtEventWhen(ev))}${ev.location ? ` · ${esc(ev.location)}` : ""}</div></div>
        ${ev.notes.map((n) => `<div class="msg-note">${esc(n)}</div>`).join("")}
        ${actions}</div>`;
    }
    return `<div class="msg slate">${esc(m.text)}</div>`;
  }).join("");
  $("#chat-log").hidden = chat.log.length === 0;
  const log = $("#chat-log");
  log.scrollTop = log.scrollHeight;
}

$("#chat-form").onsubmit = async (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text) return;
  chat.log.forEach((m) => { if (m.status === "pending") m.status = "skipped"; });
  chat.log.push({ role: "you", text });
  input.value = "";
  try {
    const event = await api("/api/chat/parse", { method: "POST", body: JSON.stringify({ text }) });
    chat.log.push({ role: "event", event, status: "pending" });
  } catch (err) {
    chat.log.push({ role: "slate", text: err.message });
  }
  chat.log = chat.log.slice(-8);
  renderChat();
};

$("#chat-log").onclick = async (e) => {
  const action = e.target.dataset?.chat;
  if (!action) return;
  const msg = [...chat.log].reverse().find((m) => m.status === "pending");
  if (!msg) return;
  if (action === "cancel") { msg.status = "skipped"; renderChat(); return; }
  e.target.disabled = true;
  try {
    const ev = msg.event;
    const res = await api("/api/events", { method: "POST", body: JSON.stringify({
      title: ev.title, start: ev.start, end: ev.end, all_day: ev.all_day, location: ev.location }) });
    msg.status = "added";
    msg.link = res.link;
    state.date = res.date;  // jump to the day it was added, so it's visible right away
    renderChat();
    await load();
  } catch (err) {
    e.target.disabled = false;
    flash(err.message, "error");
  }
};

// ---------- events ----------
$("#prev").onclick = () => { state.date = addDays(state.date, -1); load(); };
$("#next").onclick = () => { state.date = addDays(state.date, 1); load(); };
$("#sync-btn").onclick = async () => {
  const btn = $("#sync-btn");
  btn.classList.add("spin");
  await load();
  setTimeout(() => btn.classList.remove("spin"), 400);
};
// Coming back to this tab (e.g. after adding an event in Google Calendar) re-syncs automatically.
window.addEventListener("focus", () => { if (state.status?.connected) load(); });
document.addEventListener("toggle", (e) => {
  const id = e.target.dataset?.why;
  if (id) e.target.open ? state.openWhy.add(id) : state.openWhy.delete(id);
}, true);
$("#today-btn").onclick = () => { state.date = todayIso(); load(); };
$("#week").onclick = (e) => {
  const b = e.target.closest("[data-day]");
  if (b) { state.date = b.dataset.day; load(); }
};

document.addEventListener("change", async (e) => {
  const id = e.target.dataset?.done;
  if (!id) return;
  try {
    await api(`/api/tasks/${encodeURIComponent(id)}/done`, { method: "POST", body: JSON.stringify({ done: e.target.checked }) });
    await load();
  } catch (err) { flash(err.message, "error"); }
});
document.addEventListener("click", async (e) => {
  const id = e.target.dataset?.del;
  if (!id) return;
  try {
    await api(`/api/tasks/${encodeURIComponent(id)}`, { method: "DELETE" });
    await load();
  } catch (err) { flash(err.message, "error"); }
});

const impLabels = ["Trivial", "Trivial", "Low", "Low", "Medium", "Medium", "Medium", "High", "High", "Critical", "Critical"];
const impInput = $("#add-form").importance;
impInput.oninput = () => ($("#imp-out").textContent = impLabels[Math.round(impInput.value * 10)]);

$("#add-form").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title: f.title.value,
        due: f.due.value || null,
        effort_minutes: +f.effort.value,
        importance: +f.importance.value,
        location: f.location.value || null,
      }),
    });
    f.reset();
    $("#imp-out").textContent = "Medium";
    await load();
  } catch (err) { flash(err.message, "error"); }
};

$("#push-btn").onclick = async () => {
  const btn = $("#push-btn");
  btn.disabled = true;
  try {
    const { created } = await api(`/api/plan/push?date=${state.date}&start_hour=${HOURS[0]}&end_hour=${HOURS[1]}`, { method: "POST" });
    flash(created ? `Added ${created} block${created > 1 ? "s" : ""} to Google Calendar.` : "No Slate tasks to add for this day.");
  } catch (err) { flash(err.message, "error"); }
  btn.disabled = false;
};

function googleIcon() {
  return `<svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/></svg>`;
}

// OAuth round-trip feedback
const qs = new URLSearchParams(location.search);
if (qs.has("connected")) flash("Google Calendar connected. Your real schedule is loaded.");
if (qs.has("auth_error")) flash(`Couldn't connect Google Calendar (${qs.get("auth_error")}). Try again.`, "error");
if (qs.toString()) history.replaceState(null, "", "/");

boot();
