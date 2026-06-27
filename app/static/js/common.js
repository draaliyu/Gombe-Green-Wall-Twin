export const AOI = {
  west: 10.55,
  south: 10.20,
  east: 11.85,
  north: 11.55,
  coordinates: [
    [10.55, 11.55],
    [11.85, 11.55],
    [11.85, 10.20],
    [10.55, 10.20],
  ],
};

export const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
export const TERRAIN_SOURCE = "https://demotiles.maplibre.org/terrain-tiles/tiles.json";

export function formatPercent(value, digits = 1) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(digits)}%` : "—";
}

export function formatNumber(value, digits = 2) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "—";
}

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
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
  if (path.startsWith("/satellite")) return "satellite";
  if (path.startsWith("/simulation")) return "simulation";
  if (path.startsWith("/planner")) return "planner";
  if (path.startsWith("/evidence")) return "evidence";
  return "twin";
}

export function highlightNav() {
  const page = currentPage();
  document.querySelectorAll("[data-nav]").forEach((link) => {
    link.classList.toggle("active", link.dataset.nav === page);
  });
}

export function showToast(message, timeout = 3200) {
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
    this.socket.addEventListener("open", () => {
      this.retry = 1000;
      this.onStatus("online");
    });
    this.socket.addEventListener("message", (event) => {
      try {
        this.onFrame(JSON.parse(event.data));
      } catch (error) {
        console.error("Invalid live frame", error);
      }
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

  close() {
    this.closed = true;
    this.socket?.close();
  }
}

export function updateConnection(status) {
  const dot = document.querySelector("[data-connection-dot]");
  const text = document.querySelector("[data-connection-text]");
  if (text) text.textContent = status.toUpperCase();
  if (dot) dot.classList.toggle("demo", status !== "online");
}

export async function addBoundaryAndLocations(map) {
  const [boundary, locations] = await Promise.all([
    fetchJson("/api/boundary"),
    fetchJson("/api/locations"),
  ]);
  if (!map.getSource("gombe-boundary")) {
    map.addSource("gombe-boundary", { type: "geojson", data: boundary });
    map.addLayer({
      id: "gombe-fill",
      type: "fill",
      source: "gombe-boundary",
      paint: { "fill-color": "#19352d", "fill-opacity": 0.06 },
    });
    map.addLayer({
      id: "gombe-outline-glow",
      type: "line",
      source: "gombe-boundary",
      paint: { "line-color": "#69f0aa", "line-width": 5, "line-opacity": 0.16, "line-blur": 3 },
    });
    map.addLayer({
      id: "gombe-outline",
      type: "line",
      source: "gombe-boundary",
      paint: { "line-color": "#9bffd0", "line-width": 1.5, "line-opacity": 0.8 },
    });
  }
  if (!map.getSource("reference-locations")) {
    map.addSource("reference-locations", { type: "geojson", data: locations });
    map.addLayer({
      id: "reference-location-points",
      type: "circle",
      source: "reference-locations",
      paint: {
        "circle-radius": 4,
        "circle-color": "#d6ff74",
        "circle-stroke-color": "#071716",
        "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "reference-location-labels",
      type: "symbol",
      source: "reference-locations",
      layout: {
        "text-field": ["get", "name"],
        "text-size": 11,
        "text-offset": [0, 1.1],
        "text-anchor": "top",
        "text-allow-overlap": false,
      },
      paint: {
        "text-color": "#f5fff7",
        "text-halo-color": "#061011",
        "text-halo-width": 2,
      },
    });
  }
}

export function createMap(container, options = {}) {
  const map = new maplibregl.Map({
    container,
    style: MAP_STYLE,
    center: options.center || [11.18, 10.82],
    zoom: options.zoom || 8.25,
    pitch: options.pitch ?? 52,
    bearing: options.bearing ?? -10,
    antialias: true,
    maxBounds: [[10.25, 9.95], [12.10, 11.75]],
    attributionControl: false,
  });
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
  if (window.innerWidth > 760) {
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  }
  map.on("load", async () => {
    try {
      if (!map.getSource("terrain-dem")) {
        map.addSource("terrain-dem", { type: "raster-dem", url: TERRAIN_SOURCE, tileSize: 256 });
        map.setTerrain({ source: "terrain-dem", exaggeration: options.exaggeration || 1.35 });
      }
    } catch (error) {
      console.warn("Terrain unavailable", error);
    }
    await addBoundaryAndLocations(map);
  });
  return map;
}

export function fitAOI(map, padding = 42) {
  map.fitBounds([[AOI.west, AOI.south], [AOI.east, AOI.north]], {
    padding,
    duration: 900,
    pitch: window.innerWidth <= 760 ? 32 : 52,
    bearing: -10,
  });
}

export function bindFullscreen(buttonId, targetId, map) {
  const button = document.getElementById(buttonId);
  const target = document.getElementById(targetId);
  if (!button || !target) return;
  button.addEventListener("click", async () => {
    if (!document.fullscreenElement) {
      await target.requestFullscreen?.();
    } else {
      await document.exitFullscreen?.();
    }
    window.setTimeout(() => map.resize(), 120);
  });
}

highlightNav();
