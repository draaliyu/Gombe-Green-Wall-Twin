import {
  AOI,
  LiveSocket,
  bindFullscreen,
  createMap,
  fitAOI,
  formatDateTime,
  formatNumber,
  formatPercent,
  setText,
  setWidth,
  updateConnection,
  updateSourceBadge,
  fetchJson,
  showToast,
} from "./common.js";
import { TreeLayer } from "./trees3d.js";

const map = createMap("twin-map", { pitch: 56, bearing: -12, zoom: 8.2, exaggeration: 1.55 });
const treeLayer = new TreeLayer("three-trees", [11.2, 10.83]);
let latestFrame = null;
let orbiting = false;
let orbitHandle = 0;
let showingRisk = false;
let treeVisible = true;
let lastNDVIVersion = -1;
let lastSimulationVersion = -1;
let lastTreeVersion = -1;

map.on("load", () => {
  map.addSource("ndvi-ground", {
    type: "image",
    url: `/api/ndvi/texture.png?t=${Date.now()}`,
    coordinates: AOI.coordinates,
  });
  map.addLayer({
    id: "ndvi-ground-layer",
    type: "raster",
    source: "ndvi-ground",
    paint: { "raster-opacity": 0.74, "raster-fade-duration": 800 },
  });
  map.addSource("simulation-ground", {
    type: "image",
    url: `/api/simulation/texture.png?t=${Date.now()}`,
    coordinates: AOI.coordinates,
  });
  map.addLayer({
    id: "simulation-ground-layer",
    type: "raster",
    source: "simulation-ground",
    paint: { "raster-opacity": 0.10, "raster-fade-duration": 600 },
  });
  map.addLayer(treeLayer);
  fitAOI(map, window.innerWidth < 760 ? 24 : 54);
  refreshTrees();
});

async function refreshTrees() {
  try {
    const payload = await fetchJson("/api/simulation/trees");
    treeLayer.setTrees(payload.features, payload.version);
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
  (items || []).slice(0, 5).forEach((item) => {
    const article = document.createElement("article");
    article.className = `insight ${item.kind}`;
    const evidence = Array.isArray(item.evidence) && item.evidence.length
      ? `<p style="margin-top:6px;color:#718d81">${item.evidence.slice(0, 2).join(" • ")}</p>`
      : "";
    article.innerHTML = `<span class="kind">${item.kind}</span><h4>${item.title}</h4><p>${item.body}</p>${evidence}`;
    container.appendChild(article);
  });
}

function applyFrame(frame) {
  latestFrame = frame;
  const sat = frame.satellite;
  const sim = frame.simulation;
  const stats = sat.stats;
  const metrics = sim.metrics;
  setText("header-frame", String(frame.sequence).padStart(6, "0"));
  setText("last-updated", `Last updated ${formatDateTime(frame.generated_at)}`);
  updateSourceBadge("sentinel-mode", sat.mode);
  updateSourceBadge("gfw-mode", frame.gfw.mode);

  setText("map-ndvi", formatNumber(stats.mean, 2));
  setText("map-desert", formatPercent(metrics.desert_fraction));
  setText("map-tree-health", formatPercent(metrics.mean_tree_health));
  setText("map-scene-subtitle", `${sat.mode.toUpperCase()} Sentinel layer • simulation tick ${metrics.tick} • ${treeLayer.trees.length} tree instances`);

  setText("ndvi-mean", formatNumber(stats.mean, 3));
  setText("ndvi-valid", formatPercent(stats.valid_fraction));
  setText("ndvi-bare", formatPercent(stats.bare_fraction));
  setText("ndvi-dense", formatPercent(stats.dense_fraction));
  setText("ndvi-window", `${new Date(sat.observation_window_start).toLocaleDateString()} – ${new Date(sat.observation_window_end).toLocaleDateString()}`);
  const greenScore = Math.max(0, Math.min(100, ((stats.mean + 0.1) / 0.8) * 100));
  setText("green-meter-label", `${greenScore.toFixed(0)} / 100`);
  setWidth("green-meter", greenScore);

  setText("sim-vegetated", formatPercent(metrics.vegetated_fraction));
  setText("sim-desert", formatPercent(metrics.desert_fraction));
  setText("sim-barrier", formatPercent(metrics.barrier_fraction, 2));
  setText("sim-front", metrics.desert_front_cells.toLocaleString());
  setText("desert-meter-label", formatPercent(metrics.desert_fraction));
  setWidth("desert-meter", metrics.desert_fraction * 100);
  renderInsights(frame.insights);

  if (sat.texture_version !== lastNDVIVersion && map.loaded()) {
    updateImageSource("ndvi-ground", "/api/ndvi/texture.png");
    lastNDVIVersion = sat.texture_version;
  }
  if (sim.texture_version !== lastSimulationVersion && map.loaded()) {
    updateImageSource("simulation-ground", "/api/simulation/texture.png");
    lastSimulationVersion = sim.texture_version;
  }
  if (sim.tree_version !== lastTreeVersion) refreshTrees();
}

new LiveSocket(applyFrame, updateConnection);

function setRiskView(risk) {
  showingRisk = risk;
  document.getElementById("view-ndvi")?.classList.toggle("active", !risk);
  document.getElementById("view-risk")?.classList.toggle("active", risk);
  if (map.getLayer("ndvi-ground-layer")) map.setPaintProperty("ndvi-ground-layer", "raster-opacity", risk ? 0.22 : 0.74);
  if (map.getLayer("simulation-ground-layer")) map.setPaintProperty("simulation-ground-layer", "raster-opacity", risk ? 0.82 : 0.10);
  setText("map-scene-title", risk ? "Cellular-automata desert pressure" : "NDVI ground texture + living tree barrier");
}

document.getElementById("view-ndvi")?.addEventListener("click", () => setRiskView(false));
document.getElementById("view-risk")?.addEventListener("click", () => setRiskView(true));
document.getElementById("toggle-trees")?.addEventListener("click", (event) => {
  treeVisible = !treeVisible;
  treeLayer.setVisible(treeVisible);
  event.currentTarget.classList.toggle("active", treeVisible);
});
document.getElementById("toggle-run")?.addEventListener("click", async () => {
  if (!latestFrame) return;
  const running = !latestFrame.simulation.running;
  try {
    await fetchJson("/api/simulation/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ running }),
    });
    setText("run-icon", running ? "Ⅱ" : "▶");
    setText("run-label", running ? "Pause" : "Run");
  } catch (error) {
    showToast(`Could not change simulation state: ${error.message}`);
  }
});
document.getElementById("reset-view")?.addEventListener("click", () => fitAOI(map, window.innerWidth < 760 ? 24 : 54));
bindFullscreen("fullscreen-map", "twin-map-shell", map);

document.getElementById("toggle-orbit")?.addEventListener("click", (event) => {
  orbiting = !orbiting;
  event.currentTarget.classList.toggle("active", orbiting);
  cancelAnimationFrame(orbitHandle);
  if (!orbiting) return;
  const orbit = () => {
    if (!orbiting || document.hidden) return;
    map.rotateTo(map.getBearing() + 0.035, { duration: 0 });
    orbitHandle = requestAnimationFrame(orbit);
  };
  orbit();
});

window.addEventListener("resize", () => map.resize(), { passive: true });
