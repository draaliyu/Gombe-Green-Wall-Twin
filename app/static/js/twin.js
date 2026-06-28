import {
  AOI,
  LiveSocket,
  bindAreaInteraction,
  bindFullscreen,
  createMap,
  fetchJson,
  fitState,
  formatDateTime,
  formatPercent,
  setLayerVisible,
  setText,
  showToast,
  updateConnection,
  updateSourceBadge,
  weatherSummary,
} from "./common.js";
import { LiveSky } from "./sky.js";
import { TreeLayer } from "./trees3d.js";
import {
  AtmosphereCanvas,
  WeatherFlowCanvas,
  WindFlowCanvas,
  drawBarChart,
  drawDonut,
  drawLineChart,
} from "./dashboard.js";

const stateCentre = [11.18, 10.55];
const northCentre = [11.16, 10.85];
const map = createMap("twin-map", { pitch: 53, bearing: -10, zoom: 7.55, exaggeration: 1.55 });
const shell = document.getElementById("twin-map-shell");
const sky = new LiveSky(shell);
const skyDome = new AtmosphereCanvas(document.getElementById("sky-dome"), { circular: true });
const panorama = new AtmosphereCanvas(document.getElementById("panorama-sky"), { circular: false });
const weatherFlow = new WeatherFlowCanvas(document.getElementById("weather-flow-canvas"));
const windFlow = new WindFlowCanvas(document.getElementById("wind-flow-canvas"));
const treeLayer = new TreeLayer("three-trees", [11.2, 10.83]);

let latestFrame = null;
let history = [];
let treeCount = 0;
let barrierTreeCount = 0;
let lastNDVIVersion = -1;
let lastSimulationVersion = -1;
let lastTreeVersion = -1;
let orbiting = true;
let orbitSpeed = 0.65;
let orbitLast = 0;
let orbitHandle = 0;
let orbitTargetMode = 0;
let firstPersonMode = false;
let globeMode = false;
let terrainEnabled = true;
let economyMode = window.innerWidth < 760 || navigator.connection?.saveData === true;
let flowRunning = true;
let selectedArea = null;
let weatherLayersReady = false;

const weatherLayerIds = {
  clouds: "provider-clouds",
  rain: "provider-rain",
  temp: "provider-temperature",
};

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, Number(value) || 0));
}

function classify(value, thresholds, labels) {
  for (let index = 0; index < thresholds.length; index += 1) {
    if (value < thresholds[index]) return labels[index];
  }
  return labels[labels.length - 1];
}

function setStatus(id, label, level = "normal") {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = label;
  element.classList.toggle("warn", level === "warn");
  element.classList.toggle("high", level === "high");
}

function addRasterLayer(id, sourceId, tiles, opacity, beforeId = "lga-outline") {
  if (!map.getSource(sourceId)) {
    map.addSource(sourceId, { type: "raster", tiles, tileSize: 256, maxzoom: 19, attribution: "Weather layers © OpenWeather" });
  }
  if (!map.getLayer(id)) {
    map.addLayer({
      id,
      type: "raster",
      source: sourceId,
      layout: { visibility: "visible" },
      paint: { "raster-opacity": opacity, "raster-fade-duration": 350 },
    }, map.getLayer(beforeId) ? beforeId : undefined);
  }
}

function initialiseSceneLayers() {
  if (weatherLayersReady) return;
  weatherLayersReady = true;
  if (!map.getSource("earth-imagery")) {
    map.addSource("earth-imagery", {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      attribution: "Background imagery © Esri and contributors",
      maxzoom: 18,
    });
    map.addLayer({ id: "earth-imagery-layer", type: "raster", source: "earth-imagery", paint: { "raster-opacity": 0.58, "raster-saturation": -0.12, "raster-contrast": 0.10, "raster-brightness-max": 0.82 } }, "gombe-state-fill");
  }
  addRasterLayer("provider-clouds", "provider-clouds-source", ["/api/weather/tiles/clouds_new/{z}/{x}/{y}.png"], 0.50, "lga-outline");
  addRasterLayer("provider-rain", "provider-rain-source", ["/api/weather/tiles/precipitation_new/{z}/{x}/{y}.png"], 0.62, "lga-outline");
  addRasterLayer("provider-temperature", "provider-temperature-source", ["/api/weather/tiles/temp_new/{z}/{x}/{y}.png"], 0.0, "lga-outline");

  map.addSource("ndvi-ground", { type: "image", url: `/api/ndvi/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
  map.addLayer({ id: "ndvi-ground-layer", type: "raster", source: "ndvi-ground", paint: { "raster-opacity": 0.55, "raster-fade-duration": 700, "raster-contrast": 0.12 } }, "northern-focus-fill");
  map.addSource("simulation-ground", { type: "image", url: `/api/simulation/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
  map.addLayer({ id: "simulation-ground-layer", type: "raster", source: "simulation-ground", paint: { "raster-opacity": 0.32, "raster-fade-duration": 500 } }, "northern-focus-fill");
  map.addSource("cloud-follow-target", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({ id: "cloud-follow-glow", type: "circle", source: "cloud-follow-target", paint: { "circle-radius": 20, "circle-color": "rgba(82,213,255,.10)", "circle-stroke-color": "rgba(126,236,255,.65)", "circle-stroke-width": 1.2, "circle-blur": 0.35 } }, "lga-labels");
  map.addLayer({ id: "cloud-follow-point", type: "circle", source: "cloud-follow-target", paint: { "circle-radius": 3.5, "circle-color": "#baf5ff", "circle-stroke-color": "#052129", "circle-stroke-width": 1.2 } }, "lga-labels");
  map.addLayer(treeLayer, "lga-centre-points");
}

map.on("administrativeready", () => {
  initialiseSceneLayers();
  fitState(map, window.innerWidth < 760 ? 18 : 38);
  refreshTrees();
  startOrbit();
});

map.on("administrativeready", () => bindAreaInteraction(map, (feature) => openArea(feature.properties?.slug)));
map.on("move", () => {
  const bearing = ((map.getBearing() % 360) + 360) % 360;
  setText("compass-bearing", `${String(Math.round(bearing)).padStart(3, "0")}°`);
  const needle = document.querySelector("#scene-compass i");
  if (needle) needle.style.transform = `rotate(${-bearing}deg)`;
});

async function refreshTrees() {
  try {
    const payload = await fetchJson("/api/simulation/trees");
    treeLayer.setTrees(payload.features, payload.version);
    treeLayer.setWeather(payload.weather);
    lastTreeVersion = payload.version;
    treeCount = payload.features.length;
    barrierTreeCount = payload.features.filter((item) => item.barrier).length;
    setText("summary-trees", treeCount.toLocaleString());
    setText("summary-tree-note", `${barrierTreeCount.toLocaleString()} barrier trees`);
  } catch (error) {
    console.warn("Tree refresh failed", error);
  }
}

function updateImageSource(id, url) {
  const source = map.getSource(id);
  source?.updateImage?.({ url: `${url}?t=${Date.now()}`, coordinates: AOI.coordinates });
}

function ndviLabel(value) {
  if (value < 0.15) return "Very sparse vegetation";
  if (value < 0.30) return "Sparse vegetation";
  if (value < 0.50) return "Moderate vegetation";
  return "Strong vegetation signal";
}

function weatherSymbol(weather) {
  const code = Number(weather.weather_code) || 0;
  if (code >= 200 && code < 300) return "⛈";
  if (code >= 300 && code < 600) return "🌧";
  if (code >= 600 && code < 700) return "❄";
  if (code >= 700 && code < 800) return "〰";
  if (code === 800) return weather.is_daylight ? "☀" : "☾";
  return weather.is_daylight ? "🌤" : "☁";
}

function cloudFollowCoordinate(weather, timestamp = Date.now()) {
  const cover = clamp(weather.cloud_cover_percent, 0, 100) / 100;
  const direction = (Number(weather.wind_direction_deg) || 0) * Math.PI / 180;
  const speed = clamp(weather.wind_speed_mps, 0, 16);
  const phase = timestamp / 1000 * (0.006 + speed * 0.0007);
  const radius = 0.025 + cover * 0.12;
  return [
    northCentre[0] + Math.sin(direction) * Math.sin(phase) * radius,
    northCentre[1] + Math.cos(direction) * Math.cos(phase * 0.82) * radius * 0.7,
  ];
}

function updateCloudTarget(weather) {
  const source = map.getSource("cloud-follow-target");
  if (!source) return;
  if (Number(weather.cloud_cover_percent) < 35) {
    source.setData({ type: "FeatureCollection", features: [] });
    return;
  }
  const coordinate = cloudFollowCoordinate(weather);
  source.setData({ type: "FeatureCollection", features: [{ type: "Feature", properties: { label: "Wind-driven cloud-flow focus" }, geometry: { type: "Point", coordinates: coordinate } }] });
}

function currentOrbitTarget() {
  if (orbitTargetMode === 1) return northCentre;
  if (orbitTargetMode === 2 && selectedArea?.centroid) return [selectedArea.centroid.longitude, selectedArea.centroid.latitude];
  if (latestFrame && Number(latestFrame.weather.cloud_cover_percent) >= 35) return cloudFollowCoordinate(latestFrame.weather);
  return stateCentre;
}

function startOrbit() {
  cancelAnimationFrame(orbitHandle);
  orbiting = true;
  document.getElementById("toggle-orbit")?.classList.add("active");
  const loop = (timestamp) => {
    orbitHandle = requestAnimationFrame(loop);
    if (!orbiting || document.hidden || !map.loaded()) return;
    if (timestamp - orbitLast < (economyMode ? 250 : 110)) return;
    orbitLast = timestamp;
    const target = currentOrbitTarget();
    const current = map.getCenter();
    const blend = economyMode ? 0.035 : 0.055;
    const center = [current.lng + (target[0] - current.lng) * blend, current.lat + (target[1] - current.lat) * blend];
    const bearing = (map.getBearing() + orbitSpeed * (economyMode ? 0.20 : 0.34)) % 360;
    map.jumpTo({ center, bearing, pitch: firstPersonMode ? 76 : 53 });
    if (latestFrame) updateCloudTarget(latestFrame.weather);
  };
  orbitHandle = requestAnimationFrame(loop);
}

function stopOrbit() {
  orbiting = false;
  cancelAnimationFrame(orbitHandle);
  document.getElementById("toggle-orbit")?.classList.remove("active");
}

function updateImageScene(frame) {
  const weather = frame.weather;
  document.body.classList.toggle("scene-night", !weather.is_daylight);
  setText("weather-symbol", weatherSymbol(weather));
  setText("scene-mode", orbiting
    ? Number(weather.cloud_cover_percent) >= 35 ? "AUTO ORBIT • WIND-DRIVEN CLOUD FOLLOW" : "AUTO ORBIT • STATE OVERVIEW"
    : "MANUAL CAMERA");
  setText("scene-title", `${weather.is_daylight ? "Daylight" : "Night"} environmental scene • ${weather.condition}`);
  setText("scene-subtitle", `${weatherSummary(weather)} • model tick ${frame.simulation.metrics.tick.toLocaleString()} • ${frame.source_mode.toUpperCase()} sources`);
  setText("orbit-status", orbiting ? (Number(weather.cloud_cover_percent) >= 35 ? "CLOUD FLOW FOLLOW ACTIVE" : "AUTO ORBIT ACTIVE") : "ORBIT PAUSED");
  setText("sky-mode-label", weather.is_daylight ? "DAY SKY" : "NIGHT SKY");
  setText("sky-source-note", `${weather.mode.toUpperCase()} weather: ${Number(weather.cloud_cover_percent).toFixed(0)}% clouds, ${Number(weather.wind_speed_mps).toFixed(1)} m/s wind from ${weather.wind_direction_cardinal}.`);
}

function updateStatusPanel(frame) {
  const ndvi = frame.satellite.stats.mean;
  const moisture = frame.simulation.metrics.weather_moisture_forcing;
  const desert = frame.simulation.metrics.desert_fraction;
  const heat = frame.simulation.metrics.weather_heat_stress;
  const windSignal = clamp((frame.weather.wind_speed_mps / 12) * (0.35 + frame.satellite.stats.bare_fraction), 0, 1);
  const loss = frame.gfw.latest_year_loss_ha;
  const vegetationLabel = classify(ndvi, [0.15, 0.30, 0.50], ["Very low", "Sparse", "Moderate", "Good"]);
  const moistureLabel = classify(moisture, [0.28, 0.58, 0.78], ["Low", "Medium", "Supportive", "High"]);
  const desertLabel = classify(desert, [0.20, 0.42, 0.65], ["Low", "Moderate", "High", "Very high"]);
  const heatLabel = classify(heat, [0.28, 0.56, 0.76], ["Low", "Moderate", "High", "Very high"]);
  const windLabel = classify(windSignal, [0.24, 0.50, 0.73], ["Low", "Moderate", "High", "Very high"]);
  setStatus("status-vegetation", vegetationLabel, ndvi < .3 ? "warn" : "normal");
  setStatus("status-moisture", moistureLabel, moisture < .3 ? "warn" : "normal");
  setStatus("status-desert", desertLabel, desert >= .65 ? "high" : desert >= .42 ? "warn" : "normal");
  setStatus("status-heat", heatLabel, heat >= .72 ? "high" : heat >= .5 ? "warn" : "normal");
  setStatus("status-wind", windLabel, windSignal >= .7 ? "high" : windSignal >= .48 ? "warn" : "normal");
  setStatus("status-forest", `${Number(loss).toFixed(1)} ha latest year`, loss > 50 ? "warn" : "normal");
}

function buildEvents(frame) {
  const events = [];
  const weather = frame.weather;
  const metrics = frame.simulation.metrics;
  const forecast = frame.weather_forecast?.points || [];
  const next24 = forecast.slice(0, 8);
  const rain24 = next24.reduce((sum, point) => sum + Number(point.rain_3h_mm || 0), 0);
  const maxPop = Math.max(0, ...next24.map((point) => Number(point.precipitation_probability || 0)));
  if (Number(weather.rain_1h_mm) > 0) events.push({ level: "positive", icon: "☂", title: "Rain observed", detail: `${Number(weather.rain_1h_mm).toFixed(1)} mm reported in the latest hour; the moisture forcing is responding.` });
  else if (rain24 < 1 && Number(weather.humidity_percent) < 42) events.push({ level: "warning", icon: "!", title: "Low moisture outlook", detail: `Forecast rain is ${rain24.toFixed(1)} mm over the next 24 hours and humidity is ${Number(weather.humidity_percent).toFixed(0)}%.` });
  if (metrics.weather_heat_stress >= .65) events.push({ level: "danger", icon: "♨", title: "High heat-stress forcing", detail: `${Number(weather.temperature_c).toFixed(1)}°C and current weather inputs produce ${(metrics.weather_heat_stress * 100).toFixed(0)}% model heat stress.` });
  if (Number(weather.wind_speed_mps) >= 7 && frame.satellite.stats.bare_fraction >= .20) events.push({ level: "warning", icon: "≋", title: "Wind-erosion signal", detail: `${Number(weather.wind_speed_mps).toFixed(1)} m/s wind overlaps with ${(frame.satellite.stats.bare_fraction * 100).toFixed(0)}% very-sparse NDVI pixels.` });
  if (Number(weather.cloud_cover_percent) >= 70) events.push({ level: "positive", icon: "☁", title: "Dense cloud field", detail: `${Number(weather.cloud_cover_percent).toFixed(0)}% cloud cover; auto-orbit is following the wind-driven cloud-flow target.` });
  else if (maxPop >= .6) events.push({ level: "positive", icon: "☁", title: "Rain probability rising", detail: `Provider forecast precipitation probability reaches ${(maxPop * 100).toFixed(0)}% in the next 24 hours.` });
  if (metrics.restoration_gain > .002) events.push({ level: "positive", icon: "♧", title: "Restoration gain", detail: `The cellular scenario reports ${(metrics.restoration_gain * 100).toFixed(2)} percentage points of restoration gain.` });
  if (metrics.mean_tree_health < .45) events.push({ level: "danger", icon: "♧", title: "Barrier health concern", detail: `Mean simulated tree health is ${(metrics.mean_tree_health * 100).toFixed(0)}%. Increase maintenance or moisture support in the scenario lab.` });
  if (!events.length) events.push({ level: "positive", icon: "✓", title: "No high-priority advisory", detail: "Current thresholds do not indicate an elevated platform advisory. Continue monitoring live sources." });
  return events.slice(0, 5);
}

function renderEvents(frame) {
  const events = buildEvents(frame);
  setText("event-count", String(events.length));
  const container = document.getElementById("event-list");
  container.innerHTML = events.map((event) => `<article class="event-item ${event.level}"><i>${event.icon}</i><div><strong>${event.title}</strong><small>${event.detail}</small></div></article>`).join("");
}

function chartTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function updateCharts(frame) {
  const forecast = frame.weather_forecast?.points || [];
  const forecastSlice = forecast.slice(0, 18);
  drawLineChart(document.getElementById("forecast-chart"), [
    { values: forecastSlice.map((point) => Number(point.temperature_c)), color: "#ff9d36", width: 1.9 },
    { values: forecastSlice.map((point) => Number(point.humidity_percent)), color: "#42a8ff", width: 1.7 },
  ], { labels: forecastSlice.map((point) => chartTime(point.timestamp)), decimals: 0 });
  drawBarChart(document.getElementById("rain-chart"), forecast.slice(0, 24).map((point) => ({ value: Number(point.rain_3h_mm || 0), label: new Date(point.timestamp).toLocaleDateString([], { weekday: "short" }), color: "#42a8ff" })), { decimals: 1 });
  const years = frame.gfw.years || [];
  drawBarChart(document.getElementById("forest-chart"), years.map((item) => ({ value: Number(item.area_ha || 0), label: String(item.year).slice(-2), color: "#ff704c" })), { decimals: 0 });
  const metrics = frame.simulation.metrics;
  drawDonut(document.getElementById("health-donut"), [
    { value: metrics.mean_tree_health, color: "#38d886" },
    { value: metrics.stressed_fraction, color: "#e0c34b" },
    { value: metrics.desert_fraction, color: "#f05b4d" },
  ]);
  setText("health-value", `${(metrics.mean_tree_health * 100).toFixed(0)}%`);
  const trajectory = [...history.slice(-80), {
    timestamp: frame.generated_at,
    ndvi_mean: frame.satellite.stats.mean,
    vegetated_fraction: metrics.vegetated_fraction,
    desert_fraction: metrics.desert_fraction,
  }];
  drawLineChart(document.getElementById("trajectory-chart"), [
    { values: trajectory.map((item) => Number(item.vegetated_fraction || 0) * 100), color: "#38d886", width: 1.8 },
    { values: trajectory.map((item) => Number(item.desert_fraction || 0) * 100), color: "#ff9d36", width: 1.8 },
  ], { range: [0, 100], labels: trajectory.map((item) => chartTime(item.timestamp)), decimals: 0 });
  drawLineChart(document.getElementById("ndvi-sparkline"), [
    { values: trajectory.map((item) => Number(item.ndvi_mean ?? frame.satellite.stats.mean)), color: "#35e88b", fill: "rgba(53,232,139,.24)", width: 1.8 },
  ], { range: [-.05, 1], labels: [], decimals: 1 });
  setText("trajectory-count", `${trajectory.length} samples`);
  setText("forecast-mode", frame.weather_forecast.mode.toUpperCase());
}

async function loadHistory() {
  try {
    history = await fetchJson("/api/history");
  } catch (error) {
    console.warn("History unavailable", error);
    history = [];
  }
}

async function openArea(slug) {
  if (!slug) return;
  try {
    selectedArea = await fetchJson(`/api/areas/${slug}`);
    document.getElementById("area-drawer")?.classList.add("open");
    setText("area-name", selectedArea.name);
    setText("area-scope", selectedArea.northern_focus ? "Northern Gombe focus LGA" : "Gombe State context LGA");
    setText("area-ndvi", selectedArea.satellite.mean_ndvi == null ? "No intersecting pixels" : Number(selectedArea.satellite.mean_ndvi).toFixed(2));
    setText("area-bare", selectedArea.satellite.bare_fraction == null ? "No data" : formatPercent(selectedArea.satellite.bare_fraction));
    setText("area-weather", weatherSummary(selectedArea.weather));
    setText("area-desert", selectedArea.simulation.desert_fraction == null ? "Outside northern model grid" : formatPercent(selectedArea.simulation.desert_fraction));
    setText("area-barrier", selectedArea.simulation.barrier_fraction == null ? "Outside northern model grid" : formatPercent(selectedArea.simulation.barrier_fraction, 2));
    const interpretations = document.getElementById("area-interpretations");
    interpretations.innerHTML = selectedArea.interpretation.map((item) => `<article><h4>${item.title}</h4><p>${item.body}</p></article>`).join("");
    const { longitude, latitude } = selectedArea.centroid;
    orbitTargetMode = 2;
    map.easeTo({ center: [longitude, latitude], zoom: 9.0, pitch: 56, duration: 850 });
  } catch (error) {
    showToast(`Could not load LGA evidence: ${error.message}`);
  }
}

function applyFrame(frame) {
  latestFrame = frame;
  const weather = frame.weather;
  const metrics = frame.simulation.metrics;
  const ndvi = frame.satellite.stats;
  updateConnection("online");
  updateSourceBadge("sentinel-mode", frame.satellite.mode);
  updateSourceBadge("gfw-mode", frame.gfw.mode);
  updateSourceBadge("weather-mode", weather.mode);
  setText("last-updated", `${formatDateTime(frame.generated_at)} • frame ${frame.sequence.toLocaleString()}`);
  setText("command-clock", new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));

  setText("weather-temp", `${Number(weather.temperature_c).toFixed(1)}°C`);
  setText("weather-feels", `Feels like ${Number(weather.feels_like_c).toFixed(1)}°C`);
  setText("weather-condition", weather.condition);
  setText("weather-humidity", `${Number(weather.humidity_percent).toFixed(0)}%`);
  setText("weather-wind", `${Number(weather.wind_speed_mps).toFixed(1)} m/s`);
  setText("weather-pressure", `${Number(weather.pressure_hpa).toFixed(0)} hPa`);
  setText("weather-visibility", weather.visibility_km == null ? "Not reported" : `${Number(weather.visibility_km).toFixed(1)} km`);
  setText("weather-clouds", `${Number(weather.cloud_cover_percent).toFixed(0)}%`);
  setText("weather-rain", `${Number(weather.rain_1h_mm).toFixed(1)} mm`);
  setText("wind-direction-label", weather.wind_direction_cardinal);
  setText("wind-speed-label", `${Number(weather.wind_speed_mps).toFixed(1)} m/s ${weather.wind_direction_cardinal}`);

  setText("ndvi-mean", Number(ndvi.mean).toFixed(2));
  setText("ndvi-class", ndviLabel(ndvi.mean));
  setText("ndvi-min", Number(ndvi.minimum).toFixed(2));
  setText("ndvi-max", Number(ndvi.maximum).toFixed(2));
  setText("ndvi-median", Number(ndvi.median).toFixed(2));

  setText("summary-vegetation", `${(metrics.vegetated_fraction * 100).toFixed(1)}%`);
  setText("summary-desert", `${(metrics.desert_fraction * 100).toFixed(1)}%`);
  setText("summary-barrier", `${(metrics.barrier_fraction * 100).toFixed(2)}%`);
  setText("summary-trees", treeCount.toLocaleString());
  setText("summary-loss", `${Number(frame.gfw.latest_year_loss_ha).toFixed(1)} ha`);
  setText("summary-loss-year", frame.gfw.years?.length ? `Year ${frame.gfw.years.at(-1).year}` : "Latest available year");
  setText("summary-moisture", `${(metrics.weather_moisture_forcing * 100).toFixed(0)}%`);
  setText("summary-vegetation-trend", metrics.restoration_gain >= 0 ? `▲ ${(metrics.restoration_gain * 100).toFixed(2)} restoration gain` : `▼ ${Math.abs(metrics.restoration_gain * 100).toFixed(2)} change`);
  setText("summary-desert-trend", metrics.desert_change <= 0 ? `▼ ${Math.abs(metrics.desert_change * 100).toFixed(2)} model change` : `▲ ${(metrics.desert_change * 100).toFixed(2)} model change`);

  sky.update(weather);
  skyDome.update(weather);
  panorama.update(weather);
  weatherFlow.update(weather, frame.weather_forecast);
  windFlow.update(weather);
  treeLayer.setWeather(weather);
  updateImageScene(frame);
  updateStatusPanel(frame);
  renderEvents(frame);
  updateCharts(frame);
  updateCloudTarget(weather);

  const forecastPoints = frame.weather_forecast?.points || [];
  if (forecastPoints.length) {
    setText("flow-time-start", chartTime(forecastPoints[0].timestamp));
    setText("flow-time-end", chartTime(forecastPoints[Math.min(7, forecastPoints.length - 1)].timestamp));
  }
  const flowProgress = document.getElementById("flow-progress");
  if (flowProgress) flowProgress.style.width = `${18 + (frame.sequence % 70)}%`;

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
loadHistory().then(() => latestFrame && updateCharts(latestFrame));
window.setInterval(() => loadHistory().then(() => latestFrame && updateCharts(latestFrame)), 300000);
window.setInterval(() => setText("command-clock", new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })), 1000);

function bindLayerButton(buttonId, layerId, initial = true) {
  const button = document.getElementById(buttonId);
  button?.classList.toggle("active", initial);
  button?.addEventListener("click", () => {
    const enabled = !button.classList.contains("active");
    button.classList.toggle("active", enabled);
    setLayerVisible(map, layerId, enabled);
    if (layerId === weatherLayerIds.temp && map.getLayer(layerId)) {
      map.setPaintProperty(layerId, "raster-opacity", enabled ? 0.46 : 0);
    }
  });
}

bindLayerButton("layer-clouds", weatherLayerIds.clouds, true);
bindLayerButton("layer-rain", weatherLayerIds.rain, true);
bindLayerButton("layer-temp", weatherLayerIds.temp, false);
bindLayerButton("layer-risk", "simulation-ground-layer", true);

document.getElementById("layer-day")?.addEventListener("click", (event) => {
  const enabled = !event.currentTarget.classList.contains("active");
  event.currentTarget.classList.toggle("active", enabled);
  sky.canvas.style.display = enabled ? "block" : "none";
});
document.getElementById("layer-wind")?.addEventListener("click", (event) => {
  event.currentTarget.classList.toggle("active");
  const enabled = event.currentTarget.classList.contains("active");
  sky.setLayer("wind", enabled);
  windFlow.running = enabled;
});

document.getElementById("view-state")?.addEventListener("click", () => { orbitTargetMode = 0; fitState(map, window.innerWidth < 760 ? 18 : 38); });
document.getElementById("view-north")?.addEventListener("click", () => { orbitTargetMode = 1; map.fitBounds([[10.38, 10.08], [11.86, 11.55]], { padding: window.innerWidth < 760 ? 18 : 38, duration: 900, pitch: 53, bearing: -8 }); });
document.getElementById("toggle-orbit")?.addEventListener("click", () => orbiting ? stopOrbit() : startOrbit());
document.getElementById("orbit-speed")?.addEventListener("input", (event) => { orbitSpeed = Number(event.target.value); });
document.getElementById("orbit-skip")?.addEventListener("click", () => { orbitTargetMode = (orbitTargetMode + 1) % 3; showToast(["Cloud/state flow target", "Northern Gombe target", "Selected LGA target"][orbitTargetMode]); });

document.getElementById("toggle-terrain")?.addEventListener("click", (event) => {
  terrainEnabled = !terrainEnabled;
  event.currentTarget.classList.toggle("active", terrainEnabled);
  try { map.setTerrain(terrainEnabled ? { source: "terrain-dem", exaggeration: 1.55 } : null); } catch (error) { showToast(`Terrain unavailable: ${error.message}`); }
});

document.getElementById("view-globe")?.addEventListener("click", (event) => {
  globeMode = !globeMode;
  event.currentTarget.classList.toggle("active", globeMode);
  try { map.setProjection({ type: globeMode ? "globe" : "mercator" }); } catch (error) { showToast("Globe projection is not supported by this browser build."); }
});

document.getElementById("first-person")?.addEventListener("click", (event) => {
  firstPersonMode = !firstPersonMode;
  event.currentTarget.classList.toggle("active", firstPersonMode);
  if (firstPersonMode) {
    const target = currentOrbitTarget();
    map.easeTo({ center: target, zoom: 10.2, pitch: 76, bearing: map.getBearing(), duration: 900 });
  } else {
    fitState(map, window.innerWidth < 760 ? 18 : 38);
  }
});

document.getElementById("split-view")?.addEventListener("click", (event) => {
  const enabled = !shell.classList.contains("split-view");
  shell.classList.toggle("split-view", enabled);
  event.currentTarget.classList.toggle("active", enabled);
});

document.getElementById("reset-view")?.addEventListener("click", () => {
  firstPersonMode = false;
  orbitTargetMode = 0;
  document.getElementById("first-person")?.classList.remove("active");
  fitState(map, window.innerWidth < 760 ? 18 : 38);
  if (!orbiting) startOrbit();
});

document.getElementById("toggle-run")?.addEventListener("click", async () => {
  if (!latestFrame) return;
  const running = !latestFrame.simulation.running;
  await fetchJson("/api/simulation/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ running }) });
  setText("run-icon", running ? "Ⅱ" : "▶");
});

let speedTimer = 0;
document.getElementById("sim-speed")?.addEventListener("input", (event) => {
  const speed = Number(event.target.value);
  setText("sim-speed-output", `${speed.toFixed(2)}×`);
  window.clearTimeout(speedTimer);
  speedTimer = window.setTimeout(() => fetchJson("/api/simulation/speed", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ speed }) }).catch((error) => showToast(error.message)), 180);
});

document.getElementById("flow-pause")?.addEventListener("click", (event) => {
  flowRunning = !flowRunning;
  weatherFlow.setRunning(flowRunning);
  event.currentTarget.textContent = flowRunning ? "Ⅱ" : "▶";
});

document.getElementById("economy-toggle")?.addEventListener("click", (event) => {
  economyMode = !economyMode;
  document.body.classList.toggle("economy-mode", economyMode);
  event.currentTarget.classList.toggle("active", economyMode);
  showToast(economyMode ? "Economy rendering enabled" : "Full rendering enabled");
});
document.body.classList.toggle("economy-mode", economyMode);
document.getElementById("economy-toggle")?.classList.toggle("active", economyMode);

document.getElementById("close-area")?.addEventListener("click", () => document.getElementById("area-drawer")?.classList.remove("open"));
bindFullscreen("fullscreen-map", "twin-map-shell", map);
window.addEventListener("resize", () => map.resize(), { passive: true });

async function refreshV4Intelligence() {
  try {
    const summary = await fetchJson("/api/intelligence/summary");
    setText("v4-trend", String(summary.temporal?.trend || "—").replaceAll("_", " "));
    setText("v4-drought", Number.isFinite(Number(summary.drought?.score)) ? `${Number(summary.drought.score).toFixed(0)}/100` : "—");
    setText("v4-radar", Number.isFinite(Number(summary.radar?.mean_rvi)) ? Number(summary.radar.mean_rvi).toFixed(2) : "—");
    setText("v4-fires", `${summary.fire?.count ?? 0} detections`);
    setText("v4-carbon", Number.isFinite(Number(summary.carbon?.carbon_t)) ? `${Math.round(Number(summary.carbon.carbon_t)).toLocaleString()} t C` : "—");
    setText("v4-risk", Number.isFinite(Number(summary.risks?.combined)) ? `${(Number(summary.risks.combined) * 100).toFixed(0)}%` : "—");
  } catch (error) {
    console.warn("Version 4 intelligence summary unavailable", error);
  }
}
refreshV4Intelligence();
window.setInterval(refreshV4Intelligence, 60000);
