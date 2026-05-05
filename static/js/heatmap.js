"use strict";

const state = {
  sectors: [],
  clients: [],
  config: null,
  lastResponse: null,
  openActorId: null,
  tableSort: {},  // keyed per-table; preserves user sort across re-renders
};

function $(id) { return document.getElementById(id); }

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    const body = await r.text();
    throw new Error(`HTTP ${r.status} on ${url}: ${body}`);
  }
  return r.json();
}

function buildOption(value, label, selected) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = label;
  if (selected) o.selected = true;
  return o;
}

async function bootstrap() {
  const [sectorsResp, clientsResp, cfg] = await Promise.all([
    fetchJSON("/api/sectors"),
    fetchJSON("/api/clients"),
    fetchJSON("/api/config"),
  ]);
  state.sectors = sectorsResp.sectors;
  state.clients = clientsResp.clients;
  state.config = cfg;

  const sectorSel = $("sector");
  const defaultSector = state.sectors.includes("Telecommunications") ? "Telecommunications" : state.sectors[0];
  state.sectors.forEach(s => sectorSel.appendChild(buildOption(s, s, s === defaultSector)));

  const winSel = $("window");
  cfg.time_windows_months.forEach(m => {
    winSel.appendChild(buildOption(String(m), `${m} months`, m === cfg.default_time_window_months));
  });

  const clientSel = $("client");
  state.clients.forEach(c => clientSel.appendChild(buildOption(c.id, c.name, c.id === cfg.default_client_id)));

  const meta = cfg.active_formula_meta || {};
  const floor = meta.floor_epsilon;
  const formulaText =
    floor != null
      ? `Y = sqrt(max(P_sect, ${floor}) &times; max(P_ttp, ${floor})) &times; 100, X = SecurityScore &times; P_ttp`
      : `Y = sqrt(P_sect &times; P_ttp) &times; 100, X = SecurityScore &times; P_ttp`;
  $("formula-banner").innerHTML =
    `Active formula: <code>${cfg.active_formula}</code> &middot; ` +
    `Available: ${cfg.available_formulas.map(f => `<code>${f}</code>`).join(", ")} &middot; ` +
    formulaText +
    (floor != null ? ` &middot; <em>floor &epsilon; = ${floor} on each probability</em>` : "");
  $("data-banner").innerHTML =
    `Active victims adapter: <code>${cfg.active_victims_adapter}</code> &middot; ` +
    `ransomware.live usage flag: <code>${cfg.ransomware_live_usage}</code> &middot; ` +
    `Default SecurityScore: <code>${cfg.default_security_score}</code>`;

  attachHandlers();
  await reload();
}

function attachHandlers() {
  ["sector", "window", "client", "security_score"].forEach(id => {
    $(id).addEventListener("change", onFilterChange);
  });
  $("refresh").addEventListener("click", async () => {
    await fetchJSON("/api/refresh", {method: "POST"});
    await onFilterChange();
  });
  $("export-png").addEventListener("click", () => exportImage("png"));
  $("export-svg").addEventListener("click", () => exportImage("svg"));
  $("export-json").addEventListener("click", exportJSON);
  $("actor-detail-close").addEventListener("click", closeActorDetail);
}

async function onFilterChange() {
  // Any filter change invalidates the open detail panel: re-fetch it from
  // the same endpoint as the heat map so scatter and panel stay coherent.
  const previouslyOpen = state.openActorId;
  await reload();
  if (previouslyOpen) {
    await showActorDetail(previouslyOpen);
  }
}

function closeActorDetail() {
  state.openActorId = null;
  $("actor-detail").classList.add("hidden");
}

function buildQuery() {
  const params = new URLSearchParams();
  params.set("sector", $("sector").value);
  params.set("window_months", $("window").value);
  params.set("client", $("client").value);
  const sec = $("security_score").value;
  if (sec !== "") params.set("security_score", sec);
  return params;
}

async function reload() {
  const params = buildQuery();
  const data = await fetchJSON(`/api/actors?${params.toString()}`);
  state.lastResponse = data;
  renderHeatmap(data);
}

// Type -> color mapping. Source of truth for the enum lives in
// data/schema/actor_schema.json (actor.type). Keep this map in sync.
const TYPE_COLORS = {
  "state-sponsored": "#1d4ed8",  // blue
  "ransomware":      "#b91c1c",  // red
  "cybercriminal":   "#c2410c",  // orange
  "hacktivist":      "#7c3aed",  // violet
  "unknown":         "#64748b",  // slate
};
// Stable display order in the legend.
const TYPE_ORDER = ["state-sponsored", "ransomware", "cybercriminal", "hacktivist", "unknown"];

function typeColor(type) {
  return TYPE_COLORS[type] || TYPE_COLORS.unknown;
}

function typeLabel(type) {
  if (!type) return "Unknown";
  return type.charAt(0).toUpperCase() + type.slice(1);
}

// Marker size encodes `victims_total_window` (backend field set by
// scoring/scorer.py). The C.2 spec calls it "total victims in window".
// Linear mapping into [MARKER_SIZE_MIN, MARKER_SIZE_MAX] from /api/config,
// scaled against the max in the current dataset. Falls back to a uniform
// MARKER_SIZE_FALLBACK when every actor is at zero.
function buildSizeScaler(actors) {
  const cfg = state.config || {};
  const minSize = cfg.marker_size_min ?? 8;
  const maxSize = cfg.marker_size_max ?? 24;
  const fallback = cfg.marker_size_fallback ?? 12;
  const counts = actors.map(a => a.victims_total_window || 0);
  const peak = Math.max(0, ...counts);
  if (peak === 0) {
    return () => fallback;
  }
  return (a) => {
    const v = a.victims_total_window || 0;
    return minSize + (v / peak) * (maxSize - minSize);
  };
}

function hoverText(actor) {
  const ttps = (actor.top_ttps || [])
    .map(t => `${t.id} ${t.name}`)
    .join("<br>  &middot; ");
  const aliases = (actor.aliases || []).slice(0, 3).join(", ");
  return [
    `<b>${actor.name}</b>` + (aliases ? ` <i>(${aliases})</i>` : ""),
    `Type: ${actor.type || "n/a"} &middot; Country: ${actor.country || "n/a"}`,
    `Intent (Y): ${actor.y}  &middot;  Opportunity (X): ${actor.x}`,
    `P_sect: ${actor.p_sect}  &middot;  P_ttp: ${actor.p_ttp}  &middot;  SecurityScore: ${actor.security_score}`,
    `Victims in sector (window): ${actor.victims_in_sector}`,
    `Total victims (window, all sectors): ${actor.victims_total_window}  <i>(point size)</i>`,
    "Top TTPs:<br>  &middot; " + (ttps || "&mdash;"),
  ].join("<br>");
}

// Per-actor textposition. Default is 'top center'; flips through a 6-position
// cycle (top/bottom x left/center/right) when nearby earlier neighbours are
// already at preceding positions. Points stay at their computed positions;
// only labels move. Single pass, deterministic order = order in /api/actors.
// 7+ point clusters degrade to overlap (rare, expected only at the floor
// collocation point in geometric_mean_floored_v1).
const JITTER_THRESHOLD = 8;
const JITTER_POSITIONS = [
  "top center",
  "bottom center",
  "top right",
  "bottom right",
  "top left",
  "bottom left",
];
function computeTextPositions(actors) {
  const positions = new Map();
  for (let i = 0; i < actors.length; i++) {
    const a = actors[i];
    const used = Object.create(null);
    let hasNeighbour = false;
    for (let j = 0; j < i; j++) {
      const b = actors[j];
      const dx = (a.x ?? 0) - (b.x ?? 0);
      const dy = (a.y ?? 0) - (b.y ?? 0);
      if (Math.hypot(dx, dy) < JITTER_THRESHOLD) {
        const p = positions.get(b.id) || "top center";
        used[p] = (used[p] || 0) + 1;
        hasNeighbour = true;
      }
    }
    let chosen = "top center";
    if (hasNeighbour) {
      // Pick the first position in priority order with no neighbour yet.
      // If all 6 are taken (7+ collocated points), fall back to top center.
      const free = JITTER_POSITIONS.find(p => !used[p]);
      chosen = free || "top center";
    }
    positions.set(a.id, chosen);
  }
  return positions;
}

function renderHeatmap(data) {
  const actors = data.actors || [];
  const cfg = state.config || {};
  const tx = cfg.quadrant_threshold_x ?? 50;
  const ty = cfg.quadrant_threshold_y ?? 50;

  const textPositions = computeTextPositions(actors);

  // One Plotly trace per actor type -> Plotly renders a clickable legend
  // that toggles each type's visibility natively. We keep a single X/Y axis
  // (no subplots); shapes and annotations stay at layout level.
  const grouped = new Map();
  for (const a of actors) {
    const key = TYPE_COLORS[a.type] ? a.type : "unknown";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(a);
  }
  const sizeFor = buildSizeScaler(actors);
  const traces = [];
  for (const type of TYPE_ORDER) {
    const group = grouped.get(type);
    if (!group || group.length === 0) continue;
    traces.push({
      type: "scatter",
      mode: "markers+text",
      name: typeLabel(type),
      legendgroup: type,
      x: group.map(a => a.x),
      y: group.map(a => a.y),
      text: group.map(a => a.name),
      textposition: group.map(a => textPositions.get(a.id) || "top center"),
      textfont: {size: 10, color: "#1f2937"},
      customdata: group.map(a => a.id),
      hovertemplate: group.map(a => hoverText(a) + "<extra></extra>"),
      marker: {
        size: group.map(sizeFor),
        color: typeColor(type),
        line: {width: 1, color: "#0f172a"},
        opacity: 0.85,
      },
      cliponaxis: false,
    });
  }

  const layout = {
    title: {
      text: `Sector: ${data.sector}  |  since ${data.since}  (${data.window_months} mo)  |  client: ${data.client}`,
      font: {size: 14},
    },
    xaxis: {title: "Opportunity (X)", range: [0, 100], dtick: 10, zeroline: false, gridcolor: "#e2e8f0"},
    yaxis: {title: "Intent (Y)",      range: [0, 100], dtick: 10, zeroline: false, gridcolor: "#e2e8f0"},
    shapes: [
      {type: "line", x0: tx, x1: tx, y0: 0, y1: 100,
       line: {color: "rgba(153,153,153,0.3)", width: 1, dash: "dot"}},
      {type: "line", x0: 0, x1: 100, y0: ty, y1: ty,
       line: {color: "rgba(153,153,153,0.3)", width: 1, dash: "dot"}},
    ],
    annotations: [
      {x: (tx + 100) / 2, y: 96, text: "High intent / High opportunity",
       showarrow: false, font: {color: "#94a3b8", size: 10}},
      {x: tx / 2,         y: 96, text: "High intent / Low opportunity",
       showarrow: false, font: {color: "#94a3b8", size: 10}},
      {x: (tx + 100) / 2, y: 4,  text: "Low intent / High opportunity",
       showarrow: false, font: {color: "#94a3b8", size: 10}},
      {x: tx / 2,         y: 4,  text: "Low intent / Low opportunity",
       showarrow: false, font: {color: "#94a3b8", size: 10}},
    ],
    margin: {l: 60, r: 160, t: 50, b: 60},
    plot_bgcolor: "#ffffff",
    paper_bgcolor: "#ffffff",
    showlegend: true,
    legend: {
      title: {text: "Actor type", font: {size: 11}},
      x: 1.02, y: 1, xanchor: "left", yanchor: "top",
      bgcolor: "rgba(255,255,255,0.95)",
      bordercolor: "#e2e8f0",
      borderwidth: 1,
      font: {size: 11},
    },
    hoverlabel: {bgcolor: "#ffffff", bordercolor: "#cbd5e1", font: {size: 11}},
  };

  Plotly.react("heatmap", traces, layout, {responsive: true, displaylogo: false});

  const gd = $("heatmap");
  gd.removeAllListeners && gd.removeAllListeners("plotly_click");
  gd.on("plotly_click", evt => {
    const pt = evt.points && evt.points[0];
    if (!pt) return;
    const id = pt.customdata;
    if (id) showActorDetail(id);
  });
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmt2(n) {
  return Number.isFinite(n) ? n.toFixed(2) : String(n);
}

function pSectSourceLabel(src) {
  if (src === "victims_ratio") return "calculated from window";
  if (src === "baseline_fallback") return "baseline fallback";
  return src || "n/a";
}

function sharedLabel(n) {
  if (!n || n <= 0) return "Unique to this actor";
  return `Shared with ${n} actor${n > 1 ? "s" : ""}`;
}

function mitreCell(actor) {
  if (!actor.mitre_url) {
    return `not assigned`;
  }
  const id = actor.mitre_id || "MITRE ATT&amp;CK";
  return `<a href="${escapeHtml(actor.mitre_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(id)}</a>`;
}

// Sortable table rendering helpers. Each table tracks its current sort key
// and direction in `state.tableSort[<key>]`. Clicking a header toggles or
// switches the sort.
function renderSortableTable(containerId, columns, rows, sortKey, defaultSort) {
  const sortState = state.tableSort[sortKey] || {...defaultSort};
  state.tableSort[sortKey] = sortState;
  const sorted = [...rows].sort((a, b) => {
    const va = a[sortState.field];
    const vb = b[sortState.field];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return sortState.dir === "asc" ? va - vb : vb - va;
    return sortState.dir === "asc"
      ? String(va).localeCompare(String(vb))
      : String(vb).localeCompare(String(va));
  });

  const thead = columns.map(c => {
    const arrow = sortState.field === c.field
      ? (sortState.dir === "asc" ? " &uarr;" : " &darr;")
      : "";
    return `<th data-field="${c.field}" class="sortable">${c.label}${arrow}</th>`;
  }).join("");
  const tbody = sorted.length === 0
    ? `<tr><td colspan="${columns.length}">&mdash;</td></tr>`
    : sorted.map(r => "<tr>" + columns.map(c => `<td>${c.render ? c.render(r) : escapeHtml(r[c.field])}</td>`).join("") + "</tr>").join("");

  const html = `<table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table>`;
  const container = document.getElementById(containerId);
  container.innerHTML = html;

  container.querySelectorAll("th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const field = th.getAttribute("data-field");
      if (sortState.field === field) {
        sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
      } else {
        sortState.field = field;
        sortState.dir = "desc";
      }
      renderSortableTable(containerId, columns, rows, sortKey, defaultSort);
    });
  });
}

async function showActorDetail(actorId) {
  const params = buildQuery();
  const data = await fetchJSON(`/api/actor/${actorId}?${params.toString()}`);
  const a = data.actor;
  state.openActorId = actorId;
  $("actor-detail-name").textContent = a.name + (a.aliases.length ? ` (${a.aliases.join(", ")})` : "");

  const fallbackBadge = a.p_sect_source === "baseline_fallback"
    ? ` <span class="badge">baseline fallback</span>`
    : "";
  const pTtpSource = "fixture value";  // Phase 1 source of P_ttp; Phase 2 will compute from MITRE.

  $("actor-detail-body").innerHTML = `
    <div class="kv-grid">
      <div class="k">Type</div><div>${escapeHtml(a.type || "n/a")} &middot; ${escapeHtml(a.country || "n/a")}</div>
      <div class="k">MITRE ATT&amp;CK Group</div><div>${mitreCell(a)}</div>
      <div class="k">Intent (Y)</div><div>${a.y}</div>
      <div class="k">Opportunity (X)</div><div>${a.x}</div>
      <div class="k">P_sect</div><div>${fmt2(a.p_sect)} <small>(${pSectSourceLabel(a.p_sect_source)})</small>${fallbackBadge}</div>
      <div class="k">P_ttp</div><div>${fmt2(a.p_ttp)} <small>(${pTtpSource})</small></div>
      <div class="k">SecurityScore</div><div>${a.security_score} <small>(${escapeHtml(a.security_score_source || "n/a")})</small></div>
      <div class="k">Victims (window / sector)</div><div>${a.victims_total_window} / ${a.victims_in_sector}</div>
      <div class="k">Description</div><div>${escapeHtml(a.description || "")}</div>
    </div>
    <h3>TTPs <small>(click any header to sort)</small></h3>
    <div id="actor-detail-ttps"></div>
    <h3>Victims in window <small>(${a.victims_total_window} total, ${a.victims_in_sector} in selected sector)</small></h3>
    <div id="actor-detail-victims"></div>
  `;

  const ttpsRows = (a.all_top_ttps || []).map(t => ({
    id: t.id || "",
    name: t.name || "",
    tactic: t.tactic || "",
    shared_with: typeof t.shared_with === "number" ? t.shared_with : 0,
  }));
  renderSortableTable(
    "actor-detail-ttps",
    [
      {field: "id",          label: "ID",        render: r => `<code>${escapeHtml(r.id)}</code>`},
      {field: "name",        label: "Technique"},
      {field: "tactic",      label: "Tactic"},
      {field: "shared_with", label: "Shared",    render: r => escapeHtml(sharedLabel(r.shared_with))},
    ],
    ttpsRows,
    `ttps:${actorId}`,
    {field: "shared_with", dir: "desc"},
  );

  const victimRows = (a.victims_window || []).map(v => ({
    date: v._date || v.date,
    sector: v.sector,
    name: v.name,
  }));
  renderSortableTable(
    "actor-detail-victims",
    [
      {field: "date",   label: "Date"},
      {field: "sector", label: "Sector"},
      {field: "name",   label: "Name"},
    ],
    victimRows,
    `victims:${actorId}`,
    {field: "date", dir: "desc"},
  );

  $("actor-detail").classList.remove("hidden");
}

function exportImage(format) {
  const sector = $("sector").value;
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  Plotly.downloadImage("heatmap", {
    format,
    filename: `threatheatmap_${sector.replace(/[^a-zA-Z0-9]+/g, "_")}_${stamp}`,
    width: 1200,
    height: 800,
    scale: format === "png" ? 2 : 1,
  });
}

async function exportJSON() {
  const params = buildQuery();
  params.set("format", "json");
  const data = await fetchJSON(`/api/export?${params.toString()}`);
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  a.href = url;
  a.download = `threatheatmap_${data.metadata.sector.replace(/[^a-zA-Z0-9]+/g, "_")}_${stamp}.json`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
}

bootstrap().catch(err => {
  console.error(err);
  document.body.innerHTML = `<pre style="padding:2rem;color:#991b1b">${err.message}</pre>`;
});
