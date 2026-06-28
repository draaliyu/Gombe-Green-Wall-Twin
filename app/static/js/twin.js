import {
  AOI,
  LiveSocket,
  bindAreaInteraction,
  bindFullscreen,
  createMap,
  fetchJson,
  fitNorth,
  fitState,
  formatDateTime,
  formatNumber,
  formatPercent,
  setLayerVisible,
  setText,
  setWidth,
  showToast,
  updateConnection,
  updateSourceBadge,
  weatherSummary,
} from "./common.js";
import { LiveSky } from "./sky.js";
import { TreeLayer } from "./trees3d.js";

const map = createMap("twin-map", { pitch: 50, bearing: -8, zoom: 7.7, exaggeration: 1.45 });
const shell = document.getElementById("twin-map-shell");
const sky = new LiveSky(shell);
const treeLayer = new TreeLayer("three-trees", [11.2, 10.83]);
let latestFrame = null;
let orbiting = false;
let orbitHandle = 0;
let showingRisk = true;
let treeVisible = true;
let weatherVisible = true;
let lastNDVIVersion = -1;
let lastSimulationVersion = -1;
let lastTreeVersion = -1;
let selectedArea = null;

map.on("administrativeready", () => {
  map.addSource("ndvi-ground", { type: "image", url: `/api/ndvi/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
  map.addLayer({ id: "ndvi-ground-layer", type: "raster", source: "ndvi-ground", paint: { "raster-opacity": 0.78, "raster-fade-duration": 800 } }, "northern-focus-fill");
  map.addSource("simulation-ground", { type: "image", url: `/api/simulation/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
  map.addLayer({ id: "simulation-ground-layer", type: "raster", source: "simulation-ground", paint: { "raster-opacity": 0.34, "raster-fade-duration": 500 } }, "northern-focus-fill");
  map.addLayer(treeLayer, "lga-centre-points");
  fitState(map, window.innerWidth < 760 ? 22 : 48);
  refreshTrees();
});

map.on("administrativeready", () => {
  bindAreaInteraction(map, (feature) => openArea(feature.properties?.slug));
});

async function refreshTrees() {
  try {
    const payload = await fetchJson("/api/simulation/trees");
    treeLayer.setTrees(payload.features, payload.version);
    treeLayer.setWeather(payload.weather);
    lastTreeVersion = payload.version;
  } catch (error) {
    console.warn("Tree refresh failed", error);
  }
}

function updateImageSource(id, url) {
  const source = map.getSource(id);
  source?.updateImage?.({ url: `${url}?t=${Date.now()}`, coordinates: AOI.coordinates });
}

function renderInsights(items) {
  const container = document.getElementById("insight-list");
  if (!container) return;
  container.innerHTML = "";
  (items || []).slice(0, 6).forEach((item) => {
    const article = document.createElement("article");
    article.className = `insight ${item.kind}`;
    const evidence = Array.isArray(item.evidence) && item.evidence.length
      ? `<ul>${item.evidence.slice(0, 4).map((entry) => `<li>${entry}</li>`).join("")}</ul>` : "";
    article.innerHTML = `<span class="kind">${item.kind}</span><h4>${item.title}</h4><p>${item.body}</p>${evidence}`;
    container.appendChild(article);
  });
}

async function openArea(slug) {
  if (!slug) return;
  try {
    selectedArea = await fetchJson(`/api/areas/${slug}`);
    const drawer = document.getElementById("area-drawer");
    drawer?.classList.add("open");
    setText("area-name", selectedArea.name);
    setText("area-scope", selectedArea.northern_focus ? "Northern Gombe focus LGA" : "Gombe State context LGA");
    setText("area-ndvi", selectedArea.satellite.mean_ndvi == null ? "No intersecting pixels" : Number(selectedArea.satellite.mean_ndvi).toFixed(2));
    setText("area-bare", selectedArea.satellite.bare_fraction == null ? "No data" : formatPercent(selectedArea.satellite.bare_fraction));
    setText("area-weather", weatherSummary(selectedArea.weather));
    setText("area-desert", selectedArea.simulation.desert_fraction == null ? "Outside northern model grid" : formatPercent(selectedArea.simulation.desert_fraction));
    setText("area-barrier", selectedArea.simulation.barrier_fraction == null ? "Outside northern model grid" : formatPercent(selectedArea.simulation.barrier_fraction, 2));
    const interpretations = document.getElementById("area-interpretations");
    if (interpretations) {
      interpretations.innerHTML = selectedArea.interpretation.map((item) => `<article><h4>${item.title}</h4><p>${item.body}</p></article>`).join("");
    }
    const { longitude, latitude } = selectedArea.centroid;
    map.easeTo({ center: [longitude, latitude], zoom: 9.0, pitch: 48, duration: 850 });
  } catch (error) {
    showToast(`Could not load LGA evidence: ${error.message}`);
  }
}

function applyFrame(frame) {
  latestFrame = frame;
  setText("header-frame", String(frame.sequence).padStart(6, "0"));
  setText("last-updated", `Live frame ${frame.sequence.toLocaleString()} • ${formatDateTime(frame.generated_at)}`);
  updateSourceBadge("sentinel-mode", frame.satellite.mode);
  updateSourceBadge("gfw-mode", frame.gfw.mode);
  updateSourceBadge("weather-mode", frame.weather.mode);
  setText("map-scene-subtitle", `${weatherSummary(frame.weather)} • simulation tick ${frame.simulation.metrics.tick.toLocaleString()}`);
  setText("map-ndvi", formatNumber(frame.satellite.stats.mean, 2));
  setText("map-desert", formatPercent(frame.simulation.metrics.desert_fraction));
  setText("map-tree-health", formatPercent(frame.simulation.metrics.mean_tree_health));
  setText("ndvi-mean", formatNumber(frame.satellite.stats.mean, 2));
  setText("ndvi-window", `${new Date(frame.satellite.observation_window_start).toLocaleDateString()} – ${new Date(frame.satellite.observation_window_end).toLocaleDateString()}`);
  setText("ndvi-valid", formatPercent(frame.satellite.stats.valid_fraction));
  setText("ndvi-bare", formatPercent(frame.satellite.stats.bare_fraction));
  setText("ndvi-dense", formatPercent(frame.satellite.stats.dense_fraction));
  setWidth("green-meter", frame.satellite.stats.mean * 100 / 0.75);
  setText("green-meter-label", `NDVI ${formatNumber(frame.satellite.stats.mean, 2)}`);

  const metrics = frame.simulation.metrics;
  setText("sim-vegetated", formatPercent(metrics.vegetated_fraction));
  setText("sim-desert", formatPercent(metrics.desert_fraction));
  setText("sim-barrier", formatPercent(metrics.barrier_fraction, 2));
  setText("sim-front", metrics.desert_front_cells.toLocaleString());
  setWidth("desert-meter", metrics.desert_fraction * 100);
  setText("desert-meter-label", formatPercent(metrics.desert_fraction));
  setText("weather-temp", `${Number(frame.weather.temperature_c).toFixed(1)}°C`);
  setText("weather-humidity", `${Number(frame.weather.humidity_percent).toFixed(0)}%`);
  setText("weather-wind", `${Number(frame.weather.wind_speed_mps).toFixed(1)} m/s ${frame.weather.wind_direction_cardinal}`);
  setText("weather-rain", `${Number(frame.weather.rain_1h_mm).toFixed(1)} mm`);
  setText("weather-sky", frame.weather.is_daylight ? "Daylight" : "Night sky");
  setText("weather-condition", frame.weather.condition);
  setWidth("weather-moisture", metrics.weather_moisture_forcing * 100);
  setWidth("weather-heat", metrics.weather_heat_stress * 100);
  sky.update(frame.weather);
  treeLayer.setWeather(frame.weather);
  renderInsights(frame.insights);

  if (frame.satellite.texture_version !== lastNDVIVersion && map.loaded()) {
    updateImageSource("ndvi-ground", "/api/ndvi/texture.png");
    lastNDVIVersion = frame.satellite.texture_version;
  }
  if (frame.simulation.texture_version !== lastSimulationVersion && map.loaded()) {
    updateImageSource("simulation-ground", "/api/simulation/texture.png");
    lastSimulationVersion = frame.simulation.texture_version;
  }
  if (frame.simulation.tree_version !== lastTreeVersion) refreshTrees();
}

new LiveSocket(applyFrame, updateConnection);

document.getElementById("view-state")?.addEventListener("click", () => fitState(map, window.innerWidth < 760 ? 22 : 48));
document.getElementById("view-north")?.addEventListener("click", () => fitNorth(map, window.innerWidth < 760 ? 22 : 48));
document.getElementById("view-ndvi")?.addEventListener("click", (event) => {
  event.currentTarget.classList.toggle("active");
  setLayerVisible(map, "ndvi-ground-layer", event.currentTarget.classList.contains("active"));
});
document.getElementById("view-risk")?.addEventListener("click", (event) => {
  showingRisk = !showingRisk;
  event.currentTarget.classList.toggle("active", showingRisk);
  setLayerVisible(map, "simulation-ground-layer", showingRisk);
});
document.getElementById("toggle-trees")?.addEventListener("click", (event) => {
  treeVisible = !treeVisible;
  treeLayer.setVisible(treeVisible);
  event.currentTarget.classList.toggle("active", treeVisible);
});
document.getElementById("toggle-weather")?.addEventListener("click", (event) => {
  weatherVisible = !weatherVisible;
  sky.canvas.style.display = weatherVisible ? "block" : "none";
  event.currentTarget.classList.toggle("active", weatherVisible);
});
document.getElementById("toggle-run")?.addEventListener("click", async () => {
  if (!latestFrame) return;
  const running = !latestFrame.simulation.running;
  await fetchJson("/api/simulation/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ running }) });
  setText("run-label", running ? "Pause" : "Run");
  setText("run-icon", running ? "Ⅱ" : "▶");
});
document.getElementById("toggle-orbit")?.addEventListener("click", (event) => {
  orbiting = !orbiting;
  event.currentTarget.classList.toggle("active", orbiting);
  if (!orbiting) cancelAnimationFrame(orbitHandle);
  const orbit = () => {
    if (!orbiting) return;
    map.rotateTo((map.getBearing() + 0.08) % 360, { duration: 0 });
    orbitHandle = requestAnimationFrame(orbit);
  };
  orbit();
});
document.getElementById("close-area")?.addEventListener("click", () => document.getElementById("area-drawer")?.classList.remove("open"));
bindFullscreen("fullscreen-map", "twin-map-shell", map);
window.addEventListener("resize", () => map.resize(), { passive: true });
