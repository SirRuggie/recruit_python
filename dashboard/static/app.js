// Jo Nation scheduled posts dashboard. Plain JS, no build step.
"use strict";

const state = {
  user: null,
  csrf: "",
  posts: [],
  defaultChannel: "",
  templates: null,
  filter: "all",
  editing: null, // { post (or null for new), form }
};

const TIMEZONES = [
  ["America/New_York", "Eastern"],
  ["America/Chicago", "Central"],
  ["America/Denver", "Mountain"],
  ["America/Los_Angeles", "Pacific"],
  ["UTC", "UTC"],
  ["Europe/London", "London"],
  ["Europe/Berlin", "Central Europe"],
  ["Asia/Kolkata", "India"],
  ["Australia/Sydney", "Sydney"],
];

// Lucide icons (ISC license), inlined so the page needs no icon package.
const ICONS = {
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  pause: '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  pencil: '<path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/><path d="m15 5 4 4"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
};
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const $ = (sel, root = document) => root.querySelector(sel);

// ---------- API ----------

async function api(method, path, body) {
  const options = { method, headers: {}, credentials: "same-origin" };
  if (method !== "GET") options.headers["X-CSRF-Token"] = state.csrf;
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw Object.assign(new Error("Can't reach the dashboard. Check your connection."), { status: 0 });
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    state.user = null;
    renderLogin();
  }
  if (!response.ok) throw Object.assign(new Error(data.error || "Something went wrong."), { status: response.status, data });
  return data;
}

// ---------- time formatting ----------

const clock = (date, timeZone) =>
  date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone });

function hhmmLabel(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h < 12 ? "AM" : "PM";
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${suffix}`;
}

function tzShort(timeZone) {
  try {
    const part = new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "short" })
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName");
    return part ? part.value : timeZone;
  } catch {
    return timeZone;
  }
}

function countdown(ms) {
  const minutes = Math.max(0, Math.round(ms / 60000));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

function dayLabel(date) {
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86400000);
  const yesterday = new Date(today.getTime() - 86400000);
  const same = (a, b) => a.toDateString() === b.toDateString();
  if (same(date, today)) return "Today";
  if (same(date, tomorrow)) return "Tomorrow";
  if (same(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const lastSent = (iso) => (iso ? `${dayLabel(new Date(iso))}, ${clock(new Date(iso))}` : "Not yet");

// ---------- derived data ----------

const status = (post) => (post.error ? "error" : post.enabled ? "active" : "paused");
const clanName = (post) => post.clan?.name || post.clan_tag || "Unknown clan";
const initials = (name) => (name || "?").replace(/[^A-Za-z0-9 ]/g, "").split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";

function badge(post, cls = "badge") {
  if (post.clan?.badge) return `<img class="${cls}" src="${esc(post.clan.badge)}" alt="" width="44" height="44" loading="lazy">`;
  return `<span class="${cls}" aria-hidden="true">${esc(initials(clanName(post)))}</span>`;
}

function upcoming() {
  // Every future send of every active post, soonest first.
  const sends = [];
  for (const post of state.posts) {
    if (!post.enabled) continue;
    for (const iso of post.next_sends) sends.push({ post, at: new Date(iso) });
  }
  return sends.sort((a, b) => a.at - b.at);
}

// ---------- rendering ----------

function renderLogin() {
  const params = new URLSearchParams(location.search);
  const messages = {
    denied: `That Discord account isn't on the allowed list.${params.get("id") ? ` Its ID is ${params.get("id")}.` : ""}`,
    expired: "The sign-in took too long. Try again.",
    failed: "Discord sign-in failed. Try again.",
    cancelled: "Sign-in was cancelled.",
  };
  const notice = messages[params.get("login")];
  $("#app").innerHTML = `
    <section class="login">
      <div class="login-box">
        <h1>Jo Nation</h1>
        <p>Scheduled recruitment posts</p>
        ${notice ? `<p class="notice">${esc(notice)}</p>` : ""}
        <a class="btn discord" href="/auth/login">Sign in with Discord</a>
      </div>
    </section>`;
}

function render() {
  const counts = { active: 0, paused: 0, error: 0 };
  state.posts.forEach((p) => counts[status(p)]++);
  const next = upcoming()[0];
  const avatar = state.user.avatar
    ? `<img class="avatar" src="${esc(state.user.avatar)}" alt="">`
    : `<span class="avatar" aria-hidden="true"></span>`;

  $("#app").innerHTML = `
    <header class="topbar">
      <div class="brand"><strong>Jo Nation</strong><span>Scheduled posts</span></div>
      <button class="btn ghost icon-only" data-action="refresh" aria-label="Refresh">${icon("refresh")}</button>
      ${avatar}
      <button class="btn ghost icon-only" data-action="logout" aria-label="Sign out ${esc(state.user.name)}">${icon("logout")}</button>
    </header>
    <main>
      <section class="summary" aria-label="Summary">
        <div>
          <p class="next-label">Next send</p>
          ${
            next
              ? `<div class="next-row">${badge(next.post)}<div>
                   <h1 class="next-clan">${esc(clanName(next.post))}</h1>
                   <p class="next-when"><b data-countdown="${next.at.toISOString()}">in ${countdown(next.at - Date.now())}</b>
                   · ${dayLabel(next.at)} at ${clock(next.at)}</p></div></div>`
              : `<h1 class="next-clan">Nothing scheduled</h1>`
          }
        </div>
        <div class="summary-actions">
          <ul class="counts">
            <li><b>${counts.active}</b><span>Active</span></li>
            <li><b>${counts.paused}</b><span>Paused</span></li>
            <li class="${counts.error ? "is-error" : ""}"><b>${counts.error}</b><span>Errors</span></li>
          </ul>
          <button class="btn primary" data-action="new">${icon("plus")} New post</button>
        </div>
      </section>
      ${renderTimeline(next)}
      <section aria-labelledby="posts-title" style="display:grid;gap:16px">
        <div class="toolbar">
          <h2 id="posts-title">Posts</h2>
          <div class="filters" role="group" aria-label="Show">
            ${["all", "active", "paused", "error"]
              .map((f) => `<button data-filter="${f}" aria-pressed="${state.filter === f}">${{ all: "All", active: "Active", paused: "Paused", error: "Errors" }[f]}</button>`)
              .join("")}
          </div>
        </div>
        ${renderCards()}
      </section>
    </main>`;
}

function renderTimeline(next) {
  if (!state.posts.length) return "";
  const pct = (date) => ((date.getHours() * 60 + date.getMinutes()) / 1440) * 100;
  // One marker per send time of every post. Paused posts show dimmed at their usual time.
  const marks = [];
  for (const post of state.posts) {
    post.next_sends.forEach((iso, i) => {
      const at = new Date(iso);
      marks.push({ post, at, left: pct(at), time: post.times[i], isNext: next && next.post === post && +next.at === +at });
    });
  }
  marks.sort((a, b) => a.left - b.left);
  // Stack markers that would overlap into extra rows.
  const rowEnds = [];
  for (const m of marks) {
    let row = rowEnds.findIndex((end) => m.left - end > 3.2);
    if (row === -1) row = rowEnds.length;
    rowEnds[row] = m.left;
    m.row = row;
  }
  const rows = Math.max(1, rowEnds.length);
  const now = new Date();
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const hours = [0, 3, 6, 9, 12, 15, 18, 21, 24]
    .map((h) => `<span style="left:${(h / 24) * 100}%">${h === 0 || h === 24 ? "12a" : h === 12 ? "12p" : h < 12 ? `${h}a` : `${h - 12}p`}</span>`)
    .join("");
  return `
    <section class="panel" aria-labelledby="day-title">
      <div class="panel-head"><h2 id="day-title">Daily schedule</h2><p>Your time (${esc(tzShort(zone))})</p></div>
      <div class="timeline">
        <div class="track" style="--rows:${rows}">
          <div class="night" style="left:0;width:25%"></div>
          <div class="now-line" style="left:${pct(now)}%"><span>Now</span></div>
          ${marks
            .map((m) => {
              const cls = ["marker", m.isNext ? "is-next" : "", `is-${status(m.post)}`].join(" ");
              const label = `${clanName(m.post)}, ${clock(m.at)}${m.post.enabled ? "" : ", paused"}. Edit`;
              const inner = m.post.clan?.badge ? `<img src="${esc(m.post.clan.badge)}" alt="">` : esc(initials(clanName(m.post)));
              return `<button class="${cls}" style="left:${m.left}%;bottom:${10 + m.row * 40}px" data-edit="${esc(m.post.id)}" aria-label="${esc(label)}" title="${esc(`${clanName(m.post)} · ${clock(m.at)}`)}">${inner}</button>`;
            })
            .join("")}
        </div>
        <div class="hours" aria-hidden="true">${hours}</div>
      </div>
    </section>`;
}

function renderCards() {
  if (!state.posts.length) {
    return `<div class="empty"><h3>No scheduled posts yet</h3><p>Add one and the bot posts it every day at the times you pick.</p>
      <button class="btn primary" data-action="new">${icon("plus")} New post</button></div>`;
  }
  const order = { active: 0, error: 1, paused: 2 };
  const firstSend = (p) => Math.min(...p.next_sends.map((s) => +new Date(s)));
  const posts = state.posts
    .filter((p) => state.filter === "all" || status(p) === state.filter)
    .sort((a, b) => order[status(a)] - order[status(b)] || firstSend(a) - firstSend(b));
  if (!posts.length) return `<div class="empty"><p>No ${state.filter === "error" ? "posts with errors" : `${state.filter} posts`}.</p></div>`;
  return `<div class="grid">${posts.map(renderCard).join("")}</div>`;
}

function renderCard(post) {
  const st = status(post);
  const tz = tzShort(post.timezone);
  const user = post.user?.name || post.discord_id;
  const channel = post.channel?.name ? `#${post.channel.name}` : post.channel_id;
  return `
    <article class="card is-${st}" aria-labelledby="t-${esc(post.id)}">
      <div class="card-head">
        ${badge(post)}
        <div class="card-title">
          <h3 id="t-${esc(post.id)}"><button data-edit="${esc(post.id)}">${esc(clanName(post))}</button></h3>
          <p>${esc(post.clan_tag || "")}</p>
        </div>
        <span class="chip ${st}">${{ active: "Active", paused: "Paused", error: "Error" }[st]}</span>
      </div>
      <ul class="card-times" aria-label="Sends daily at">
        ${post.times.map((t) => `<li>${icon("clock")}${hhmmLabel(t)} <small>${esc(tz)}</small></li>`).join("")}
      </ul>
      <dl class="meta">
        <dt>Posts as</dt><dd>${esc(user)}</dd>
        <dt>Channel</dt><dd>${esc(channel)}</dd>
        <dt>Last sent</dt><dd>${esc(lastSent(post.last_posted))}</dd>
      </dl>
      ${post.error ? `<p class="card-error">${icon("alert")}<span>${esc(post.error)}</span></p>` : ""}
      <div class="card-actions">
        <button class="btn" data-edit="${esc(post.id)}">${icon("pencil")} Edit</button>
        <button class="btn" data-toggle="${esc(post.id)}">${post.enabled ? `${icon("pause")} Pause` : `${icon("play")} Resume`}</button>
      </div>
    </article>`;
}

// ---------- editor ----------

function blankForm() {
  return {
    discord_id: "",
    clan_tag: "",
    channel_id: state.defaultChannel,
    times: ["09:00"],
    timezone: "America/New_York",
    enabled: true,
    content: { description: "", image_url: "", discord_link: "" },
    saved_content: null,
  };
}

async function openEditor(post) {
  const form = post
    ? {
        discord_id: post.discord_id,
        clan_tag: post.clan_tag || "",
        channel_id: post.channel_id,
        times: [...post.times],
        timezone: post.timezone,
        enabled: post.enabled,
        content: { ...post.content },
        saved_content: post.has_template ? post.saved_content : null,
      }
    : blankForm();
  const editing = { post, form, errors: {}, message: "", saving: false, confirmDelete: false };
  state.editing = editing;
  // Open at once; the template list fills in when it arrives.
  renderEditor();
  const dialog = $("#editor");
  if (!dialog.open) dialog.showModal();
  if (post?.clan_tag) checkClan(post.clan_tag);
  if (state.templates === null) {
    try {
      state.templates = (await api("GET", "/api/templates")).templates;
    } catch (err) {
      toast(err.message, true);
      return;
    }
    if (state.editing !== editing) return;
    readForm();
    renderEditor();
  }
}

function closeEditor() {
  $("#editor").close();
}

function fieldError(name) {
  const error = state.editing.errors[name];
  return error ? `<span class="field-error" id="err-${name}">${esc(error)}</span>` : "";
}
const invalid = (name) => (state.editing.errors[name] ? `aria-invalid="true" aria-describedby="err-${name}"` : "");

function renderEditor() {
  const { post, form, message, saving, confirmDelete } = state.editing;
  const templates = [...(state.templates || [])];
  // Until the list loads (or if this user has no template), keep the current user selectable.
  if (form.discord_id && form.discord_id !== "__other" && !templates.some((t) => t.discord_id === form.discord_id)) {
    templates.unshift({ discord_id: form.discord_id, user: post?.user, clan_tag: post?.clan_tag });
  }
  const known = templates.some((t) => t.discord_id === form.discord_id);
  const choosingOther = form.discord_id === "__other" || (form.discord_id && !known);
  const tzKnown = TIMEZONES.some(([z]) => z === form.timezone);
  const isCustom = form.saved_content && ["description", "image_url", "discord_link"].some((f) => form.content[f] !== form.saved_content[f]);
  const ownerName = templates.find((t) => t.discord_id === form.discord_id)?.user?.name || post?.user?.name || "this user";

  $("#editor").innerHTML = `
    <form class="editor" novalidate>
      <div class="editor-head">
        <h2 id="editor-title">${post ? `Edit ${esc(clanName(post))}` : "New scheduled post"}</h2>
        <button type="button" class="btn ghost icon-only" data-action="close" aria-label="Close">${icon("x")}</button>
      </div>
      <div class="editor-body">
        ${message ? `<p class="form-error" role="alert">${esc(message)}</p>` : ""}

        <fieldset>
          <legend>When</legend>
          <div class="switch-row">
            <div><span class="field-label" id="enabled-label">Sending</span><p class="hint">Off pauses it without deleting it.</p></div>
            <label class="switch"><input type="checkbox" name="enabled" role="switch" aria-labelledby="enabled-label" ${form.enabled ? "checked" : ""}><span></span></label>
          </div>
          <div class="field">
            <span class="field-label" id="times-label">Sends every day at</span>
            <div class="times" role="group" aria-labelledby="times-label">
              ${form.times
                .map(
                  (t, i) => `<div class="time-row">
                    <input type="time" name="time" data-index="${i}" value="${esc(t)}" aria-label="Send time ${i + 1}" required ${invalid("times")}>
                    ${form.times.length > 1 ? `<button type="button" class="btn icon-only" data-remove-time="${i}" aria-label="Remove ${hhmmLabel(t)}">${icon("trash")}</button>` : ""}
                  </div>`,
                )
                .join("")}
            </div>
            ${fieldError("times")}
            <div class="row-actions">
              ${form.times.length < 6 ? `<button type="button" class="btn" data-action="add-time">${icon("plus")} Add time</button>` : ""}
              ${form.times.length === 1 ? `<button type="button" class="btn" data-action="add-12h">${icon("plus")} Twice a day (+12h)</button>` : ""}
            </div>
          </div>
          <div class="field">
            <label for="f-tz">Timezone</label>
            <select id="f-tz" name="timezone" ${invalid("timezone")}>
              ${tzKnown ? "" : `<option value="${esc(form.timezone)}" selected>${esc(form.timezone)}</option>`}
              ${TIMEZONES.map(([z, label]) => `<option value="${z}" ${z === form.timezone ? "selected" : ""}>${label} (${esc(tzShort(z))})</option>`).join("")}
            </select>
            ${fieldError("timezone")}
          </div>
        </fieldset>

        <fieldset>
          <legend>Where</legend>
          <div class="field">
            <label for="f-user">Posts as</label>
            <select id="f-user" name="discord_user" ${invalid("discord_id")}>
              <option value="" ${form.discord_id ? "" : "selected"} disabled>Pick a saved /post-clan template</option>
              ${templates
                .map((t) => `<option value="${esc(t.discord_id)}" ${t.discord_id === form.discord_id ? "selected" : ""}>${esc(t.user?.name || t.discord_id)}${t.clan_tag ? ` · ${esc(t.clan_tag)}` : ""}</option>`)
                .join("")}
              <option value="__other" ${choosingOther ? "selected" : ""}>Someone else (enter Discord user ID)</option>
            </select>
            ${
              choosingOther
                ? `<input type="text" name="discord_id" inputmode="numeric" autocomplete="off" placeholder="Discord user ID" value="${esc(form.discord_id === "__other" ? "" : form.discord_id)}" aria-label="Discord user ID" ${invalid("discord_id")}>`
                : ""
            }
            <span class="hint">The post says "Posted by" this person.</span>
            ${fieldError("discord_id")}
          </div>
          <div class="two">
            <div class="field">
              <label for="f-tag">Clan tag</label>
              <input id="f-tag" type="text" name="clan_tag" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="#2PYLUR2PV" value="${esc(form.clan_tag)}" ${invalid("clan_tag")}>
              <span class="clan-check" id="clan-check" aria-live="polite"></span>
              ${fieldError("clan_tag")}
            </div>
            <div class="field">
              <label for="f-channel">Channel ID</label>
              <input id="f-channel" type="text" name="channel_id" inputmode="numeric" autocomplete="off" value="${esc(form.channel_id)}" ${invalid("channel_id")}>
              <span class="hint">${post?.channel?.name && post.channel_id === form.channel_id ? `#${esc(post.channel.name)}` : form.channel_id === state.defaultChannel ? "Recruitment channel" : ""}</span>
              ${fieldError("channel_id")}
            </div>
          </div>
        </fieldset>

        <fieldset>
          <legend>Post</legend>
          <div class="source">
            <span>${form.saved_content ? (isCustom ? "Custom text for this post" : `From ${esc(ownerName)}'s saved template`) : "Saved as a new template for this user"}</span>
            ${isCustom ? `<button type="button" class="linkish" data-action="reset-content">Use saved template</button>` : ""}
          </div>
          <div class="field">
            <label for="f-desc">Description</label>
            <textarea id="f-desc" name="description" maxlength="1500" ${invalid("description")}>${esc(form.content.description)}</textarea>
            <span class="hint" id="desc-count">${form.content.description.length} / 1500</span>
            ${fieldError("description")}
          </div>
          <div class="field">
            <label for="f-img">Image URL <span class="hint">(optional)</span></label>
            <input id="f-img" type="url" name="image_url" placeholder="https://" value="${esc(form.content.image_url)}" ${invalid("image_url")}>
            ${fieldError("image_url")}
          </div>
          <div class="field">
            <label for="f-link">Discord invite link <span class="hint">(optional)</span></label>
            <input id="f-link" type="url" name="discord_link" placeholder="https://discord.gg/…" value="${esc(form.content.discord_link)}" ${invalid("discord_link")}>
            ${fieldError("discord_link")}
          </div>
          <details class="preview">
            <summary>Preview</summary>
            <div id="preview"></div>
          </details>
        </fieldset>
      </div>
      <div class="editor-foot">
        ${
          post
            ? `<button type="button" class="btn ${confirmDelete ? "danger" : "ghost"}" data-action="delete" ${saving ? "disabled" : ""}>${icon("trash")} ${confirmDelete ? "Confirm delete" : "Delete"}</button>`
            : ""
        }
        <span class="spacer"></span>
        <button type="button" class="btn" data-action="close">Cancel</button>
        <button type="submit" class="btn primary" ${saving ? "disabled" : ""}>${saving ? "Saving…" : post ? "Save" : "Add post"}</button>
      </div>
    </form>`;
  renderPreview();
}

function renderPreview() {
  const box = $("#preview");
  if (!box || !state.editing) return;
  const { form } = state.editing;
  const name = state.editing.clanName || (state.editing.post && clanName(state.editing.post)) || "Your clan";
  box.innerHTML = `
    <div class="discord">
      <div class="discord-box">
        <h4>⚔️ ${esc(name)} Recruitment</h4>
        <hr>
        <div class="stats">Clan tag, level, trophies, members and war stats fill in from the Clash API when it posts.</div>
        <hr>
        <strong>📋 About Our Clan</strong>
        <div class="desc">${esc(form.content.description) || '<span class="hint">No description yet</span>'}</div>
        ${form.content.image_url.startsWith("https://") ? `<img src="${esc(form.content.image_url)}" alt="Post image">` : ""}
        <div class="discord-buttons"><span>📱 Apply In-Game</span>${form.content.discord_link ? "<span>💬 Join Discord</span>" : ""}</div>
      </div>
    </div>`;
}

let clanTimer = null;
function checkClan(raw) {
  clearTimeout(clanTimer);
  const out = $("#clan-check");
  const tag = raw.trim().toUpperCase().replace(/^#/, "");
  if (!out) return;
  if (tag.length < 4) {
    out.className = "clan-check";
    out.textContent = "";
    return;
  }
  out.className = "clan-check";
  out.textContent = "Checking…";
  clanTimer = setTimeout(async () => {
    try {
      const { clan } = await api("GET", `/api/clans/${encodeURIComponent(tag)}`);
      if (!$("#clan-check")) return;
      if (clan && !clan.missing) {
        out.className = "clan-check ok";
        out.innerHTML = `${clan.badge ? `<img src="${esc(clan.badge)}" alt="">` : ""}${esc(clan.name)} · ${esc(clan.members)}/50 members`;
        state.editing.clanName = clan.name;
        renderPreview();
      } else if (clan?.missing) {
        out.className = "clan-check bad";
        out.textContent = "No clan has that tag.";
      } else {
        out.className = "clan-check";
        out.textContent = "Couldn't check the tag right now.";
      }
    } catch {
      out.textContent = "";
    }
  }, 450);
}

function readForm() {
  const f = state.editing.form;
  const el = $("#editor form");
  f.enabled = el.enabled.checked;
  f.times = [...el.querySelectorAll('input[name="time"]')].map((i) => i.value);
  f.timezone = el.timezone.value;
  const user = el.discord_user.value;
  f.discord_id = user === "__other" ? (el.discord_id ? el.discord_id.value.trim() : "__other") : user;
  f.clan_tag = el.clan_tag.value;
  f.channel_id = el.channel_id.value.trim();
  f.content = {
    description: el.description.value,
    image_url: el.image_url.value.trim(),
    discord_link: el.discord_link.value.trim(),
  };
}

function pickTemplate(discordId) {
  const f = state.editing.form;
  const template = (state.templates || []).find((t) => t.discord_id === discordId);
  f.discord_id = discordId;
  if (!template) {
    f.saved_content = null;
    return;
  }
  f.saved_content = { ...template.content };
  // A new post starts from the template. An existing post keeps its own text.
  if (!state.editing.post) {
    f.content = { ...template.content };
    if (!f.clan_tag && template.clan_tag) f.clan_tag = template.clan_tag;
  }
}

async function save() {
  readForm();
  const { post, form } = state.editing;
  state.editing.saving = true;
  state.editing.errors = {};
  state.editing.message = "";
  renderEditor();
  const body = {
    discord_id: form.discord_id === "__other" ? "" : form.discord_id,
    clan_tag: form.clan_tag,
    channel_id: form.channel_id,
    times: form.times,
    timezone: form.timezone,
    enabled: form.enabled,
    content: form.content,
  };
  try {
    const result = post ? await api("PUT", `/api/posts/${encodeURIComponent(post.id)}`, { ...body, rev: post.rev }) : await api("POST", "/api/posts", body);
    upsert(result.post);
    state.templates = null; // a new template may have been created
    closeEditor();
    toast(post ? "Saved. The bot picks it up within a minute." : "Added. The bot picks it up within a minute.");
  } catch (err) {
    state.editing.saving = false;
    state.editing.errors = err.data?.fields || {};
    state.editing.message = err.message;
    renderEditor();
    const firstBad = $('#editor [aria-invalid="true"]') || $("#editor .form-error");
    firstBad?.scrollIntoView({ block: "center" });
  }
}

async function remove() {
  const { post } = state.editing;
  if (!state.editing.confirmDelete) {
    readForm();
    state.editing.confirmDelete = true;
    renderEditor();
    $('#editor [data-action="delete"]').focus();
    return;
  }
  try {
    await api("DELETE", `/api/posts/${encodeURIComponent(post.id)}`);
    state.posts = state.posts.filter((p) => p.id !== post.id);
    closeEditor();
    render();
    toast(`Deleted ${clanName(post)}.`);
  } catch (err) {
    toast(err.message, true);
  }
}

function upsert(post) {
  const i = state.posts.findIndex((p) => p.id === post.id);
  if (i === -1) state.posts.push(post);
  else state.posts[i] = post;
  render();
}

async function toggle(id, button) {
  const post = state.posts.find((p) => p.id === id);
  button.disabled = true;
  try {
    const result = await api("POST", `/api/posts/${encodeURIComponent(id)}/enabled`, { enabled: !post.enabled });
    upsert(result.post);
    toast(result.post.enabled ? `${clanName(post)} resumed.` : `${clanName(post)} paused.`);
  } catch (err) {
    button.disabled = false;
    toast(err.message, true);
  }
}

let toastTimer = null;
function toast(text, bad = false) {
  const el = $("#toast");
  el.textContent = text;
  el.className = `show${bad ? " bad" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = ""), 3500);
}

// ---------- events ----------

document.addEventListener("click", (event) => {
  const target = event.target.closest("button, a");
  if (!target) return;
  const inEditor = target.closest("#editor");
  if (target.dataset.edit) return openEditor(state.posts.find((p) => p.id === target.dataset.edit));
  if (target.dataset.toggle) return toggle(target.dataset.toggle, target);
  if (target.dataset.filter) {
    state.filter = target.dataset.filter;
    return render();
  }
  if (target.dataset.removeTime) {
    readForm();
    state.editing.form.times.splice(Number(target.dataset.removeTime), 1);
    return renderEditor();
  }
  switch (target.dataset.action) {
    case "new":
      return openEditor(null);
    case "refresh":
      return load(true);
    case "logout":
      return api("POST", "/api/logout").finally(() => {
        state.user = null;
        renderLogin();
      });
    case "close":
      return closeEditor();
    case "add-time":
    case "add-12h": {
      readForm();
      const times = state.editing.form.times;
      let next = "21:00";
      if (target.dataset.action === "add-12h" || times.length) {
        const [h, m] = (times[times.length - 1] || "09:00").split(":").map(Number);
        const step = target.dataset.action === "add-12h" ? 12 : 1;
        next = `${String((h + step) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      }
      times.push(next);
      renderEditor();
      return $(`#editor input[data-index="${times.length - 1}"]`)?.focus();
    }
    case "reset-content":
      readForm();
      state.editing.form.content = { ...state.editing.form.saved_content };
      return renderEditor();
    case "delete":
      return remove();
  }
  if (inEditor && target.type === "submit") return; // handled by submit
});

document.addEventListener("submit", (event) => {
  if (!event.target.closest("#editor")) return;
  event.preventDefault();
  save();
});

function clearError(field) {
  // Once a field is changed, its old server error no longer applies.
  const key = { discord_user: "discord_id", time: "times" }[field.name] || field.name;
  if (!state.editing.errors[key]) return;
  delete state.editing.errors[key];
  $(`#err-${key}`)?.remove();
  $("#editor").querySelectorAll('[aria-invalid="true"]').forEach((el) => {
    if (el.getAttribute("aria-describedby") === `err-${key}`) el.removeAttribute("aria-invalid");
  });
}

document.addEventListener("input", (event) => {
  if (!state.editing || !event.target.closest("#editor")) return;
  const name = event.target.name;
  clearError(event.target);
  if (name === "clan_tag") checkClan(event.target.value);
  if (["description", "image_url", "discord_link"].includes(name)) {
    readForm();
    $("#desc-count").textContent = `${state.editing.form.content.description.length} / 1500`;
    renderPreview();
  }
});

document.addEventListener("change", (event) => {
  if (!state.editing || event.target.name !== "discord_user") return;
  readForm();
  pickTemplate(event.target.value);
  state.editing.errors = {};
  state.editing.message = "";
  renderEditor();
  if (event.target.value === "__other") $('#editor input[name="discord_id"]')?.focus();
  else $("#f-user")?.focus();
});

$("#editor")?.addEventListener("close", () => {
  state.editing = null;
});

// Keep the countdown and the "now" line current.
setInterval(() => {
  const el = document.querySelector("[data-countdown]");
  if (el) {
    const ms = new Date(el.dataset.countdown) - Date.now();
    if (ms <= 0 && !state.editing) return load(false);
    el.textContent = `in ${countdown(ms)}`;
  }
}, 20000);

// ---------- start ----------

async function load(announce) {
  try {
    const data = await api("GET", "/api/posts");
    state.posts = data.posts;
    state.defaultChannel = data.default_channel;
    if (!state.editing) render();
    if (announce) toast("Up to date.");
  } catch (err) {
    if (err.status !== 401) toast(err.message, true);
  }
}

async function boot() {
  try {
    const data = await api("GET", "/api/me");
    if (!data.user) return renderLogin();
    state.user = data.user;
    state.csrf = data.csrf;
    if (location.search) history.replaceState(null, "", "/");
    await load(false);
  } catch (err) {
    $("#app").innerHTML = `<p class="boot">${esc(err.message)}</p>`;
  }
}

boot();
