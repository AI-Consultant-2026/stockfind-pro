// StockFind Pro — dashboard frontend. Vanilla JS, no build step; talks to the
// Flask API under /api/*. Organized as: state, API helpers, render functions
// per panel, a small SVG line-chart renderer for the backtest equity curve,
// and event wiring at the bottom.

const API = "/api";

const state = {
  view: "scanner",
  mode: "all",
  strategyId: null,
  sector: "",
  qualifyingOnly: true,
  strategiesMeta: [],
  modesMeta: [],
  universe: [],
  lastScan: null,
  btRulesMode: "strategy",
  user: null,
  dashboardLoaded: false,
};

// ---------------------------------------------------------------- helpers --
function $(sel, root = document) { return root.querySelector(sel); }
function $all(sel, root = document) { return [...root.querySelectorAll(sel)]; }
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
function fmtNum(v, digits = 1) { return v == null ? "—" : Number(v).toFixed(digits); }
function fmtPct(v, digits = 1) { return v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(digits)}%`; }
// For fields that arrive as a fraction (0.12 = 12%) and may be null — avoids
// `null * 100 -> 0` silently rendering "+0.0%" for genuinely missing data.
function pctField(v, digits = 1) { return v == null ? "—" : fmtPct(v * 100, digits); }
function fmtMoney(v) {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${Number(v).toFixed(2)}`;
}
function scoreClass(v) {
  if (v == null) return "";
  if (v >= 70) return "good";
  if (v >= 40) return "warning";
  return "critical";
}
function tierBadgeHtml(tier, label) {
  return `<span class="tier-badge ${tier}">${tier === "green" ? "🟢" : tier === "amber" ? "🟠" : "🔴"} ${label}</span>`;
}

async function api(path, opts) {
  const res = await fetch(API + path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 || res.status === 402) {
      // Session expired or subscription lapsed mid-visit — re-check and swap
      // to the right gate screen instead of leaving the dashboard half-loaded.
      refreshAuthGate();
    }
    const err = new Error(body.message || `API ${path} failed: ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

// ------------------------------------------------------------ view switch --
function switchView(view) {
  state.view = view;
  $all(".nav-tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
  $all(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view === "sectors") loadSectors();
  if (view === "backtest") loadRunHistory();
}

// ------------------------------------------------------------- bootstrap --
async function initDashboard() {
  wireStaticEvents();
  const meta = await api("/strategies");
  state.strategiesMeta = meta.strategies;
  state.modesMeta = meta.modes;
  buildModeSwitch();
  buildStrategyChips();

  const uni = await api("/universe");
  state.universe = uni.companies;
  buildSectorFilterOptions();
  buildBacktestFormOptions();

  await loadScan();
  await loadRadar();
}

function buildModeSwitch() {
  const wrap = $("#mode-switch");
  wrap.innerHTML = "";
  for (const m of state.modesMeta) {
    const btn = el("button", {
      class: "mode-btn" + (m.id === state.mode ? " active" : ""),
      title: m.description || "",
      onclick: () => { state.mode = m.id; state.strategyId = null; buildStrategyChips(); refreshScanOnly(); },
    }, m.label);
    btn.dataset.mode = m.id;
    wrap.appendChild(btn);
  }
}

function buildStrategyChips() {
  const wrap = $("#strategy-chips");
  wrap.innerHTML = "";
  const visible = state.mode === "all" ? state.strategiesMeta : state.strategiesMeta.filter((s) => s.modes.includes(state.mode));
  const allChip = el("button", {
    class: "chip" + (state.strategyId === null ? " active" : ""),
    onclick: () => { state.strategyId = null; buildStrategyChips(); refreshScanOnly(); },
  }, "All Strategies");
  wrap.appendChild(allChip);
  for (const s of visible) {
    const chip = el("button", {
      class: "chip" + (state.strategyId === s.strategy_id ? " active" : ""),
      title: s.description,
      onclick: () => { state.strategyId = s.strategy_id; buildStrategyChips(); refreshScanOnly(); },
    }, `${s.badge.split(" ")[0]} ${s.short}`);
    wrap.appendChild(chip);
  }
}

function buildSectorFilterOptions() {
  const sectors = [...new Set(state.universe.map((c) => c.sector))].sort();
  for (const sel of [$("#sector-filter"), $("#bt-sector")]) {
    for (const s of sectors) sel.appendChild(el("option", { value: s }, s));
  }
  $("#sector-filter").addEventListener("change", (e) => { state.sector = e.target.value; refreshScanOnly(); });
  $("#qualifying-toggle").addEventListener("change", (e) => { state.qualifyingOnly = e.target.checked; refreshScanOnly(); });
}

function buildBacktestFormOptions() {
  const sel = $("#bt-strategy");
  for (const s of state.strategiesMeta) sel.appendChild(el("option", { value: s.strategy_id }, s.label));
  const today = new Date().toISOString().slice(0, 10);
  $("#bt-end").value = today;
}

function wireStaticEvents() {
  $all(".nav-tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
  $("#modal-overlay").addEventListener("click", (e) => { if (e.target.id === "modal-overlay") closeModal(); });
  $all(".rules-toggle button").forEach((b) => b.addEventListener("click", () => {
    state.btRulesMode = b.dataset.mode;
    $all(".rules-toggle button").forEach((x) => x.classList.toggle("active", x === b));
    $("#strategy-select-field").style.display = state.btRulesMode === "strategy" ? "" : "none";
    $("#custom-rules-summary").style.display = state.btRulesMode === "custom" ? "" : "none";
  }));
  $("#bt-run").addEventListener("click", runBacktest);
}

// ------------------------------------------------------------ scan/render --
async function loadScan() {
  const data = await fetchScan();
  state.lastScan = data;
  renderAsOfBanner(data.as_of);
  renderStatTiles(data.counts);
  renderHero(data.results[0]);
  renderOppList(data.results);
}

async function refreshScanOnly() {
  const data = await fetchScan();
  state.lastScan = data;
  renderStatTiles(data.counts);
  renderHero(data.results[0]);
  renderOppList(data.results);
}

function fetchScan() {
  const params = new URLSearchParams();
  if (state.mode !== "all") params.set("mode", state.mode);
  if (state.strategyId) params.set("strategy", state.strategyId);
  if (state.sector) params.set("sector", state.sector);
  params.set("qualifying_only", state.qualifyingOnly);
  params.set("limit", "60");
  return api(`/scan?${params.toString()}`);
}

function renderAsOfBanner(asOf) {
  $("#asof-banner").innerHTML = `<strong>Point-in-time scan as of ${asOf}.</strong> Running entirely on simulated market data (see README) — every score below is a deterministic quant calculation, not a prediction.`;
  $("#as-of-label").textContent = `As of ${asOf}`;
}

function renderStatTiles(counts) {
  const wrap = $("#stat-tiles");
  wrap.innerHTML = "";
  const tiles = [
    { label: "🟢 High-Conviction Setups", value: counts.high_conviction, cls: "good" },
    { label: "🟠 Watch Setups", value: counts.watch, cls: "warning" },
    { label: "🔴 Risk Warnings", value: counts.risk_warning, cls: "critical" },
    { label: "Total Scanned", value: counts.total_scanned, cls: "" },
  ];
  for (const t of tiles) {
    wrap.appendChild(el("div", { class: `stat-tile ${t.cls}` }, [
      el("div", { class: "label" }, t.label),
      el("div", { class: "value tabular" }, String(t.value)),
    ]));
  }
}

function subscoreCell(k, v) {
  return el("div", { class: "subscore" }, [
    el("div", { class: "k" }, k),
    el("div", { class: `v ${scoreClass(v)}` }, fmtNum(v, 0)),
  ]);
}

function renderHero(opp) {
  const host = $("#hero-content");
  host.innerHTML = "";
  if (!opp) { host.appendChild(el("div", { class: "empty-state" }, "No opportunities match the current filters.")); return; }
  const s = opp.scores;
  const conv = opp.convergence;
  const exp = opp.explanation;

  const head = el("div", { class: "hero-head" }, [
    el("div", {}, [
      el("div", { class: "hero-ticker", onclick: () => openStockModal(opp.ticker), style: "cursor:pointer;" }, `${opp.ticker} — ${opp.name}`),
      el("div", { class: "hero-name" }, `${opp.sector} · ${opp.industry} · $${fmtNum(opp.price, 2)}`),
      el("div", { html: tierBadgeHtml(opp.overall_signal.tier, opp.overall_signal.label) }),
    ]),
    el("div", { class: "hero-score" }, [
      el("div", { class: "num tabular" }, fmtNum(opp.display_score, 0)),
      el("div", { class: "of100" }, "/ 100"),
    ]),
  ]);

  const subgrid = el("div", { class: "subscore-grid" }, [
    subscoreCell("Quality", s.quality), subscoreCell("Growth", s.growth), subscoreCell("Momentum", s.momentum),
    subscoreCell("Value", s.value), subscoreCell("Cash Flow", s.cash_flow), subscoreCell("Catalyst", s.catalyst),
    subscoreCell("Risk", s.risk),
  ]);

  const convBlock = el("div", { class: "convergence-block" }, [
    el("div", { class: "convergence-label" }, [
      el("span", {}, "SIGNAL CONVERGENCE"),
      el("span", { class: "tabular" }, `${conv.positive_count} of ${conv.total} signals · ${fmtNum(conv.convergence_pct, 0)}%`),
    ]),
    el("div", { class: "convergence-bar" }, [el("div", { class: "convergence-fill", style: `width:${conv.convergence_pct}%;` })]),
  ]);

  const whyGrid = el("div", { class: "why-grid" }, [
    el("div", { class: "why-col" }, [el("h4", {}, "Why?"), el("ul", { class: "why-list good" }, exp.why.map((w) => el("li", {}, w)))]),
    el("div", { class: "why-col" }, [el("h4", {}, "Why Not?"), el("ul", { class: "why-list warn" }, exp.why_not.map((w) => el("li", {}, w)))]),
  ]);

  const concern = el("div", { class: "concern-box" }, [el("strong", {}, "Main concern: "), exp.main_concern]);

  const badges = el("div", { class: "badge-row" }, opp.qualifying_strategies.map((q) => el("span", { class: "mini-badge" }, q.badge)));

  const actions = el("div", { class: "action-row" }, [
    el("button", { class: "btn primary", onclick: () => toast(`${opp.ticker} added to research list.`) }, "🟢 Add to Research List"),
    el("button", { class: "btn", onclick: () => openStockModal(opp.ticker) }, "View Full Detail"),
  ]);

  host.appendChild(head);
  host.appendChild(badges);
  host.appendChild(subgrid);
  host.appendChild(convBlock);
  host.appendChild(whyGrid);
  host.appendChild(concern);
  host.appendChild(actions);
}

function renderOppList(results) {
  const wrap = $("#opp-list");
  wrap.innerHTML = "";
  if (!results.length) { wrap.appendChild(el("div", { class: "empty-state" }, "No opportunities match the current filters.")); return; }
  results.forEach((opp, i) => {
    const s = opp.scores;
    const card = el("div", { class: "opp-card", onclick: () => openStockModal(opp.ticker) }, [
      el("div", { class: "opp-rank-score" }, [
        el("div", { class: `num tabular ${scoreClass(opp.display_score)}` }, fmtNum(opp.display_score, 0)),
        el("div", { class: "lbl" }, `#${i + 1}`),
      ]),
      el("div", { class: "opp-main" }, [
        el("div", { class: "ticker-row" }, [
          el("span", { class: "ticker" }, opp.ticker), el("span", { class: "name" }, opp.name),
        ]),
        el("div", { class: "headline" }, opp.top_strategy ? opp.top_strategy.headline : ""),
        el("div", { class: "badge-row" }, opp.qualifying_strategies.slice(0, 3).map((q) => el("span", { class: "mini-badge" }, q.badge))),
      ]),
      el("div", { class: "opp-subscores" }, [
        subMini("Q", s.quality), subMini("G", s.growth), subMini("M", s.momentum), subMini("V", s.value), subMini("R", s.risk),
      ]),
      el("div", { class: "opp-conv" }, [
        el("div", { class: "conv-label" }, "Convergence"),
        el("div", { class: `tabular ${scoreClass(opp.convergence.convergence_pct)}`, style: "font-weight:700;" }, `${fmtNum(opp.convergence.convergence_pct, 0)}%`),
        el("div", { html: tierBadgeHtml(opp.overall_signal.tier, opp.overall_signal.label) }),
      ]),
    ]);
    wrap.appendChild(card);
  });
}
function subMini(k, v) {
  return el("div", { class: "mini" }, [el("div", { class: "k" }, k), el("div", { class: `v ${scoreClass(v)}` }, fmtNum(v, 0))]);
}

// --------------------------------------------------------------- radar ----
async function loadRadar() {
  const data = await api("/radar");
  const wrap = $("#radar-feed");
  wrap.innerHTML = "";
  if (!data.signal_feed.length) { wrap.appendChild(el("div", { class: "empty-state" }, "No active signals.")); return; }
  for (const item of data.signal_feed) {
    wrap.appendChild(el("div", { class: "radar-item", onclick: () => openStockModal(item.ticker) }, [
      el("div", { class: "left" }, [
        el("span", { class: "ticker" }, item.ticker),
        el("span", { class: "badge-txt" }, item.badge),
      ]),
      el("span", { class: `score tabular ${scoreClass(item.opportunity_score)}` }, fmtNum(item.opportunity_score, 0)),
    ]));
  }
}

// -------------------------------------------------------------- sectors ---
async function loadSectors() {
  const data = await api("/sectors");
  const wrap = $("#sector-bars");
  wrap.innerHTML = "";
  const max = Math.max(...data.sectors.map((s) => s.momentum_score), 1);
  data.sectors.forEach((s, i) => {
    const color = `var(--series-${(i % 8) + 1})`;
    wrap.appendChild(el("div", { class: "sector-bar-row" }, [
      el("div", { class: "name" }, s.sector),
      el("div", { class: "sector-bar-track" }, [el("div", { class: "sector-bar-fill", style: `width:${(s.momentum_score / max) * 100}%; background:${color};` })]),
      el("div", { class: "val tabular" }, fmtNum(s.momentum_score, 0)),
    ]));
  });
}

// ------------------------------------------------------------- toast ------
function toast(msg) {
  const t = el("div", {
    style: "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--surface-2);border:1px solid var(--border-strong);padding:10px 18px;border-radius:8px;font-size:13px;z-index:200;",
  }, msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2200);
}

// -------------------------------------------------------- auth / paywall --
function showGateView(view) {
  // view is one of: "auth", "paywall", "app"
  $("#view-auth").classList.toggle("active", view === "auth");
  $("#view-paywall").classList.toggle("active", view === "paywall");
  $("#view-app").classList.toggle("active", view === "app");
  $("#account-chip").style.display = view === "auth" ? "none" : "flex";
}

function renderAccountChip() {
  if (!state.user) return;
  $("#account-email").textContent = state.user.email;
  $("#paywall-email").textContent = state.user.email;
}

async function refreshAuthGate() {
  const data = await api("/auth/me");
  state.user = data.user;
  if (!state.user) {
    showGateView("auth");
    return;
  }
  renderAccountChip();
  if (!state.user.subscribed) {
    showGateView("paywall");
    return;
  }
  showGateView("app");
  if (!state.dashboardLoaded) {
    state.dashboardLoaded = true;
    await initDashboard();
  }
}

function wireAuthEvents() {
  let authMode = "login";
  $all("#view-auth .gate-tabs button").forEach((b) => b.addEventListener("click", () => {
    authMode = b.dataset.authmode;
    $all("#view-auth .gate-tabs button").forEach((x) => x.classList.toggle("active", x === b));
    $("#auth-submit").textContent = authMode === "login" ? "Log In" : "Sign Up";
    $("#auth-error").textContent = "";
  }));

  $("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#auth-error").textContent = "";
    const email = $("#auth-email").value.trim();
    const password = $("#auth-password").value;
    const btn = $("#auth-submit");
    btn.disabled = true;
    try {
      const data = await api(`/auth/${authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      state.user = data.user;
      renderAccountChip();
      showGateView(state.user.subscribed ? "app" : "paywall");
      if (state.user.subscribed && !state.dashboardLoaded) {
        state.dashboardLoaded = true;
        await initDashboard();
      }
    } catch (err) {
      $("#auth-error").textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  $all("[data-plan]").forEach((b) => b.addEventListener("click", async () => {
    $("#paywall-error").textContent = "";
    b.disabled = true;
    try {
      const data = await api("/auth/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: b.dataset.plan }),
      });
      state.user = data.user;
      showGateView("app");
      if (!state.dashboardLoaded) {
        state.dashboardLoaded = true;
        await initDashboard();
      }
    } catch (err) {
      $("#paywall-error").textContent = err.message;
    } finally {
      b.disabled = false;
    }
  }));

  async function doLogout(e) {
    if (e) e.preventDefault();
    await api("/auth/logout", { method: "POST" });
    state.user = null;
    state.dashboardLoaded = false;
    $("#auth-form").reset();
    showGateView("auth");
  }
  $("#account-logout").addEventListener("click", doLogout);
  $("#paywall-logout").addEventListener("click", doLogout);
}

async function bootstrap() {
  wireAuthEvents();
  await refreshAuthGate();
}

bootstrap();

// ---------------------------------------------------------- stock modal ---
let modalState = { detail: null, activeStrategy: null };

async function openStockModal(ticker) {
  const overlay = $("#modal-overlay");
  overlay.classList.add("open");
  $("#modal-content").innerHTML = '<div class="loading-row"><span class="spinner"></span> Loading detail…</div>';
  try {
    const detail = await api(`/stock/${ticker}`);
    modalState.detail = detail;
    modalState.activeStrategy = detail.top_strategy ? detail.top_strategy.strategy_id : detail.all_strategies[0].strategy_id;
    renderModal();
  } catch (err) {
    $("#modal-content").innerHTML = `<div class="empty-state">Failed to load ${ticker}: ${err.message}</div>`;
  }
}
function closeModal() { $("#modal-overlay").classList.remove("open"); }

function renderModal() {
  const d = modalState.detail;
  const s = d.scores;
  const t = d.technical;
  const f = d.fundamental;
  const ev = d.event;
  const conv = d.convergence;
  const exp = d.explanation;
  const host = $("#modal-content");
  host.innerHTML = "";

  host.appendChild(el("button", { class: "modal-close", onclick: closeModal }, "✕"));
  host.appendChild(el("div", { class: "hero-head" }, [
    el("div", {}, [
      el("div", { class: "hero-ticker" }, `${d.ticker} — ${d.name}`),
      el("div", { class: "hero-name" }, `${d.sector} · ${d.industry} · $${fmtNum(d.price, 2)} · as of ${d.as_of}`),
      el("div", { html: tierBadgeHtml(d.overall_signal.tier, d.overall_signal.label) }),
    ]),
    el("div", { class: "hero-score" }, [
      el("div", { class: "num tabular" }, fmtNum(d.display_score, 0)),
      el("div", { class: "of100" }, "/ 100 · Setup quality " + fmtNum(exp.setup_quality_10, 1) + "/10"),
    ]),
  ]));

  host.appendChild(el("div", { class: "subscore-grid", style: "margin:16px 0;" }, [
    subscoreCell("Quality", s.quality), subscoreCell("Growth", s.growth), subscoreCell("Momentum", s.momentum),
    subscoreCell("Value", s.value), subscoreCell("Cash Flow", s.cash_flow), subscoreCell("Catalyst", s.catalyst),
    subscoreCell("Risk", s.risk),
  ]));

  host.appendChild(el("div", { class: "convergence-block", style: "margin-bottom:16px;" }, [
    el("div", { class: "convergence-label" }, [
      el("span", {}, "SIGNAL CONVERGENCE"),
      el("span", { class: "tabular" }, `${conv.positive_count} of ${conv.total} · ${fmtNum(conv.convergence_pct, 0)}%`),
    ]),
    el("div", { class: "convergence-bar" }, [el("div", { class: "convergence-fill", style: `width:${conv.convergence_pct}%;` })]),
  ]));

  host.appendChild(el("div", { class: "why-grid", style: "margin-bottom:16px;" }, [
    el("div", { class: "why-col" }, [el("h4", {}, "Why?"), el("ul", { class: "why-list good" }, exp.why.map((w) => el("li", {}, w)))]),
    el("div", { class: "why-col" }, [el("h4", {}, "Why Not?"), el("ul", { class: "why-list warn" }, exp.why_not.map((w) => el("li", {}, w)))]),
  ]));
  host.appendChild(el("div", { class: "concern-box", style: "margin-bottom:18px;" }, [el("strong", {}, "Main concern: "), exp.main_concern]));
  host.appendChild(el("p", { style: "font-size:12.5px;color:var(--text-secondary);margin:-8px 0 18px;" }, exp.narrative));

  // Fundamental vs trading opportunity + rankings
  host.appendChild(el("div", { class: "subscore-grid", style: "grid-template-columns:repeat(2,1fr);margin-bottom:18px;" }, [
    subscoreCell("Fundamental Opportunity", d.fundamental_opportunity),
    subscoreCell("Trading Opportunity", d.trading_opportunity),
  ]));

  // Strategy tabs
  host.appendChild(el("h4", { style: "margin:0 0 4px;font-size:12px;text-transform:uppercase;color:var(--text-muted);" }, "Strategy checklists"));
  const tabRow = el("div", { class: "strategy-badges-full" });
  for (const r of d.all_strategies) {
    tabRow.appendChild(el("button", {
      class: "strategy-tab-badge" + (modalState.activeStrategy === r.strategy_id ? " active" : "") + (r.qualifies ? "" : ""),
      style: r.qualifies ? "" : "opacity:0.55;",
      onclick: () => { modalState.activeStrategy = r.strategy_id; renderModal(); },
    }, `${r.qualifies ? "✓" : "·"} ${r.label} (${r.signals_met}/${r.signals_total})`));
  }
  host.appendChild(tabRow);

  const activeResult = d.all_strategies.find((r) => r.strategy_id === modalState.activeStrategy);
  if (activeResult) {
    const list = el("ul", { class: "checklist" });
    for (const item of activeResult.checklist) {
      list.appendChild(el("li", { class: item.met ? "met" : "" }, [el("span", { class: "mark" }, item.met ? "✓" : "○"), item.label]));
    }
    host.appendChild(el("div", { class: "panel", style: "background:var(--surface-2);margin:10px 0 18px;padding:14px;" }, [
      el("div", { style: "font-weight:700;margin-bottom:6px;" }, `${activeResult.badge} — opportunity score ${fmtNum(activeResult.opportunity_score, 0)}`),
      list,
      activeResult.data_lag_notice ? el("div", { class: "data-lag-note" }, activeResult.data_lag_notice) : null,
      activeResult.note ? el("div", { class: "data-lag-note" }, activeResult.note) : null,
    ]));
  }

  // Raw metrics table
  host.appendChild(el("h4", { style: "margin:0 0 4px;font-size:12px;text-transform:uppercase;color:var(--text-muted);" }, "Key metrics"));
  const rows = [
    ["P/E (TTM)", fmtNum(f.pe, 1)], ["Forward P/E", fmtNum(f.forward_pe, 1)], ["PEG", fmtNum(f.peg, 2)],
    ["EV/EBITDA", fmtNum(f.ev_ebitda, 1)], ["Price/FCF", fmtNum(f.price_fcf, 1)], ["FCF Yield", fmtPct(f.fcf_yield)],
    ["Price/Sales", fmtNum(f.price_sales, 2)], ["Fair Value (est.)", f.fair_value != null ? `$${fmtNum(f.fair_value, 2)}` : "—"],
    ["Est. Upside/Downside", fmtPct(f.upside_pct)],
    ["Revenue Growth YoY", pctField(f.revenue_growth_yoy)], ["EPS Growth YoY", pctField(f.eps_growth_yoy)],
    ["FCF Growth YoY", pctField(f.fcf_growth_yoy)], ["ROIC", pctField(f.roic)], ["ROE", pctField(f.roe)],
    ["Gross Margin", pctField(f.gross_margin)], ["Operating Margin", pctField(f.operating_margin)],
    ["Leverage (Debt/(Debt+Cash))", pctField(f.leverage)], ["Market Cap", f.market_cap != null ? fmtMoney(f.market_cap * 1e6) : "—"],
    ["RSI (14)", fmtNum(t.rsi14, 1)], ["Above 20/50/200-day MA", `${t.above_sma20 ? "✓" : "✗"} / ${t.above_sma50 ? "✓" : "✗"} / ${t.above_sma200 ? "✓" : "✗"}`],
    ["Volume vs 20d avg", `${fmtNum(t.volume_ratio, 2)}×`], ["% from 52w High/Low", `${fmtPct(t.pct_from_52w_high)} / ${fmtPct(t.pct_from_52w_low)}`],
    ["63d Momentum", fmtPct(t.mom_63d)], ["63d Relative Strength vs S&P", fmtPct(t.rel_strength_63d)],
    ["21d Historical Volatility (ann.)", fmtPct(t.hist_vol_21d * 100)],
    ["Institutional Ownership", ev.institutional_ownership_pct != null ? `${fmtNum(ev.institutional_ownership_pct, 1)}% (reported as of ${ev.institutional_ownership_as_of})` : "—"],
    ["Short Interest % Float", ev.short_interest_pct_float != null ? fmtPct(ev.short_interest_pct_float) : "—"],
    ["Days to Cover", fmtNum(ev.days_to_cover, 1)],
    ["Insider Buy/Sell Value (180d)", `${fmtMoney(ev.insider_buy_value_180d)} / ${fmtMoney(ev.insider_sell_value_180d)}`],
    ["Latest Earnings (EPS beat / Rev beat)", ev.eps_beat_pct != null ? `${fmtPct(ev.eps_beat_pct)} / ${fmtPct(ev.revenue_beat_pct)}` : "—"],
    ["Guidance Change", ev.guidance_change || "—"],
  ];
  const table = el("table", { class: "raw-table" });
  for (const [k, v] of rows) table.appendChild(el("tr", {}, [el("td", {}, k), el("td", {}, String(v))]));
  host.appendChild(table);
  host.appendChild(el("div", { class: "data-lag-note" }, "Institutional ownership and short interest are inherently reported with a lag — labeled with the period they actually reflect, not shown as real-time."));
}

// -------------------------------------------------------------- backtest --
function collectBacktestParams() {
  const body = {
    start_date: $("#bt-start").value,
    end_date: $("#bt-end").value,
    top_n: parseInt($("#bt-topn").value, 10) || 12,
  };
  if ($("#bt-sector").value) body.sector = $("#bt-sector").value;
  if (state.btRulesMode === "strategy") {
    body.strategy_id = $("#bt-strategy").value;
  } else {
    body.rules = { min_roic: 0.15, min_eps_growth: 0.10, require_above_200ma: true, min_momentum_score: 60, min_volume_ratio: 1.0 };
  }
  return body;
}

async function runBacktest() {
  const btn = $("#bt-run");
  btn.disabled = true;
  $("#bt-status").textContent = "Running point-in-time simulation — this replays the full history month by month, can take up to a minute…";
  $("#bt-results").innerHTML = '<div class="loading-row"><span class="spinner"></span> Simulating…</div>';
  try {
    const body = collectBacktestParams();
    const result = await api("/backtest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    renderBacktestResult(result);
    loadRunHistory();
    $("#bt-status").textContent = "Done.";
  } catch (err) {
    $("#bt-results").innerHTML = `<div class="empty-state">Backtest failed: ${err.message}</div>`;
    $("#bt-status").textContent = "";
  } finally {
    btn.disabled = false;
  }
}

function renderBacktestResult(result) {
  const host = $("#bt-results");
  host.innerHTML = "";
  const m = result.metrics;

  const legend = el("div", { class: "legend-row" }, [
    el("div", { class: "legend-item" }, [el("span", { class: "legend-swatch", style: "background:var(--series-1);" }), "Strategy portfolio"]),
    el("div", { class: "legend-item" }, [el("span", { class: "legend-swatch", style: "background:var(--text-muted);" }), "S&P 500 (benchmark)"]),
  ]);
  host.appendChild(legend);

  const chartWrap = el("div", { style: "position:relative;" });
  host.appendChild(chartWrap);
  renderEquityChart(chartWrap, result.equity_curve, result.benchmark_curve);

  const metricTiles = [
    ["Total Return", fmtPct(m.total_return_pct), m.total_return_pct >= 0 ? "good" : "critical"],
    ["Annualized Return", fmtPct(m.annualized_return_pct), m.annualized_return_pct >= 0 ? "good" : "critical"],
    ["S&P 500 Annualized", fmtPct(m.benchmark_annualized_return_pct), ""],
    ["Excess vs S&P (ann.)", fmtPct(m.excess_annualized_pct), m.excess_annualized_pct >= 0 ? "good" : "critical"],
    ["Max Drawdown", fmtPct(m.max_drawdown_pct), "critical"],
    ["Sharpe Ratio", fmtNum(m.sharpe_ratio, 2), ""],
    ["Sortino Ratio", fmtNum(m.sortino_ratio, 2), ""],
    ["Win Rate", m.win_rate_pct != null ? `${fmtNum(m.win_rate_pct, 1)}%` : "—", ""],
    ["Avg Gain / Avg Loss", `${fmtPct(m.avg_gain_pct)} / ${fmtPct(m.avg_loss_pct)}`, ""],
    ["Profit Factor", fmtNum(m.profit_factor, 2), ""],
    ["Number of Trades", String(m.number_of_trades), ""],
    ["Avg Turnover / Rebalance", m.avg_turnover_pct != null ? `${fmtNum(m.avg_turnover_pct, 0)}%` : "—", ""],
  ];
  const grid = el("div", { class: "metrics-grid" });
  for (const [k, v, cls] of metricTiles) {
    grid.appendChild(el("div", { class: "metric-tile" }, [el("div", { class: "k" }, k), el("div", { class: `v tabular ${cls}` }, v)]));
  }
  host.appendChild(grid);
}

// Minimal SVG line chart: two series indexed to 100 at the start date, with
// gridlines, a legend (rendered separately above), and a hover crosshair +
// tooltip per the dataviz skill's interaction spec.
function renderEquityChart(container, equityCurve, benchCurve) {
  const W = container.clientWidth || 800, H = 280, PAD = { l: 46, r: 16, t: 12, b: 26 };
  const n = equityCurve.length;
  if (n < 2) { container.appendChild(el("div", { class: "empty-state" }, "Not enough data points to chart.")); return; }

  const stratIdx = equityCurve.map((p) => p.equity * 100);
  const benchBase = benchCurve[0].close || 1;
  const benchIdx = benchCurve.map((p) => (p.close != null ? (p.close / benchBase) * 100 : null));

  const allVals = [...stratIdx, ...benchIdx.filter((v) => v != null)];
  const yMin = Math.min(...allVals, 100) * 0.97;
  const yMax = Math.max(...allVals, 100) * 1.03;

  const x = (i) => PAD.l + (i / (n - 1)) * (W - PAD.l - PAD.r);
  const y = (v) => H - PAD.b - ((v - yMin) / (yMax - yMin)) * (H - PAD.t - PAD.b);

  const svgns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgns, "svg");
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", H);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.style.display = "block";

  // gridlines (4 horizontal)
  const gridSteps = 4;
  for (let i = 0; i <= gridSteps; i++) {
    const v = yMin + (i / gridSteps) * (yMax - yMin);
    const gy = y(v);
    const line = document.createElementNS(svgns, "line");
    line.setAttribute("x1", PAD.l); line.setAttribute("x2", W - PAD.r);
    line.setAttribute("y1", gy); line.setAttribute("y2", gy);
    line.setAttribute("stroke", "var(--gridline)"); line.setAttribute("stroke-width", "1");
    svg.appendChild(line);
    const label = document.createElementNS(svgns, "text");
    label.setAttribute("x", 4); label.setAttribute("y", gy + 4); label.setAttribute("fill", "var(--text-muted)");
    label.setAttribute("font-size", "10"); label.textContent = v.toFixed(0);
    svg.appendChild(label);
  }

  function pathFor(values) {
    let d = "";
    let started = false;
    values.forEach((v, i) => {
      if (v == null) return;
      d += `${started ? "L" : "M"}${x(i).toFixed(2)},${y(v).toFixed(2)} `;
      started = true;
    });
    return d.trim();
  }

  const benchPath = document.createElementNS(svgns, "path");
  benchPath.setAttribute("d", pathFor(benchIdx));
  benchPath.setAttribute("fill", "none"); benchPath.setAttribute("stroke", "var(--text-muted)");
  benchPath.setAttribute("stroke-width", "2"); benchPath.setAttribute("stroke-linejoin", "round"); benchPath.setAttribute("stroke-linecap", "round");
  svg.appendChild(benchPath);

  const stratPath = document.createElementNS(svgns, "path");
  stratPath.setAttribute("d", pathFor(stratIdx));
  stratPath.setAttribute("fill", "none"); stratPath.setAttribute("stroke", "var(--series-1)");
  stratPath.setAttribute("stroke-width", "2"); stratPath.setAttribute("stroke-linejoin", "round"); stratPath.setAttribute("stroke-linecap", "round");
  svg.appendChild(stratPath);

  // end markers
  [[stratIdx, "var(--series-1)"], [benchIdx, "var(--text-muted)"]].forEach(([vals, color]) => {
    const lastIdx = [...vals].map((v, i) => [v, i]).filter(([v]) => v != null).pop();
    if (!lastIdx) return;
    const [v, i] = lastIdx;
    const c = document.createElementNS(svgns, "circle");
    c.setAttribute("cx", x(i)); c.setAttribute("cy", y(v)); c.setAttribute("r", 4);
    c.setAttribute("fill", color); c.setAttribute("stroke", "var(--surface-1)"); c.setAttribute("stroke-width", "2");
    svg.appendChild(c);
  });

  // hover crosshair
  const crosshair = document.createElementNS(svgns, "line");
  crosshair.setAttribute("y1", PAD.t); crosshair.setAttribute("y2", H - PAD.b);
  crosshair.setAttribute("stroke", "var(--border-strong)"); crosshair.setAttribute("stroke-width", "1");
  crosshair.setAttribute("visibility", "hidden");
  svg.appendChild(crosshair);

  const hitRect = document.createElementNS(svgns, "rect");
  hitRect.setAttribute("x", PAD.l); hitRect.setAttribute("y", PAD.t);
  hitRect.setAttribute("width", W - PAD.l - PAD.r); hitRect.setAttribute("height", H - PAD.t - PAD.b);
  hitRect.setAttribute("fill", "transparent");
  svg.appendChild(hitRect);

  container.innerHTML = "";
  container.appendChild(svg);

  const tooltip = el("div", { class: "tooltip-layer", style: "display:none;" });
  container.style.position = "relative";
  container.appendChild(tooltip);

  hitRect.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((relX - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
    const idx = Math.max(0, Math.min(n - 1, i));
    crosshair.setAttribute("x1", x(idx)); crosshair.setAttribute("x2", x(idx)); crosshair.setAttribute("visibility", "visible");
    tooltip.style.display = "block";
    tooltip.style.left = `${(x(idx) / W) * 100}%`;
    tooltip.style.top = "10px";
    tooltip.innerHTML = `<div style="color:var(--text-muted);margin-bottom:4px;">${equityCurve[idx].date}</div>
      <div style="color:var(--series-1);">Strategy: ${stratIdx[idx].toFixed(1)}</div>
      <div style="color:var(--text-muted);">S&P 500: ${benchIdx[idx] != null ? benchIdx[idx].toFixed(1) : "—"}</div>`;
  });
  hitRect.addEventListener("mouseleave", () => { crosshair.setAttribute("visibility", "hidden"); tooltip.style.display = "none"; });
}

async function loadRunHistory() {
  const data = await api("/backtest");
  const wrap = $("#run-history");
  wrap.innerHTML = "";
  if (!data.runs.length) { wrap.appendChild(el("div", { class: "empty-state" }, "No backtests run yet.")); return; }
  for (const run of data.runs) {
    const label = run.strategy_name === "custom_rules" ? "Custom rules" : run.strategy_name;
    wrap.appendChild(el("div", {
      class: "run-history-item",
      onclick: async () => { const full = await api(`/backtest/${run.id}`); renderBacktestResult(full); },
    }, [
      el("span", {}, `#${run.id} · ${label} · ${run.start_date} → ${run.end_date}`),
      el("span", { class: "tabular" }, `${fmtPct(run.metrics.annualized_return_pct)} ann. / Sharpe ${fmtNum(run.metrics.sharpe_ratio, 2)}`),
    ]));
  }
}
