"use strict";

const state = {
  sectors: [],
  clients: [],
  config: null,
  lastResponse: null,
  openActorId: null,
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

function actorColor(actor) {
  const palette = {
    "state-sponsored": "#1d4ed8",
    "ransomware":      "#b91c1c",
    "extortion":       "#7c3aed",
    "cybercrime":      "#c2410c",
  };
  return palette[actor.type] || "#0f766e";
}

function actorSize(actor) {
  const v = actor.victims_total_window || 0;
  return Math.max(10, Math.min(34, 10 + v * 3));
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
    `Victims (window): ${actor.victims_total_window} &middot; in sector: ${actor.victims_in_sector}`,
    "Top TTPs:<br>  &middot; " + (ttps || "&mdash;"),
  ].join("<br>");
}

function renderHeatmap(data) {
  const actors = data.actors || [];
  const trace = {
    type: "scatter",
    mode: "markers+text",
    x: actors.map(a => a.x),
    y: actors.map(a => a.y),
    text: actors.map(a => a.name),
    textposition: "top center",
    textfont: {size: 10, color: "#1f2937"},
    customdata: actors.map(a => a.id),
    hovertemplate: actors.map(a => hoverText(a) + "<extra></extra>"),
    marker: {
      size: actors.map(actorSize),
      color: actors.map(actorColor),
      line: {width: 1, color: "#0f172a"},
      opacity: 0.85,
    },
  };

  const layout = {
    title: {
      text: `Sector: ${data.sector}  |  since ${data.since}  (${data.window_months} mo)  |  client: ${data.client}`,
      font: {size: 14},
    },
    xaxis: {title: "Opportunity (X)", range: [0, 100], dtick: 10, zeroline: false, gridcolor: "#e2e8f0"},
    yaxis: {title: "Intent (Y)",      range: [0, 100], dtick: 10, zeroline: false, gridcolor: "#e2e8f0"},
    shapes: [
      {type: "line", x0: 50, x1: 50, y0: 0, y1: 100, line: {color: "#cbd5e1", width: 1, dash: "dot"}},
      {type: "line", x0: 0, x1: 100, y0: 50, y1: 50, line: {color: "#cbd5e1", width: 1, dash: "dot"}},
    ],
    annotations: [
      {x: 75, y: 95, text: "High intent / High opportunity", showarrow: false, font: {color: "#94a3b8", size: 10}},
      {x: 25, y: 95, text: "High intent / Low opportunity",  showarrow: false, font: {color: "#94a3b8", size: 10}},
      {x: 75, y: 5,  text: "Low intent / High opportunity",  showarrow: false, font: {color: "#94a3b8", size: 10}},
      {x: 25, y: 5,  text: "Low intent / Low opportunity",   showarrow: false, font: {color: "#94a3b8", size: 10}},
    ],
    margin: {l: 60, r: 30, t: 50, b: 60},
    plot_bgcolor: "#ffffff",
    paper_bgcolor: "#ffffff",
    showlegend: false,
    hoverlabel: {bgcolor: "#ffffff", bordercolor: "#cbd5e1", font: {size: 11}},
  };

  Plotly.react("heatmap", [trace], layout, {responsive: true, displaylogo: false});

  const gd = $("heatmap");
  gd.removeAllListeners && gd.removeAllListeners("plotly_click");
  gd.on("plotly_click", evt => {
    const pt = evt.points && evt.points[0];
    if (!pt) return;
    const id = pt.customdata;
    if (id) showActorDetail(id);
  });
}

async function showActorDetail(actorId) {
  const params = buildQuery();
  const data = await fetchJSON(`/api/actor/${actorId}?${params.toString()}`);
  const a = data.actor;
  state.openActorId = actorId;
  $("actor-detail-name").textContent = a.name + (a.aliases.length ? ` (${a.aliases.join(", ")})` : "");

  const ttpsRows = (a.all_top_ttps || []).map(t =>
    `<tr><td><code>${t.id}</code></td><td>${t.name}</td><td>${t.tactic || ""}</td></tr>`
  ).join("");
  const victimRows = (a.victims_window || []).map(v =>
    `<tr><td>${v._date || v.date}</td><td>${v.sector}</td><td>${v.name}</td></tr>`
  ).join("");
  const fallbackBadge = a.p_sect_source === "baseline_fallback"
    ? ` <span class="badge">baseline fallback</span>`
    : "";

  $("actor-detail-body").innerHTML = `
    <div class="kv-grid">
      <div class="k">Type</div><div>${a.type || "n/a"} &middot; ${a.country || "n/a"}</div>
      <div class="k">Intent (Y)</div><div>${a.y}</div>
      <div class="k">Opportunity (X)</div><div>${a.x}</div>
      <div class="k">P_sect &middot; P_ttp</div><div>${a.p_sect}${fallbackBadge} &middot; ${a.p_ttp}</div>
      <div class="k">SecurityScore</div><div>${a.security_score} <small>(${a.security_score_source || "n/a"})</small></div>
      <div class="k">Victims (window / sector)</div><div>${a.victims_total_window} / ${a.victims_in_sector}</div>
      <div class="k">Description</div><div>${a.description || ""}</div>
    </div>
    <h3>TTPs</h3>
    <table><thead><tr><th>ID</th><th>Technique</th><th>Tactic</th></tr></thead><tbody>${ttpsRows}</tbody></table>
    <h3>Victims in window</h3>
    <table><thead><tr><th>Date</th><th>Sector</th><th>Name</th></tr></thead><tbody>${victimRows || '<tr><td colspan="3">&mdash;</td></tr>'}</tbody></table>
  `;
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
