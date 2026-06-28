import {
  AOI,
  LiveSocket,
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

const map = createMap("planner-map", { pitch: 34, bearing: 0, zoom: 7.9, exaggeration: 1.15 });
let points = [];
let drawing = true;
let lastSimulationVersion = -1;
let administrativeReady = false;

const emptyLine = { type: "FeatureCollection", features: [] };
function lineGeoJSON() {
  const features = points.map((coordinates, index) => ({ type: "Feature", properties: { index }, geometry: { type: "Point", coordinates } }));
  if (points.length >= 2) features.unshift({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: points } });
  return { type: "FeatureCollection", features };
}

function clearDraft(message = "Draft state: empty and unsaved.") {
  points = [];
  refreshCandidate();
  setText("draft-state-note", message);
}

map.on("administrativeready", () => {
  map.addSource("planner-ndvi", { type: "image", url: `/api/ndvi/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
  map.addLayer({ id: "planner-ndvi-layer", type: "raster", source: "planner-ndvi", paint: { "raster-opacity": 0.72 } }, "northern-focus-fill");
  map.addSource("planner-simulation", { type: "image", url: `/api/simulation/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
  map.addLayer({ id: "planner-simulation-layer", type: "raster", source: "planner-simulation", paint: { "raster-opacity": 0.38 } }, "northern-focus-fill");
  map.addSource("candidate-corridor", { type: "geojson", data: emptyLine });
  map.addLayer({ id: "candidate-corridor-glow", type: "line", source: "candidate-corridor", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#69f0aa", "line-width": 12, "line-opacity": 0.27, "line-blur": 5 } });
  map.addLayer({ id: "candidate-corridor-line", type: "line", source: "candidate-corridor", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#d6ff74", "line-width": 3.5, "line-dasharray": [2, 1] } });
  map.addLayer({ id: "candidate-corridor-points", type: "circle", source: "candidate-corridor", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 6, "circle-color": "#69f0aa", "circle-stroke-color": "#061011", "circle-stroke-width": 2 } });
  fitNorth(map, window.innerWidth < 760 ? 22 : 46);
  clearDraft();
});

map.on("administrativeready", () => { administrativeReady = true; });

map.on("click", (event) => {
  if (!drawing) return;
  if (!administrativeReady) { showToast("Northern LGA boundaries are still loading."); return; }
  const hits = map.queryRenderedFeatures(event.point, { layers: ["northern-focus-fill"] });
  if (!hits.length) {
    showToast("Place corridor points inside a highlighted northern-focus LGA.");
    return;
  }
  const { lng, lat } = event.lngLat;
  points.push([Number(lng.toFixed(6)), Number(lat.toFixed(6))]);
  refreshCandidate();
  setText("draft-state-note", `Draft state: ${points.length} unsaved point${points.length === 1 ? "" : "s"}. Refreshing the page will clear them.`);
});

function haversine(a, b) {
  const radius = 6371;
  const toRad = (value) => value * Math.PI / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLon = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const value = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(value));
}

function refreshCandidate() {
  map.getSource("candidate-corridor")?.setData(lineGeoJSON());
  setText("planner-point-count", points.length.toString());
  let length = 0;
  for (let index = 1; index < points.length; index += 1) length += haversine(points[index - 1], points[index]);
  setText("planner-length", `${length.toFixed(1)} km`);
}

function applyFrame(frame) {
  setText("planner-last-updated", `Live frame ${frame.sequence.toLocaleString()} • ${formatDateTime(frame.generated_at)}`);
  const simulation = frame.simulation;
  const metrics = simulation.metrics;
  setText("planner-health", formatPercent(metrics.mean_tree_health));
  setText("planner-desert", formatPercent(metrics.desert_fraction));
  setText("planner-vegetated", formatPercent(metrics.vegetated_fraction));
  setText("planner-barrier", formatPercent(metrics.barrier_fraction, 2));
  setText("planner-gain", `${metrics.restoration_gain >= 0 ? "+" : ""}${formatPercent(metrics.restoration_gain, 2)}`);
  if (simulation.texture_version !== lastSimulationVersion && map.loaded()) {
    map.getSource("planner-simulation")?.updateImage?.({ url: `/api/simulation/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
    lastSimulationVersion = simulation.texture_version;
  }
}
new LiveSocket(applyFrame, updateConnection);

document.getElementById("planner-draw")?.addEventListener("click", (event) => {
  drawing = !drawing;
  event.currentTarget.classList.toggle("active", drawing);
  map.getCanvas().style.cursor = drawing ? "crosshair" : "grab";
});
document.getElementById("planner-undo")?.addEventListener("click", () => { points.pop(); refreshCandidate(); setText("draft-state-note", points.length ? `Draft state: ${points.length} unsaved point${points.length === 1 ? "" : "s"}.` : "Draft state: empty and unsaved."); });
document.getElementById("planner-clear")?.addEventListener("click", () => clearDraft());
document.getElementById("planner-state")?.addEventListener("click", () => fitState(map, window.innerWidth < 760 ? 20 : 42));
document.getElementById("planner-north")?.addEventListener("click", () => fitNorth(map, window.innerWidth < 760 ? 20 : 42));
bindFullscreen("planner-fullscreen", "planner-map-shell", map);

document.getElementById("corridor-width")?.addEventListener("input", (event) => setText("corridor-width-value", `${event.target.value} cells`));
document.getElementById("submit-corridor")?.addEventListener("click", async () => {
  if (points.length < 2) { showToast("Add at least two draft points first."); return; }
  try {
    const result = await fetchJson("/api/planner/corridor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coordinates: points, width_cells: Number(document.getElementById("corridor-width").value) }),
    });
    setText("planner-cells", result.cells_planted.toLocaleString());
    setText("planner-message", result.note);
    clearDraft("Draft cleared after commit. Draw a new corridor to test another intervention.");
    showToast(`${result.cells_planted.toLocaleString()} model cells committed; the draft was cleared.`);
  } catch (error) { showToast(`Could not commit corridor: ${error.message}`); }
});
document.getElementById("remove-all-corridors")?.addEventListener("click", async () => {
  try {
    const result = await fetchJson("/api/planner/corridors", { method: "DELETE" });
    setText("planner-cells", "0");
    setText("planner-message", result.note);
    clearDraft();
    showToast("All committed barrier cells were removed.");
  } catch (error) { showToast(`Could not clear barriers: ${error.message}`); }
});
document.getElementById("reset-whole-scenario")?.addEventListener("click", async () => {
  try {
    await fetchJson("/api/simulation/reset", { method: "POST" });
    setText("planner-cells", "0");
    setText("planner-message", "The vegetation, desert and barrier scenario was reinitialised from the current NDVI grid.");
    clearDraft();
    showToast("The full simulation scenario was reset.");
  } catch (error) { showToast(`Could not reset scenario: ${error.message}`); }
});
window.addEventListener("pageshow", () => clearDraft());
window.addEventListener("resize", () => map.resize(), { passive: true });
