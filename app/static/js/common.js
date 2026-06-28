export const AOI = {
  west: 10.55,
  south: 10.20,
  east: 11.85,
  north: 11.55,
  coordinates: [[10.55, 11.55], [11.85, 11.55], [11.85, 10.20], [10.55, 10.20]],
};

export const STATE_BOUNDS = [[10.24, 9.43], [12.31, 11.72]];
export const NORTH_BOUNDS = [[10.38, 10.08], [11.86, 11.55]];
export const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
export const TERRAIN_SOURCE = "https://demotiles.maplibre.org/terrain-tiles/tiles.json";

export function formatPercent(value, digits = 1) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(digits)}%` : "Not available";
}

export function formatNumber(value, digits = 2) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "Not available";
}

export function formatDateTime(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return date.toLocaleString([], { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatClock(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

export function setWidth(id, value) {
  const element = document.getElementById(id);
  if (element) element.style.width = `${Math.max(0, Math.min(100, Number(value) || 0))}%`;
}

export function updateSourceBadge(id, mode) {
  const element = document.getElementById(id);
  if (!element) return;
  const label = String(mode || "unavailable").toUpperCase();
  element.textContent = label;
  element.classList.toggle("demo", mode !== "live");
}

export function currentPage() {
  const path = window.location.pathname;
  if (path.startsWith("/areas")) return "areas";
  if (path.startsWith("/weather")) return "weather";
  if (path.startsWith("/satellite")) return "satellite";
  if (path.startsWith("/simulation")) return "simulation";
  if (path.startsWith("/planner")) return "planner";
  if (path.startsWith("/evidence")) return "evidence";
  return "twin";
}

export function highlightNav() {
  const page = currentPage();
  document.querySelectorAll("[data-nav]").forEach((link) => link.classList.toggle("active", link.dataset.nav === page));
}

export function showToast(message, timeout = 3400) {
  let toast = document.getElementById("app-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "app-toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), timeout);
}

export function fetchJson(url, options = {}) {
  return fetch(url, options).then(async (response) => {
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `${response.status} ${response.statusText}`);
    }
    return response.json();
  });
}

export class LiveSocket {
  constructor(onFrame, onStatus = () => {}) {
    this.onFrame = onFrame;
    this.onStatus = onStatus;
    this.socket = null;
    this.retry = 1000;
    this.closed = false;
    this.connect();
  }

  connect() {
    if (this.closed) return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    this.onStatus("connecting");
    this.socket = new WebSocket(`${protocol}://${window.location.host}/ws/live`);
    this.socket.addEventListener("open", () => { this.retry = 1000; this.onStatus("online"); });
    this.socket.addEventListener("message", (event) => {
      try { this.onFrame(JSON.parse(event.data)); } catch (error) { console.error("Invalid live frame", error); }
    });
    this.socket.addEventListener("close", () => {
      this.onStatus("offline");
      if (!this.closed) {
        window.setTimeout(() => this.connect(), this.retry);
        this.retry = Math.min(this.retry * 1.7, 15000);
      }
    });
    this.socket.addEventListener("error", () => this.socket?.close());
  }

  close() { this.closed = true; this.socket?.close(); }
}

export function updateConnection(status) {
  const dot = document.querySelector("[data-connection-dot]");
  const text = document.querySelector("[data-connection-text]");
  if (text) text.textContent = status.toUpperCase();
  if (dot) dot.classList.toggle("demo", status !== "online");
}

function sourceData(map, id, data) {
  if (map.getSource(id)) map.getSource(id).setData(data);
  else map.addSource(id, { type: "geojson", data });
}

export async function addAdministrativeLayers(map) {
  const [boundary, lgas, north, locations] = await Promise.all([
    fetchJson("/api/boundary"), fetchJson("/api/lgas"), fetchJson("/api/northern-lgas"), fetchJson("/api/locations"),
  ]);
  sourceData(map, "gombe-boundary", boundary);
  sourceData(map, "gombe-lgas", lgas);
  sourceData(map, "northern-lgas", north);
  sourceData(map, "lga-centres", locations);

  if (!map.getLayer("gombe-state-fill")) {
    map.addLayer({ id: "gombe-state-fill", type: "fill", source: "gombe-boundary", paint: { "fill-color": "#17332a", "fill-opacity": 0.14 } });
    map.addLayer({ id: "northern-focus-fill", type: "fill", source: "northern-lgas", paint: { "fill-color": "#54e995", "fill-opacity": 0.12 } });
    map.addLayer({ id: "northern-focus-glow", type: "line", source: "northern-lgas", paint: { "line-color": "#74ffac", "line-width": 8, "line-opacity": 0.16, "line-blur": 4 } });
    map.addLayer({ id: "northern-focus-outline", type: "line", source: "northern-lgas", paint: { "line-color": "#baffcf", "line-width": 2.8, "line-opacity": 0.96 } });
    map.addLayer({ id: "lga-hover-fill", type: "fill", source: "gombe-lgas", paint: { "fill-color": "#d6ff74", "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.20, 0] } });
    map.addLayer({ id: "lga-outline", type: "line", source: "gombe-lgas", paint: { "line-color": ["case", ["get", "northern_focus"], "#8bffc1", "#6e8d80"], "line-width": ["case", ["get", "northern_focus"], 2.0, 1.1], "line-opacity": 0.90 } });
    map.addLayer({ id: "gombe-state-outline-glow", type: "line", source: "gombe-boundary", paint: { "line-color": "#69f0aa", "line-width": 7, "line-opacity": 0.16, "line-blur": 4 } });
    map.addLayer({ id: "gombe-state-outline", type: "line", source: "gombe-boundary", paint: { "line-color": "#b4ffdb", "line-width": 2.2, "line-opacity": 0.95 } });
    map.addLayer({
      id: "lga-centre-points", type: "circle", source: "lga-centres",
      paint: { "circle-radius": ["case", ["get", "northern_focus"], 4.5, 3], "circle-color": ["case", ["get", "northern_focus"], "#d6ff74", "#7fb7a0"], "circle-stroke-color": "#061011", "circle-stroke-width": 1.5 },
    });
    map.addLayer({
      id: "lga-labels", type: "symbol", source: "lga-centres",
      layout: { "text-field": ["get", "name"], "text-size": ["case", ["get", "northern_focus"], 12, 10], "text-font": ["Noto Sans Bold"], "text-offset": [0, 1.15], "text-anchor": "top", "text-allow-overlap": false },
      paint: { "text-color": ["case", ["get", "northern_focus"], "#f6fff3", "#c1d3ca"], "text-halo-color": "#05100f", "text-halo-width": 2.4 },
    });
  }
  return { boundary, lgas, north, locations };
}

export function createMap(container, options = {}) {
  const map = new maplibregl.Map({
    container,
    style: MAP_STYLE,
    center: options.center || [11.20, 10.42],
    zoom: options.zoom || 7.65,
    pitch: options.pitch ?? 48,
    bearing: options.bearing ?? -8,
    antialias: true,
    maxBounds: [[10.05, 9.20], [12.48, 11.92]],
    attributionControl: false,
    cooperativeGestures: window.innerWidth <= 760,
  });
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
  if (window.innerWidth > 760) map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.on("load", async () => {
    try {
      if (!map.getSource("terrain-dem")) {
        map.addSource("terrain-dem", { type: "raster-dem", url: TERRAIN_SOURCE, tileSize: 256 });
        map.setTerrain({ source: "terrain-dem", exaggeration: options.exaggeration || 1.25 });
      }
    } catch (error) { console.warn("Terrain unavailable", error); }
    await addAdministrativeLayers(map);
    map.fire("administrativeready");
  });
  return map;
}

export function fitState(map, padding = 42) {
  map.fitBounds(STATE_BOUNDS, { padding, duration: 900, pitch: window.innerWidth <= 760 ? 22 : 42, bearing: 0 });
}

export function fitNorth(map, padding = 42) {
  map.fitBounds(NORTH_BOUNDS, { padding, duration: 900, pitch: window.innerWidth <= 760 ? 28 : 50, bearing: -8 });
}

export function fitAOI(map, padding = 42) { fitNorth(map, padding); }

export function bindFullscreen(buttonId, targetId, map) {
  const button = document.getElementById(buttonId);
  const target = document.getElementById(targetId);
  if (!button || !target) return;
  button.addEventListener("click", async () => {
    if (!document.fullscreenElement) await target.requestFullscreen?.();
    else await document.exitFullscreen?.();
    window.setTimeout(() => map.resize(), 140);
  });
}

export function setLayerVisible(map, id, visible) {
  if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
}

export function bindAreaInteraction(map, callback) {
  let hovered = null;
  map.on("mousemove", "lga-hover-fill", (event) => {
    const feature = event.features?.[0];
    if (!feature) return;
    if (hovered !== null) map.setFeatureState({ source: "gombe-lgas", id: hovered }, { hover: false });
    hovered = feature.id;
    if (hovered !== undefined && hovered !== null) map.setFeatureState({ source: "gombe-lgas", id: hovered }, { hover: true });
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "lga-hover-fill", () => {
    if (hovered !== null) map.setFeatureState({ source: "gombe-lgas", id: hovered }, { hover: false });
    hovered = null;
    map.getCanvas().style.cursor = "";
  });
  map.on("click", "lga-hover-fill", (event) => {
    const feature = event.features?.[0];
    if (feature) callback?.(feature);
  });
}

export function weatherSummary(weather) {
  if (!weather) return "Weather unavailable";
  const rain = Number(weather.rain_1h_mm || 0) > 0 ? ` • ${Number(weather.rain_1h_mm).toFixed(1)} mm rain` : "";
  return `${weather.condition} • ${Number(weather.temperature_c).toFixed(1)}°C • wind ${Number(weather.wind_speed_mps).toFixed(1)} m/s ${weather.wind_direction_cardinal}${rain}`;
}

highlightNav();
