const API = "/api/admin";

function $(sel, root = document) { return root.querySelector(sel); }
function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function api(path, opts) {
  const res = await fetch(API + path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.message || `API ${path} failed: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return body;
}

function showView(view) {
  $("#view-login").classList.toggle("active", view === "login");
  $("#view-dashboard").classList.toggle("active", view === "dashboard");
  $("#account-chip").style.display = view === "dashboard" ? "flex" : "none";
}

async function refreshGate() {
  const data = await api("/me");
  if (data.admin) {
    showView("dashboard");
    loadAll();
  } else {
    showView("login");
  }
}

function wireEvents() {
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#login-error").textContent = "";
    const email = $("#login-email").value.trim();
    const password = $("#login-password").value;
    const btn = $("#login-submit");
    btn.disabled = true;
    try {
      await api("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      showView("dashboard");
      loadAll();
    } catch (err) {
      $("#login-error").textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  $("#admin-logout").addEventListener("click", async () => {
    await api("/logout", { method: "POST" });
    $("#login-form").reset();
    showView("login");
  });

  let searchTimer = null;
  $("#user-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadUsers(e.target.value.trim()), 250);
  });
}

async function loadAll() {
  await Promise.all([loadStats(), loadUsers(""), loadActivity(), loadTopStocks()]);
}

async function loadStats() {
  const s = await api("/stats");
  const row1 = $("#stat-tiles");
  const row2 = $("#stat-tiles-2");
  row1.innerHTML = "";
  row2.innerHTML = "";
  const tiles1 = [
    { label: "Total Users", value: s.total_users, cls: "" },
    { label: "Subscribed", value: s.subscribed, cls: "good" },
    { label: "Free", value: s.free, cls: "" },
    { label: "Active (7d)", value: s.active_7d, cls: "good" },
  ];
  const tiles2 = [
    { label: "Signups Today", value: s.signups_today, cls: "" },
    { label: "Signups (7d)", value: s.signups_7d, cls: "" },
    { label: "Backtests (7d)", value: s.backtests_7d, cls: "" },
  ];
  row2.style.gridTemplateColumns = "repeat(3, 1fr)";
  for (const t of tiles1) {
    row1.appendChild(el("div", { class: `stat-tile ${t.cls}` }, [
      el("div", { class: "label" }, t.label),
      el("div", { class: "value tabular" }, String(t.value)),
    ]));
  }
  for (const t of tiles2) {
    row2.appendChild(el("div", { class: `stat-tile ${t.cls}` }, [
      el("div", { class: "label" }, t.label),
      el("div", { class: "value tabular" }, String(t.value)),
    ]));
  }
}

async function loadTopStocks() {
  const s = await api("/stats");
  const wrap = $("#top-stocks");
  wrap.innerHTML = "";
  if (!s.top_stocks_7d.length) { wrap.appendChild(el("div", { class: "empty-state" }, "No stock views yet.")); return; }
  for (const t of s.top_stocks_7d) {
    wrap.appendChild(el("div", { class: "activity-item" }, [
      el("span", { class: "email" }, t.ticker),
      el("span", { class: "time" }, `${t.views} view${t.views === 1 ? "" : "s"}`),
    ]));
  }
}

async function loadUsers(q) {
  const data = await api(`/users?q=${encodeURIComponent(q || "")}`);
  const tbody = $("#users-tbody");
  tbody.innerHTML = "";
  if (!data.users.length) {
    tbody.appendChild(el("tr", {}, [el("td", { colspan: "6" }, [el("div", { class: "empty-state" }, "No users found.")])]));
    return;
  }
  for (const u of data.users) {
    tbody.appendChild(el("tr", {}, [
      el("td", { class: "email" }, u.email),
      el("td", {}, fmtDate(u.created_at)),
      el("td", { html: `<span class="status-pill ${u.subscribed ? "subscribed" : "free"}">${u.subscribed ? "Subscribed" : "Free"}</span>` }),
      el("td", {}, u.plan || "—"),
      el("td", {}, fmtDateTime(u.last_active_at)),
      el("td", {}, [
        el("button", {
          class: "btn",
          onclick: async (e) => {
            e.target.disabled = true;
            await api(`/users/${u.id}/toggle-subscription`, { method: "POST" });
            await Promise.all([loadUsers($("#user-search").value.trim()), loadStats(), loadActivity()]);
          },
        }, u.subscribed ? "Revoke" : "Grant"),
      ]),
    ]));
  }
}

const EVENT_LABELS = {
  signup: "Signup", login: "Login", subscribe: "Subscribed", unsubscribe: "Unsubscribed",
  backtest_run: "Backtest", admin_login: "Admin login", admin_toggle_subscription: "Admin action",
  scan: "Scan", stock_view: "Stock view", tab_view: "Tab view",
};

async function loadActivity() {
  const data = await api("/activity?limit=150");
  const wrap = $("#activity-feed");
  wrap.innerHTML = "";
  if (!data.activity.length) { wrap.appendChild(el("div", { class: "empty-state" }, "No activity yet.")); return; }
  for (const a of data.activity) {
    wrap.appendChild(el("div", { class: "activity-item" }, [
      el("div", { class: "left" }, [
        el("span", { class: `activity-tag ${a.event_type}` }, EVENT_LABELS[a.event_type] || a.event_type),
        el("span", { class: "email" }, a.email || "—"),
        a.detail ? el("span", { class: "detail" }, `· ${a.detail}`) : null,
      ]),
      el("span", { class: "time" }, fmtDateTime(a.created_at)),
    ]));
  }
}

wireEvents();
refreshGate();
