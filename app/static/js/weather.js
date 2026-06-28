import {
  LiveSocket,
  bindFullscreen,
  createMap,
  fetchJson,
  fitNorth,
  fitState,
  formatClock,
  formatDateTime,
  setLayerVisible,
  setText,
  setWidth,
  showToast,
  updateConnection,
} from "./common.js";
import { LiveSky } from "./sky.js";
import { drawLineChart } from "./dashboard.js";

const map = createMap("weather-map", { pitch: 45, bearing: -8, zoom: 7.65, exaggeration: 1.35 });
const sky = new LiveSky("weather-stage");
let latestFrame = null;
let orbiting = true;
let orbitHandle = 0;
let lastOrbit = 0;
let orbitSpeed = .55;

function addProviderLayer(id, source, layer, opacity) {
  if (!map.getSource(source)) map.addSource(source, { type: "raster", tiles: [`/api/weather/tiles/${layer}/{z}/{x}/{y}.png`], tileSize: 256, maxzoom: 19 });
  if (!map.getLayer(id)) map.addLayer({ id, type: "raster", source, paint: { "raster-opacity": opacity, "raster-fade-duration": 350 } }, map.getLayer("lga-outline") ? "lga-outline" : undefined);
}

map.on("administrativeready", () => {
  addProviderLayer("weather-provider-cloud-layer", "weather-provider-cloud-source", "clouds_new", .52);
  addProviderLayer("weather-provider-rain-layer", "weather-provider-rain-source", "precipitation_new", .62);
  addProviderLayer("weather-provider-temp-layer", "weather-provider-temp-source", "temp_new", 0);
  fitState(map, window.innerWidth < 760 ? 18 : 40);
  startOrbit();
});

function cloudTarget(weather, time) {
  const direction = (Number(weather.wind_direction_deg) || 0) * Math.PI / 180;
  const cover = Math.max(0, Math.min(100, Number(weather.cloud_cover_percent) || 0)) / 100;
  const phase = time / 1000 * (.006 + Number(weather.wind_speed_mps || 0) * .0007);
  return [11.18 + Math.sin(direction) * Math.sin(phase) * (.03 + cover * .10), 10.72 + Math.cos(direction) * Math.cos(phase * .8) * (.02 + cover * .06)];
}

function startOrbit() {
  orbiting = true;
  document.getElementById("weather-orbit")?.classList.add("active");
  cancelAnimationFrame(orbitHandle);
  const loop = (timestamp) => {
    orbitHandle = requestAnimationFrame(loop);
    if (!orbiting || document.hidden || !latestFrame || !map.loaded()) return;
    if (timestamp - lastOrbit < (window.innerWidth < 760 ? 260 : 130)) return;
    lastOrbit = timestamp;
    const target = Number(latestFrame.weather.cloud_cover_percent) >= 35 ? cloudTarget(latestFrame.weather, timestamp) : [11.18, 10.55];
    const current = map.getCenter();
    map.jumpTo({ center: [current.lng + (target[0] - current.lng) * .05, current.lat + (target[1] - current.lat) * .05], bearing: (map.getBearing() + orbitSpeed * .3) % 360, pitch: 45 });
  };
  orbitHandle = requestAnimationFrame(loop);
}

function renderInterpretation(frame) {
  const weather = frame.weather;
  const metrics = frame.simulation.metrics;
  const forecast = frame.weather_forecast?.points || [];
  const next24 = forecast.slice(0, 8);
  const rain24 = next24.reduce((sum, point) => sum + Number(point.rain_3h_mm || 0), 0);
  const maxPop = Math.max(0, ...next24.map((point) => Number(point.precipitation_probability || 0)));
  const moistureText = metrics.weather_moisture_forcing >= 0.62 ? "strong" : metrics.weather_moisture_forcing >= 0.34 ? "moderate" : "limited";
  const heatText = metrics.weather_heat_stress >= 0.62 ? "high" : metrics.weather_heat_stress >= 0.34 ? "moderate" : "low";
  const cards = [
    { title: "Current cloud and precipitation", body: `Cloud cover is ${Number(weather.cloud_cover_percent).toFixed(0)}% and reported rain is ${Number(weather.rain_1h_mm).toFixed(1)} mm in the latest hour. Provider cloud and precipitation map layers are shown when the OpenWeather key is configured.` },
    { title: "Wind-following camera", body: `Wind is ${Number(weather.wind_speed_mps).toFixed(1)} m/s from ${weather.wind_direction_cardinal}. Auto-orbit follows a wind-driven cloud-flow target when cloud cover is at least 35%. The target is a visual tracking construct, not a detected individual cloud object.` },
    { title: "Next 24 hours", body: `The configured forecast provides ${rain24.toFixed(1)} mm total three-hour rainfall increments over the next 24 hours, with maximum precipitation probability ${(maxPop * 100).toFixed(0)}%.` },
    { title: "Land-model forcing", body: `The scenario receives ${moistureText} atmospheric moisture support and ${heatText} heat stress. These bounded inputs use weather observations and do not replace measured soil moisture or evapotranspiration.` },
    { title: "Day and night scene", body: `${weather.is_daylight ? "The current observation time is between provider sunrise and sunset, so the sun is shown." : "The current observation time is outside provider daylight, so the moon and stars are shown."} Cloud cover reduces celestial visibility.` },
  ];
  document.getElementById("weather-interpretation").innerHTML = cards.map((card) => `<article><h4>${card.title}</h4><p>${card.body}</p></article>`).join("");
}

function drawForecast(frame) {
  const points = (frame.weather_forecast?.points || []).slice(0, 24);
  drawLineChart(document.getElementById("weather-forecast-chart"), [
    { values: points.map((point) => Number(point.temperature_c)), color: "#ff9d36", width: 2 },
    { values: points.map((point) => Number(point.humidity_percent)), color: "#42a8ff", width: 1.8 },
    { values: points.map((point) => Number(point.rain_3h_mm) * 10), color: "#36e3d3", width: 1.4 },
  ], { labels: points.map((point) => new Date(point.timestamp).toLocaleTimeString([], { hour: "2-digit" })), decimals: 0 });
}

function applyFrame(frame) {
  latestFrame = frame;
  const weather = frame.weather;
  const metrics = frame.simulation.metrics;
  sky.update(weather);
  setText("weather-last-updated", `Live frame ${frame.sequence.toLocaleString()} • ${formatDateTime(frame.generated_at)}`);
  setText("weather-source-label", `${weather.mode.toUpperCase()} • ${weather.location_name}`);
  setText("weather-main", `${weather.condition} • ${Number(weather.temperature_c).toFixed(1)}°C`);
  setText("weather-explanation", `${weather.note} Wind is from ${weather.wind_direction_cardinal}; cloud cover is ${Number(weather.cloud_cover_percent).toFixed(0)}%.`);
  setText("weather-page-temp", `${Number(weather.temperature_c).toFixed(1)}°C`);
  setText("weather-page-feels", `${Number(weather.feels_like_c).toFixed(1)}°C`);
  setText("weather-page-humidity", `${Number(weather.humidity_percent).toFixed(0)}%`);
  setText("weather-page-wind", `${Number(weather.wind_speed_mps).toFixed(1)} m/s ${weather.wind_direction_cardinal}`);
  setText("weather-page-clouds", `${Number(weather.cloud_cover_percent).toFixed(0)}%`);
  setText("weather-page-rain", `${Number(weather.rain_1h_mm).toFixed(1)} mm`);
  setText("weather-sunrise", formatClock(weather.sunrise));
  setText("weather-sunset", formatClock(weather.sunset));
  setText("weather-daylight", weather.is_daylight ? "Day" : "Night");
  setText("weather-visibility", weather.visibility_km == null ? "Not reported" : `${Number(weather.visibility_km).toFixed(1)} km`);
  setText("weather-force-moisture-label", `${(metrics.weather_moisture_forcing * 100).toFixed(0)}%`);
  setText("weather-force-heat-label", `${(metrics.weather_heat_stress * 100).toFixed(0)}%`);
  setWidth("weather-force-moisture", metrics.weather_moisture_forcing * 100);
  setWidth("weather-force-heat", metrics.weather_heat_stress * 100);
  renderInterpretation(frame);
  drawForecast(frame);
}

new LiveSocket(applyFrame, updateConnection);

document.getElementById("weather-state")?.addEventListener("click", () => fitState(map, window.innerWidth < 760 ? 18 : 40));
document.getElementById("weather-north")?.addEventListener("click", () => fitNorth(map, window.innerWidth < 760 ? 18 : 40));
[["weather-celestial", "celestial"], ["weather-clouds", "clouds"], ["weather-wind", "wind"], ["weather-rain", "rain"]].forEach(([id, layer]) => {
  document.getElementById(id)?.addEventListener("click", (event) => {
    event.currentTarget.classList.toggle("active");
    sky.setLayer(layer, event.currentTarget.classList.contains("active"));
  });
});
[["weather-provider-clouds", "weather-provider-cloud-layer"], ["weather-provider-rain", "weather-provider-rain-layer"], ["weather-provider-temp", "weather-provider-temp-layer"]].forEach(([id, layer]) => {
  document.getElementById(id)?.addEventListener("click", (event) => {
    event.currentTarget.classList.toggle("active");
    setLayerVisible(map, layer, event.currentTarget.classList.contains("active"));
    if (layer === "weather-provider-temp-layer") map.setPaintProperty(layer, "raster-opacity", event.currentTarget.classList.contains("active") ? .46 : 0);
  });
});
document.getElementById("weather-orbit")?.addEventListener("click", (event) => {
  orbiting = !orbiting;
  event.currentTarget.classList.toggle("active", orbiting);
  if (orbiting) startOrbit(); else cancelAnimationFrame(orbitHandle);
});
document.getElementById("weather-refresh")?.addEventListener("click", async () => {
  try {
    const weather = await fetchJson("/api/weather/refresh", { method: "POST" });
    sky.update(weather);
    showToast(`Weather refreshed: ${weather.condition}`);
  } catch (error) { showToast(`Weather refresh failed: ${error.message}`); }
});
bindFullscreen("weather-full", "weather-stage", map);
window.addEventListener("resize", () => map.resize(), { passive: true });
