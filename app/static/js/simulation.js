import {
  LiveSocket,
  fetchJson,
  formatDateTime,
  formatPercent,
  setText,
  showToast,
  updateConnection,
} from "./common.js";

const canvas = document.getElementById("simulation-canvas");
const ctx = canvas.getContext("2d");
let latestFrame = null;
let lastTextureVersion = -1;
let simulationImage = new Image();
let scenarioInitialised = false;
let history = [];

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(420, Math.floor(rect.width * dpr));
  canvas.height = Math.max(360, Math.floor(Math.max(rect.height, 520) * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawSimulation();
}

function drawSimulation() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);
  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, "#13231d");
  gradient.addColorStop(1, "#3d2a1c");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);
  if (simulationImage.complete && simulationImage.naturalWidth) {
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(simulationImage, 0, 0, width, height);
  }
  ctx.strokeStyle = "rgba(220,255,232,.08)";
  ctx.lineWidth = 1;
  for (let x = 0; x < width; x += width / 24) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
  for (let y = 0; y < height; y += height / 18) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
  ctx.fillStyle = "rgba(6,16,17,.76)";
  ctx.fillRect(14, 14, 230, 62);
  ctx.fillStyle = "#effaf2";
  ctx.font = "700 13px system-ui";
  ctx.fillText("LIVE CELLULAR LANDSCAPE", 27, 38);
  ctx.fillStyle = "#9eb9ad";
  ctx.font = "11px system-ui";
  ctx.fillText("green = vegetation • amber = desert • mint = barrier", 27, 59);
}

function loadSimulationImage(version) {
  simulationImage = new Image();
  simulationImage.onload = drawSimulation;
  simulationImage.src = `/api/simulation/texture.png?v=${version}&t=${Date.now()}`;
}

function setScenarioControls(parameters) {
  Object.entries(parameters).forEach(([key, value]) => {
    const input = document.querySelector(`[data-parameter="${key}"]`);
    if (!input) return;
    input.value = value;
    const outputId = `${input.id}-value`;
    setText(outputId, Number(value).toFixed(key.includes("rate") ? 3 : 2));
  });
  scenarioInitialised = true;
}

function applyFrame(frame) {
  latestFrame = frame;
  const simulation = frame.simulation;
  const metrics = simulation.metrics;
  setText("sim-last-updated", `Last updated ${formatDateTime(frame.generated_at)}`);
  setText("lab-tick", metrics.tick.toLocaleString());
  setText("lab-speed", `${simulation.speed.toFixed(2)}×`);
  setText("lab-vegetated", formatPercent(metrics.vegetated_fraction));
  setText("lab-desert", formatPercent(metrics.desert_fraction));
  setText("lab-barrier", formatPercent(metrics.barrier_fraction, 2));
  setText("lab-health", formatPercent(metrics.mean_tree_health));
  setText("sim-run-toggle", simulation.running ? "Pause" : "Resume");
  if (!scenarioInitialised) setScenarioControls(simulation.parameters);
  if (simulation.texture_version !== lastTextureVersion) {
    lastTextureVersion = simulation.texture_version;
    loadSimulationImage(lastTextureVersion);
  }
  history.push({ tick: metrics.tick, vegetation: metrics.vegetated_fraction, desert: metrics.desert_fraction, barrier: metrics.barrier_fraction });
  history = history.slice(-120);
  drawHistory();
}

function drawHistory() {
  const chart = document.getElementById("history-chart");
  if (!chart) return;
  const rect = chart.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  chart.width = Math.max(400, Math.floor(rect.width * dpr));
  chart.height = Math.max(220, Math.floor(rect.height * dpr));
  const c = chart.getContext("2d");
  c.scale(dpr, dpr);
  const width = chart.width / dpr, height = chart.height / dpr;
  c.clearRect(0, 0, width, height);
  const pad = { l: 38, r: 12, t: 15, b: 26 };
  c.strokeStyle = "rgba(158,185,173,.18)";
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (height - pad.t - pad.b) * i / 4;
    c.beginPath(); c.moveTo(pad.l, y); c.lineTo(width - pad.r, y); c.stroke();
  }
  const plotW = width - pad.l - pad.r, plotH = height - pad.t - pad.b;
  const series = [
    { key: "vegetation", color: "#69f0aa" },
    { key: "desert", color: "#e0a24f" },
    { key: "barrier", color: "#d6ff74" },
  ];
  series.forEach(({ key, color }) => {
    c.strokeStyle = color; c.lineWidth = 2; c.beginPath();
    history.forEach((item, index) => {
      const x = pad.l + (history.length <= 1 ? 0 : index / (history.length - 1)) * plotW;
      const y = pad.t + (1 - item[key]) * plotH;
      if (index === 0) c.moveTo(x, y); else c.lineTo(x, y);
    });
    c.stroke();
  });
  c.fillStyle = "#9eb9ad"; c.font = "10px system-ui";
  c.fillText("0%", 10, height - pad.b + 3); c.fillText("100%", 5, pad.t + 3);
  c.fillStyle = "#69f0aa"; c.fillText("Vegetation", pad.l, height - 7);
  c.fillStyle = "#e0a24f"; c.fillText("Desert", pad.l + 78, height - 7);
  c.fillStyle = "#d6ff74"; c.fillText("Barrier", pad.l + 126, height - 7);
}

new LiveSocket(applyFrame, updateConnection);

document.querySelectorAll("[data-parameter]").forEach((input) => {
  input.addEventListener("input", () => setText(`${input.id}-value`, Number(input.value).toFixed(input.dataset.parameter.includes("rate") ? 3 : 2)));
});

document.getElementById("apply-scenario")?.addEventListener("click", async () => {
  const parameters = {};
  document.querySelectorAll("[data-parameter]").forEach((input) => { parameters[input.dataset.parameter] = Number(input.value); });
  try {
    await fetchJson("/api/simulation/scenario", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(parameters) });
    showToast("Scenario parameters applied.");
  } catch (error) { showToast(`Scenario update failed: ${error.message}`); }
});

document.getElementById("sim-run-toggle")?.addEventListener("click", async () => {
  if (!latestFrame) return;
  await fetchJson("/api/simulation/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ running: !latestFrame.simulation.running }) });
});
document.getElementById("sim-step-faster")?.addEventListener("click", async () => {
  if (!latestFrame) return;
  const next = latestFrame.simulation.speed >= 4 ? 0.5 : Math.min(5, latestFrame.simulation.speed + 0.5);
  await fetchJson("/api/simulation/speed", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ speed: next }) });
});
document.getElementById("sim-reset")?.addEventListener("click", async () => {
  await fetchJson("/api/simulation/reset", { method: "POST" });
  history = [];
  showToast("Simulation reset from the latest NDVI grid.");
});

window.addEventListener("resize", () => { resizeCanvas(); drawHistory(); }, { passive: true });
resizeCanvas();
