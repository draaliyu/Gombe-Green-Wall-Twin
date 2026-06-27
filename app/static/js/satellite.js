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
} from "./common.js";

const map = createMap("satellite-map", { pitch: 42, bearing: -8, zoom: 8.2, exaggeration: 1.35 });
let lastTextureVersion = -1;
let classified = false;
let latestGrid = null;

map.on("load", () => {
  map.addSource("sat-ndvi", { type: "image", url: `/api/ndvi/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
  map.addLayer({ id: "sat-ndvi-layer", type: "raster", source: "sat-ndvi", paint: { "raster-opacity": 0.82, "raster-contrast": 0.1, "raster-saturation": 0.1 } });
  fitAOI(map, window.innerWidth < 760 ? 24 : 48);
});

function drawHistogram(grid) {
  const canvas = document.getElementById("ndvi-histogram");
  if (!canvas || !grid) return;
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(300, Math.floor(rect.width * dpr));
  canvas.height = Math.max(200, Math.floor(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const width = canvas.width / dpr;
  const height = canvas.height / dpr;
  ctx.clearRect(0, 0, width, height);
  const values = grid.values.flat().filter((value) => Number.isFinite(value));
  const bins = new Array(24).fill(0);
  values.forEach((value) => {
    const index = Math.max(0, Math.min(bins.length - 1, Math.floor(((value + 0.2) / 1.0) * bins.length)));
    bins[index] += 1;
  });
  const max = Math.max(...bins, 1);
  const left = 34, right = 12, top = 15, bottom = 30;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  ctx.strokeStyle = "rgba(158,185,173,.25)";
  ctx.beginPath(); ctx.moveTo(left, top); ctx.lineTo(left, top + plotH); ctx.lineTo(left + plotW, top + plotH); ctx.stroke();
  bins.forEach((count, index) => {
    const x = left + index / bins.length * plotW;
    const barW = plotW / bins.length - 2;
    const barH = count / max * plotH;
    const ndvi = -0.2 + index / bins.length;
    const hue = Math.max(28, Math.min(145, 40 + (ndvi + 0.1) * 120));
    ctx.fillStyle = `hsl(${hue} 65% 48%)`;
    ctx.fillRect(x + 1, top + plotH - barH, barW, barH);
  });
  ctx.fillStyle = "#9eb9ad";
  ctx.font = "10px system-ui";
  ctx.fillText("-0.2", left - 8, height - 8);
  ctx.fillText("0.3", left + plotW * 0.5 - 8, height - 8);
  ctx.fillText("0.8", left + plotW - 12, height - 8);
}

async function loadGrid() {
  latestGrid = await fetchJson("/api/ndvi/grid");
  drawHistogram(latestGrid);
}
loadGrid().catch(console.error);

function applyFrame(frame) {
  const sat = frame.satellite;
  const stats = sat.stats;
  setText("sat-last-updated", `Last updated ${formatDateTime(frame.generated_at)}`);
  setText("sat-map-title", `${sat.mode.toUpperCase()} NDVI • mean ${formatNumber(stats.mean, 3)}`);
  setText("sat-map-subtitle", `${formatPercent(stats.valid_fraction)} valid coverage • cloud limit ${sat.cloud_limit_percent}%`);
  setText("sat-mean", formatNumber(stats.mean, 3));
  setText("sat-median", formatNumber(stats.median, 3));
  setText("sat-p10", formatNumber(stats.p10, 3));
  setText("sat-p90", formatNumber(stats.p90, 3));
  setText("sat-valid-label", formatPercent(stats.valid_fraction));
  setWidth("sat-valid-meter", stats.valid_fraction * 100);
  setText("sat-note", sat.note);
  updateSourceBadge("sat-source-mode", sat.mode);
  if (sat.texture_version !== lastTextureVersion && map.loaded()) {
    map.getSource("sat-ndvi")?.updateImage?.({ url: `/api/ndvi/texture.png?t=${Date.now()}`, coordinates: AOI.coordinates });
    lastTextureVersion = sat.texture_version;
    loadGrid().catch(console.error);
  }
}
new LiveSocket(applyFrame, updateConnection);

document.getElementById("sat-view-texture")?.addEventListener("click", () => {
  classified = false;
  map.setPaintProperty("sat-ndvi-layer", "raster-contrast", 0.1);
  map.setPaintProperty("sat-ndvi-layer", "raster-saturation", 0.1);
  document.getElementById("sat-view-texture").classList.add("active");
  document.getElementById("sat-view-class").classList.remove("active");
});
document.getElementById("sat-view-class")?.addEventListener("click", () => {
  classified = true;
  map.setPaintProperty("sat-ndvi-layer", "raster-contrast", 0.55);
  map.setPaintProperty("sat-ndvi-layer", "raster-saturation", 0.55);
  document.getElementById("sat-view-class").classList.add("active");
  document.getElementById("sat-view-texture").classList.remove("active");
});
document.getElementById("sat-reset")?.addEventListener("click", () => fitAOI(map, window.innerWidth < 760 ? 24 : 48));
bindFullscreen("sat-fullscreen", "satellite-map-shell", map);
window.addEventListener("resize", () => { map.resize(); drawHistogram(latestGrid); }, { passive: true });
