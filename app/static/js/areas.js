import {
  LiveSocket,
  bindAreaInteraction,
  bindFullscreen,
  createMap,
  fetchJson,
  fitNorth,
  fitState,
  formatDateTime,
  formatPercent,
  setText,
  showToast,
  updateConnection,
} from "./common.js";

const map = createMap("areas-map", { zoom: 7.6, pitch: 28, bearing: 0, exaggeration: 1.1 });
let areas = [];
let activeSlug = null;

map.on("administrativeready", () => {
  bindAreaInteraction(map, (feature) => selectArea(feature.properties?.slug));
  fitState(map, window.innerWidth < 760 ? 20 : 42);
});

function renderList() {
  const container = document.getElementById("area-list");
  if (!container) return;
  container.innerHTML = "";
  areas.forEach((area) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `area-button ${activeSlug === area.slug ? "active" : ""}`;
    button.innerHTML = `<strong>${area.name}</strong><span>${area.northern_focus ? "Northern focus" : "State context"}</span>`;
    button.addEventListener("click", () => selectArea(area.slug));
    container.appendChild(button);
  });
  setText("areas-count", `${areas.length} LGAs`);
}

async function selectArea(slug) {
  if (!slug) return;
  activeSlug = slug;
  renderList();
  try {
    const profile = await fetchJson(`/api/areas/${slug}`);
    setText("selected-area-name", profile.name);
    setText("selected-area-scope", profile.northern_focus ? "Northern focus" : "State context");
    setText("selected-ndvi", profile.satellite.mean_ndvi == null ? "No intersecting pixels" : Number(profile.satellite.mean_ndvi).toFixed(2));
    setText("selected-ndvi-mode", `${profile.satellite.mode.toUpperCase()} satellite aggregation`);
    setText("selected-bare", profile.satellite.bare_fraction == null ? "No data" : formatPercent(profile.satellite.bare_fraction));
    setText("selected-temp", `${Number(profile.weather.temperature_c).toFixed(1)}°C`);
    setText("selected-condition", `${profile.weather.condition} • ${profile.weather.mode}`);
    setText("selected-wind", `${Number(profile.weather.wind_speed_mps).toFixed(1)} m/s ${profile.weather.wind_direction_cardinal}`);
    setText("selected-desert", profile.simulation.desert_fraction == null ? "Outside model grid" : formatPercent(profile.simulation.desert_fraction));
    setText("selected-barrier", profile.simulation.barrier_fraction == null ? "Outside model grid" : formatPercent(profile.simulation.barrier_fraction, 2));
    const interpretation = document.getElementById("selected-interpretation");
    if (interpretation) interpretation.innerHTML = profile.interpretation.map((item) => `<article><h4>${item.title}</h4><p>${item.body}</p></article>`).join("");
    map.easeTo({ center: [profile.centroid.longitude, profile.centroid.latitude], zoom: profile.northern_focus ? 9 : 8.5, pitch: 34, duration: 850 });
  } catch (error) {
    showToast(`Could not load area evidence: ${error.message}`);
  }
}

Promise.all([fetchJson("/api/areas"), fetchJson("/api/snapshot")]).then(([items]) => {
  areas = items;
  renderList();
  const initial = areas.find((area) => area.name === "Dukku") || areas[0];
  if (initial) selectArea(initial.slug);
}).catch((error) => showToast(`Could not load LGAs: ${error.message}`));

new LiveSocket((frame) => setText("areas-last-updated", `Live frame ${frame.sequence.toLocaleString()} • ${formatDateTime(frame.generated_at)}`), updateConnection);
document.getElementById("areas-state")?.addEventListener("click", () => fitState(map, window.innerWidth < 760 ? 20 : 42));
document.getElementById("areas-north")?.addEventListener("click", () => fitNorth(map, window.innerWidth < 760 ? 20 : 42));
bindFullscreen("areas-full", "areas-map-shell", map);
window.addEventListener("resize", () => map.resize(), { passive: true });
