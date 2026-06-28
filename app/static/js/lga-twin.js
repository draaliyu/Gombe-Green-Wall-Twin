import {
  MAP_STYLE,
  TERRAIN_SOURCE,
  bindFullscreen,
  fetchJson,
  formatDateTime,
  formatPercent,
  setText,
  setWidth,
  showToast,
  updateConnection,
} from "./common.js";
import { LiveSky } from "./sky.js";
import { TreeLayer } from "./trees3d.js";

const slug = decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop() || "");
const state = {
  catalogue: [],
  snapshot: null,
  activeLayer: "ndvi",
  orbit: true,
  ground: false,
  pitch3d: true,
  orbitFrame: null,
  treeLayer: null,
  treeVersion: -1,
  socket: null,
  socketRetry: 1000,
  destroyed: false,
};

const map = new maplibregl.Map({
  container: "lga-map",
  style: MAP_STYLE,
  center: [11.17, 10.29],
  zoom: 8.4,
  pitch: 56,
  bearing: -18,
  antialias: true,
  attributionControl: false,
  cooperativeGestures: window.innerWidth <= 760,
});
map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
if (window.innerWidth > 760) map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

const sky = new LiveSky("lga-sky-layer", { className: "live-sky-canvas lga-live-sky-canvas" });
let boundary = null;
let bounds = null;
let mapReady = false;
let layerRevision = 0;

function pct(value, digits = 1) { return formatPercent(Number(value), digits); }
function number(value, digits = 1, suffix = "") {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(digits)}${suffix}` : "Not available";
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}
function ndviClass(value) {
  const v = Number(value);
  if (!Number.isFinite(v)) return "No valid pixels";
  if (v >= 0.55) return "Dense/strong greenness";
  if (v >= 0.35) return "Moderate vegetation";
  if (v >= 0.18) return "Sparse vegetation";
  return "Very limited greenness";
}
function riskLabel(value) {
  const v = Number(value);
  if (v >= 0.7) return "Very high";
  if (v >= 0.5) return "High";
  if (v >= 0.3) return "Moderate";
  return "Low";
}

function fitLocal(duration = 850) {
  if (!bounds) return;
  map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], {
    padding: window.innerWidth <= 760 ? 34 : 82,
    duration,
    pitch: state.ground ? 72 : state.pitch3d ? 56 : 18,
    bearing: state.ground ? -28 : -12,
  });
}

function imageCoordinates(bbox) {
  const [west, south, east, north] = bbox;
  return [[west, north], [east, north], [east, south], [west, south]];
}

function addOrUpdateImageLayer(layer, url, bbox, opacity = 0.72) {
  const sourceId = `lga-${layer}-source`;
  const layerId = `lga-${layer}-layer`;
  if (map.getLayer(layerId)) map.removeLayer(layerId);
  if (map.getSource(sourceId)) map.removeSource(sourceId);
  map.addSource(sourceId, { type: "image", url, coordinates: imageCoordinates(bbox) });
  const before = map.getLayer("lga-boundary-line") ? "lga-boundary-line" : undefined;
  map.addLayer({
    id: layerId,
    type: "raster",
    source: sourceId,
    paint: { "raster-opacity": opacity, "raster-fade-duration": 260, "raster-resampling": "linear" },
    layout: { visibility: layer === state.activeLayer ? "visible" : "none" },
  }, before);
}

function setActiveLayer(layer) {
  state.activeLayer = layer;
  ["ndvi", "simulation", "landcover", "suitability", "risk"].forEach((name) => {
    if (map.getLayer(`lga-${name}-layer`)) map.setLayoutProperty(`lga-${name}-layer`, "visibility", name === layer ? "visible" : "none");
  });
  document.querySelectorAll("[data-layer]").forEach((button) => button.classList.toggle("active", button.dataset.layer === layer));
}

async function loadMapLayers(snapshot, force = false) {
  if (!mapReady || !snapshot) return;
  layerRevision += 1;
  const revision = layerRevision;
  const bbox = snapshot.geography.bbox;
  const stamp = `${Date.now()}-${revision}`;
  const layers = [
    ["ndvi", 0.70], ["simulation", 0.64], ["landcover", 0.72], ["suitability", 0.68], ["risk", 0.64],
  ];
  layers.forEach(([layer, opacity]) => addOrUpdateImageLayer(layer, `/api/lga-twins/${encodeURIComponent(slug)}/textures/${layer}.png?v=${stamp}`, bbox, opacity));
  setActiveLayer(state.activeLayer);
  if (force) showToast("Local environmental layers refreshed.");
}

function addBoundary(data) {
  boundary = data;
  if (map.getSource("lga-local-boundary")) map.getSource("lga-local-boundary").setData(data);
  else map.addSource("lga-local-boundary", { type: "geojson", data });
  if (!map.getLayer("lga-local-fill")) {
    map.addLayer({ id: "lga-local-fill", type: "fill", source: "lga-local-boundary", paint: { "fill-color": "#4de895", "fill-opacity": 0.045 } });
    map.addLayer({ id: "lga-boundary-glow", type: "line", source: "lga-local-boundary", paint: { "line-color": "#59ffc0", "line-width": 12, "line-opacity": 0.15, "line-blur": 6 } });
    map.addLayer({ id: "lga-boundary-line", type: "line", source: "lga-local-boundary", paint: { "line-color": "#c5ffe1", "line-width": 3.0, "line-opacity": 0.98 } });
  }
}

function initialiseTrees(snapshot) {
  if (!mapReady || !snapshot || state.treeLayer) return;
  const center = [snapshot.geography.centroid.longitude, snapshot.geography.centroid.latitude];
  state.treeLayer = new TreeLayer("lga-procedural-trees", center);
  map.addLayer(state.treeLayer);
  state.treeLayer.setTrees(snapshot.trees || [], Number(snapshot.satellite.texture_version || 1));
  state.treeLayer.setWeather(snapshot.weather);
}

function updateTrees(snapshot) {
  if (!state.treeLayer) initialiseTrees(snapshot);
  if (!state.treeLayer) return;
  const version = Number(snapshot.satellite.texture_version || 0) * 100000 + Number(snapshot.desertification.scenario_tick || 0);
  state.treeLayer.setTrees(snapshot.trees || [], version);
  state.treeLayer.setWeather(snapshot.weather);
}

function renderWeather(snapshot) {
  const weather = snapshot.weather;
  setText("lga-weather-mode", String(weather.mode || "unavailable").toUpperCase());
  setText("lga-temperature", number(weather.temperature_c, 1, "°C"));
  setText("lga-condition", `${weather.condition} • feels ${number(weather.feels_like_c, 1, "°C")}`);
  setText("lga-humidity", number(weather.humidity_percent, 0, "%"));
  setText("lga-wind", `${number(weather.wind_speed_mps, 1, " m/s")} ${weather.wind_direction_cardinal || ""}`);
  setText("lga-pressure", number(weather.pressure_hpa, 0, " hPa"));
  setText("lga-rain", number(weather.rain_1h_mm, 1, " mm"));
  setText("lga-clouds", number(weather.cloud_cover_percent, 0, "%"));
  setText("lga-visibility", weather.visibility_km == null ? "Not reported" : number(weather.visibility_km, 1, " km"));
  sky.update(weather);
}

function renderMetrics(snapshot) {
  const sat = snapshot.satellite.stats;
  setText("lga-satellite-mode", String(snapshot.satellite.mode || "unavailable").toUpperCase());
  setText("lga-ndvi", number(sat.mean, 2));
  setText("lga-ndvi-class", ndviClass(sat.mean));
  setText("lga-valid", pct(sat.valid_fraction)); setWidth("lga-valid-bar", Number(sat.valid_fraction) * 100);
  setText("lga-dense", pct(sat.dense_fraction)); setWidth("lga-dense-bar", Number(sat.dense_fraction) * 100);
  const bareSparse = Number(sat.bare_fraction || 0) + Number(sat.sparse_fraction || 0);
  setText("lga-bare", pct(bareSparse)); setWidth("lga-bare-bar", bareSparse * 100);
  setText("lga-vegetated", pct(snapshot.vegetation.modelled_vegetated_fraction));
  setText("lga-desert", `${riskLabel(snapshot.desertification.mean_pressure)} • ${number(snapshot.desertification.mean_pressure, 2)}`);
  setText("lga-suitability", `${riskLabel(1 - snapshot.restoration.mean_suitability)} opportunity • ${number(snapshot.restoration.mean_suitability, 2)}`);
  setText("lga-risk", `${riskLabel(snapshot.risk.combined_mean)} • ${number(snapshot.risk.combined_mean, 2)}`);
  setText("lga-tree-count", Number(snapshot.vegetation.tree_instances || 0).toLocaleString());
  setText("lga-area", number(snapshot.geography.area_km2_approx, 1, " km²"));
}

function renderLandcover(snapshot) {
  const container = document.getElementById("lga-landcover");
  if (!container) return;
  const entries = Object.entries(snapshot.landcover.classes || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  container.innerHTML = entries.map(([name, value]) => `<div class="landcover-row"><span>${escapeHtml(name.replaceAll("_", " "))}</span><div class="landcover-track"><i style="width:${Math.max(1, Number(value) * 100)}%"></i></div><b>${pct(value)}</b></div>`).join("");
}

function renderAlerts(snapshot) {
  const container = document.getElementById("lga-alerts");
  const alerts = snapshot.alerts || [];
  setText("lga-alert-count", String(alerts.length));
  if (!container) return;
  container.innerHTML = alerts.map((item) => `<article class="lga-alert ${escapeHtml(item.severity)}"><span class="alert-dot"></span><div><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.body)}</p></div></article>`).join("");
}

function renderRegistry(snapshot) {
  setText("lga-project-count", String(snapshot.projects.length));
  setText("lga-projects", String(snapshot.projects.length));
  setText("lga-field", String(snapshot.field_observations.length));
  setText("lga-hotspots", String(snapshot.thermal_anomalies.count));
  const container = document.getElementById("lga-project-list");
  if (!container) return;
  if (!snapshot.projects.length) {
    container.innerHTML = `<p class="empty-note">No restoration project is currently linked to this LGA registry.</p>`;
    return;
  }
  container.innerHTML = snapshot.projects.slice(0, 5).map((project) => `<article><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.status)} • ${Number(project.planted_trees || 0).toLocaleString()} planted</span></article>`).join("");
}

function renderInterpretations(snapshot) {
  const container = document.getElementById("lga-interpretations");
  if (!container) return;
  container.innerHTML = (snapshot.interpretations || []).map((item) => `<article class="insight ${escapeHtml(item.kind)}"><span class="kind">${escapeHtml(item.kind)}</span><h4>${escapeHtml(item.title)}</h4><p>${escapeHtml(item.body)}</p>${item.evidence?.length ? `<ul>${item.evidence.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul>` : ""}</article>`).join("");
}

function renderProvenance(snapshot) {
  setText("lga-source-mode", String(snapshot.source_mode || "unavailable").toUpperCase());
  const provenance = document.getElementById("lga-provenance");
  const limitations = document.getElementById("lga-limitations");
  if (provenance) provenance.innerHTML = (snapshot.provenance || []).map((item) => `<article><span>${escapeHtml(item.kind)}</span><strong>${escapeHtml(item.source)}</strong><em>${escapeHtml(item.mode)}</em></article>`).join("");
  if (limitations) limitations.innerHTML = `<h3>Use limitations</h3><ul>${(snapshot.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderEcosystems(snapshot) {
  const container = document.getElementById("lga-ecosystems");
  if (!container) return;
  const carbon = snapshot.carbon_ecosystems;
  const services = carbon.ecosystem_service_scores || {};
  container.innerHTML = `<div class="carbon-summary"><div><small>Biomass density</small><strong>${number(carbon.aboveground_biomass_density_mg_ha, 1, " Mg/ha")}</strong></div><div><small>Estimated carbon</small><strong>${Number(carbon.estimated_total_carbon_t || 0).toLocaleString()} t</strong></div><div><small>Uncertainty</small><strong>±${number(carbon.uncertainty_mg_ha, 1, " Mg/ha")}</strong></div></div>${Object.entries(services).map(([name, value]) => `<div class="ecosystem-row"><span>${escapeHtml(name.replaceAll("_", " "))}</span><div><i style="width:${Number(value)}%"></i></div><b>${number(value, 0)}</b></div>`).join("")}`;
}

function prepareCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 1.6);
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: rect.width, height: rect.height };
}

function drawSeries(canvasId, datasets, labels = []) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = prepareCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 38, right: 14, top: 16, bottom: 28 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  ctx.strokeStyle = "rgba(180,220,210,.14)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) { const y = pad.top + plotH * i / 4; ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke(); }
  const all = datasets.flatMap((item) => item.values).filter(Number.isFinite);
  let min = Math.min(...all, 0); let max = Math.max(...all, 1);
  if (max - min < 0.001) max = min + 1;
  datasets.forEach((dataset) => {
    ctx.strokeStyle = dataset.color; ctx.lineWidth = 2.2; ctx.beginPath();
    dataset.values.forEach((value, index) => {
      const x = pad.left + (dataset.values.length <= 1 ? 0 : index / (dataset.values.length - 1)) * plotW;
      const y = pad.top + (1 - (value - min) / (max - min)) * plotH;
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  ctx.fillStyle = "rgba(205,228,219,.68)"; ctx.font = "10px sans-serif";
  if (labels.length) { ctx.fillText(labels[0] || "", pad.left, height - 8); const last = labels[labels.length - 1] || ""; ctx.fillText(last, width - pad.right - ctx.measureText(last).width, height - 8); }
  let legendX = pad.left;
  datasets.forEach((dataset) => { ctx.fillStyle = dataset.color; ctx.fillRect(legendX, 5, 13, 2); ctx.fillStyle = "rgba(230,244,237,.82)"; ctx.fillText(dataset.label, legendX + 18, 9); legendX += 92; });
}

function renderCharts(snapshot) {
  const timeline = snapshot.timeline?.points || [];
  setText("lga-timeline-mode", String(snapshot.timeline?.mode || "unavailable").toUpperCase());
  drawSeries("lga-timeline-chart", [
    { label: "NDVI", color: "#48e58e", values: timeline.map((item) => Number(item.ndvi)) },
    { label: "Desert", color: "#ffad45", values: timeline.map((item) => Number(item.desert_fraction)) },
  ], timeline.map((item) => item.period));
  const forecast = (snapshot.forecast?.points || []).slice(0, 16);
  drawSeries("lga-forecast-chart", [
    { label: "Temp °C", color: "#ffad45", values: forecast.map((item) => Number(item.temperature_c) / 50) },
    { label: "Rain prob.", color: "#42a8ff", values: forecast.map((item) => Number(item.precipitation_probability)) },
    { label: "Cloud", color: "#d1e4e6", values: forecast.map((item) => Number(item.cloud_cover_percent) / 100) },
  ], forecast.map((item) => new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })));
}

function renderSnapshot(snapshot, first = false) {
  state.snapshot = snapshot;
  document.title = `${snapshot.name} Digital Twin | Gombe Restoration Intelligence`;
  setText("lga-header-title", `${snapshot.name} Digital Twin`);
  setText("lga-name", snapshot.name);
  setText("lga-scope", snapshot.northern_focus ? "Northern-focus LGA twin" : "Gombe State LGA twin");
  setText("lga-map-summary", `${snapshot.weather.condition}; NDVI ${number(snapshot.satellite.stats.mean, 2)}; ${riskLabel(snapshot.desertification.mean_pressure).toLowerCase()} desert-pressure screening.`);
  setText("lga-updated", `Last updated ${formatDateTime(snapshot.generated_at)}`);
  setText("lga-live-frame", `${snapshot.name.toUpperCase()} LIVE SERVICE • ${String(snapshot.source_mode).toUpperCase()}`);
  renderWeather(snapshot); renderMetrics(snapshot); renderLandcover(snapshot); renderAlerts(snapshot); renderRegistry(snapshot); renderInterpretations(snapshot); renderProvenance(snapshot); renderEcosystems(snapshot); renderCharts(snapshot); updateTrees(snapshot);
  if (first) fitLocal(0);
}

async function loadInitial() {
  try {
    const [catalogue, localBoundary, snapshot] = await Promise.all([
      fetchJson("/api/lga-twins"),
      fetchJson(`/api/lga-twins/${encodeURIComponent(slug)}/boundary`),
      fetchJson(`/api/lga-twins/${encodeURIComponent(slug)}/snapshot`),
    ]);
    state.catalogue = catalogue;
    const select = document.getElementById("lga-select");
    if (select) {
      select.innerHTML = catalogue.map((item) => `<option value="${escapeHtml(item.slug)}" ${item.slug === snapshot.slug ? "selected" : ""}>${escapeHtml(item.name)}${item.northern_focus ? " • northern focus" : ""}</option>`).join("");
    }
    boundary = localBoundary;
    bounds = snapshot.geography.bbox;
    if (mapReady) { addBoundary(localBoundary); await loadMapLayers(snapshot); initialiseTrees(snapshot); fitLocal(0); }
    renderSnapshot(snapshot, true);
    connectSocket();
  } catch (error) {
    showToast(`Could not load LGA digital twin: ${error.message}`, 7000);
    setText("lga-name", "LGA twin unavailable");
  }
}

function connectSocket() {
  if (state.destroyed) return;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  updateConnection("connecting");
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/lga/${encodeURIComponent(slug)}`);
  state.socket = socket;
  socket.addEventListener("open", () => { state.socketRetry = 1000; updateConnection("online"); });
  socket.addEventListener("message", (event) => {
    try { renderSnapshot(JSON.parse(event.data)); } catch (error) { console.warn("Invalid LGA frame", error); }
  });
  socket.addEventListener("close", () => {
    updateConnection("offline");
    if (!state.destroyed) { window.setTimeout(connectSocket, state.socketRetry); state.socketRetry = Math.min(15000, state.socketRetry * 1.7); }
  });
  socket.addEventListener("error", () => socket.close());
}

function orbitLoop(time) {
  state.orbitFrame = requestAnimationFrame(orbitLoop);
  if (!state.orbit || !mapReady || document.hidden || map.isMoving()) return;
  const speed = state.snapshot ? 0.0014 + Math.min(0.002, Number(state.snapshot.weather.wind_speed_mps || 0) * 0.00008) : 0.0014;
  map.rotateTo((map.getBearing() + speed * 16) % 360, { duration: 0 });
  if (state.snapshot && Number(state.snapshot.weather.cloud_cover_percent || 0) >= 35 && Math.floor(time / 2200) !== Math.floor((time - 16) / 2200)) {
    const center = state.snapshot.geography.centroid;
    const direction = Number(state.snapshot.weather.wind_direction_deg || 0) * Math.PI / 180;
    const offset = 0.005 + Math.min(0.018, Number(state.snapshot.weather.wind_speed_mps || 0) * 0.0012);
    map.easeTo({ center: [center.longitude + Math.sin(direction) * offset, center.latitude + Math.cos(direction) * offset], duration: 1900, essential: false });
  }
}

map.on("load", async () => {
  mapReady = true;
  try {
    map.addSource("terrain-dem", { type: "raster-dem", url: TERRAIN_SOURCE, tileSize: 256 });
    map.setTerrain({ source: "terrain-dem", exaggeration: 1.45 });
  } catch (error) { console.warn("Terrain unavailable", error); }
  if (boundary) addBoundary(boundary);
  if (state.snapshot) { await loadMapLayers(state.snapshot); initialiseTrees(state.snapshot); fitLocal(0); }
});

function navigate(delta) {
  if (!state.catalogue.length || !state.snapshot) return;
  const index = state.catalogue.findIndex((item) => item.slug === state.snapshot.slug);
  const target = state.catalogue[(index + delta + state.catalogue.length) % state.catalogue.length];
  if (target) window.location.href = target.route;
}

document.getElementById("lga-select")?.addEventListener("change", (event) => { window.location.href = `/lga/${encodeURIComponent(event.target.value)}`; });
document.getElementById("lga-prev")?.addEventListener("click", () => navigate(-1));
document.getElementById("lga-next")?.addEventListener("click", () => navigate(1));
document.getElementById("lga-refresh")?.addEventListener("click", async () => {
  try { const snapshot = await fetchJson(`/api/lga-twins/${encodeURIComponent(slug)}/snapshot`); renderSnapshot(snapshot); await loadMapLayers(snapshot, true); }
  catch (error) { showToast(`Refresh failed: ${error.message}`); }
});
document.querySelectorAll("[data-layer]").forEach((button) => button.addEventListener("click", () => setActiveLayer(button.dataset.layer)));
document.getElementById("lga-orbit")?.addEventListener("click", (event) => { state.orbit = !state.orbit; event.currentTarget.classList.toggle("active", state.orbit); });
document.getElementById("lga-3d")?.addEventListener("click", (event) => { state.pitch3d = !state.pitch3d; state.ground = false; event.currentTarget.classList.toggle("active", state.pitch3d); map.easeTo({ pitch: state.pitch3d ? 58 : 10, duration: 700 }); });
document.getElementById("lga-ground")?.addEventListener("click", (event) => { state.ground = !state.ground; event.currentTarget.classList.toggle("active", state.ground); map.easeTo({ pitch: state.ground ? 78 : 56, zoom: state.ground ? map.getZoom() + 1.4 : map.getZoom() - 1.0, bearing: state.ground ? -28 : -12, duration: 850 }); });
document.getElementById("lga-reset")?.addEventListener("click", () => fitLocal());
bindFullscreen("lga-full", "lga-map-shell", map);

document.querySelectorAll(".compact-sliders input[type=range]").forEach((input) => input.addEventListener("input", () => { const output = input.parentElement?.querySelector("output"); if (output) output.textContent = Number(input.value).toFixed(2); }));
document.getElementById("local-run-scenario")?.addEventListener("click", async () => {
  const payload = {
    aridity_pressure: Number(document.getElementById("local-aridity")?.value),
    grazing_pressure: Number(document.getElementById("local-grazing")?.value),
    rainfall_support: Number(document.getElementById("local-rainfall")?.value),
    restoration_effort: Number(document.getElementById("local-restoration")?.value),
    barrier_maintenance: Number(document.getElementById("local-maintenance")?.value),
    steps: 48,
  };
  try {
    setText("local-scenario-result", "Running experiment…");
    const result = await fetchJson(`/api/lga-twins/${encodeURIComponent(slug)}/scenario`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    drawSeries("local-scenario-chart", [
      { label: "Vegetation", color: "#48e58e", values: result.series.map((item) => item.vegetation) },
      { label: "Desert", color: "#ffad45", values: result.series.map((item) => item.desert) },
      { label: "Barrier", color: "#42e5cf", values: result.series.map((item) => item.barrier) },
    ], result.series.map((item) => String(item.step)));
    setText("local-scenario-result", `Vegetation ${result.outcome.vegetation_change >= 0 ? "+" : ""}${pct(result.outcome.vegetation_change)} • desert ${result.outcome.desert_change >= 0 ? "+" : ""}${pct(result.outcome.desert_change)}`);
  } catch (error) { showToast(`Scenario failed: ${error.message}`); setText("local-scenario-result", "Experiment failed."); }
});

window.addEventListener("resize", () => { map.resize(); if (state.snapshot) renderCharts(state.snapshot); }, { passive: true });
window.addEventListener("beforeunload", () => { state.destroyed = true; state.socket?.close(); if (state.orbitFrame) cancelAnimationFrame(state.orbitFrame); });
requestAnimationFrame(orbitLoop);
loadInitial();
