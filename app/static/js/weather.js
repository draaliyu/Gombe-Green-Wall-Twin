import {
  LiveSocket,
  bindFullscreen,
  createMap,
  fetchJson,
  fitNorth,
  fitState,
  formatClock,
  formatDateTime,
  setText,
  setWidth,
  showToast,
  updateConnection,
} from "./common.js";
import { LiveSky } from "./sky.js";

const map = createMap("weather-map", { pitch: 38, bearing: -8, zoom: 7.65, exaggeration: 1.2 });
const sky = new LiveSky("weather-stage");
let latestFrame = null;

map.on("administrativeready", () => fitState(map, window.innerWidth < 760 ? 18 : 40));

function renderInterpretation(frame) {
  const weather = frame.weather;
  const metrics = frame.simulation.metrics;
  const moistureText = metrics.weather_moisture_forcing >= 0.62 ? "strong" : metrics.weather_moisture_forcing >= 0.34 ? "moderate" : "limited";
  const heatText = metrics.weather_heat_stress >= 0.62 ? "high" : metrics.weather_heat_stress >= 0.34 ? "moderate" : "low";
  const cards = [
    {
      title: "Cloud and rain signal",
      body: `Cloud cover is ${Number(weather.cloud_cover_percent).toFixed(0)}% and reported rain is ${Number(weather.rain_1h_mm).toFixed(1)} mm in the latest hour. The scene therefore uses ${weather.rain_1h_mm > 0 ? "active rain streaks and denser clouds" : "cloud movement without a strong rainfall layer"}.`,
    },
    {
      title: "Wind movement",
      body: `Wind is reported at ${Number(weather.wind_speed_mps).toFixed(1)} m/s from ${weather.wind_direction_cardinal}. Animated streamlines and procedural tree sway use this speed and bearing. This represents the observation at the weather coordinate, not a complete state-wide wind field.`,
    },
    {
      title: "Restoration forcing",
      body: `The scenario currently receives ${moistureText} atmospheric moisture support and ${heatText} heat stress. Rain and humidity increase the moisture signal; high temperature and stronger wind increase drying stress within bounded limits.`,
    },
    {
      title: "Day and night scene",
      body: `${weather.is_daylight ? "The timestamp falls between the reported sunrise and sunset, so the scene displays the sun." : "The timestamp is outside the reported daylight period, so the scene displays the moon and stars."} Cloud cover reduces celestial visibility.`,
    },
  ];
  document.getElementById("weather-interpretation").innerHTML = cards.map((card) => `<article><h4>${card.title}</h4><p>${card.body}</p></article>`).join("");
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
document.getElementById("weather-refresh")?.addEventListener("click", async () => {
  try {
    const weather = await fetchJson("/api/weather/refresh", { method: "POST" });
    sky.update(weather);
    showToast(`Weather refreshed: ${weather.condition}`);
  } catch (error) { showToast(`Weather refresh failed: ${error.message}`); }
});
bindFullscreen("weather-full", "weather-stage", map);
window.addEventListener("resize", () => map.resize(), { passive: true });
