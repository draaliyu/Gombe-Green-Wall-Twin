import {
  LiveSocket,
  fetchJson,
  formatDateTime,
  formatNumber,
  formatPercent,
  setText,
  updateConnection,
  updateSourceBadge,
} from "./common.js";

function renderInsights(items) {
  const container = document.getElementById("evidence-insights");
  container.innerHTML = "";
  (items || []).forEach((item) => {
    const article = document.createElement("article");
    article.className = `insight ${item.kind}`;
    const evidence = (item.evidence || []).map((entry) => `<li>${entry}</li>`).join("");
    article.innerHTML = `<span class="kind">${item.kind} • confidence ${item.confidence}</span><h4>${item.title}</h4><p>${item.body}</p>${evidence ? `<ul style="color:#718d81;font-size:10px;line-height:1.5;padding-left:17px">${evidence}</ul>` : ""}`;
    container.appendChild(article);
  });
}

function applyFrame(frame) {
  const sat = frame.satellite;
  const gfw = frame.gfw;
  const sim = frame.simulation;
  setText("evidence-last-updated", `Last updated ${formatDateTime(frame.generated_at)}`);
  updateSourceBadge("evidence-sentinel-mode", sat.mode);
  updateSourceBadge("evidence-gfw-mode", gfw.mode);
  setText("evidence-ndvi", formatNumber(sat.stats.mean, 3));
  setText("evidence-coverage", formatPercent(sat.stats.valid_fraction));
  setText("evidence-sentinel-note", sat.note);
  setText("evidence-gfw-loss", formatNumber(gfw.cumulative_loss_ha, 1));
  setText("evidence-gfw-latest", formatNumber(gfw.latest_year_loss_ha, 1));
  setText("evidence-gfw-note", gfw.note);
  setText("evidence-tick", sim.metrics.tick.toLocaleString());
  setText("evidence-barrier", formatPercent(sim.metrics.barrier_fraction, 2));
  renderInsights(frame.insights);
}
new LiveSocket(applyFrame, updateConnection);

fetchJson("/api/methodology").then((methodology) => {
  const ndvi = methodology.ndvi;
  document.getElementById("ndvi-methodology").innerHTML = `
    <p><strong>Formula:</strong> <code>${ndvi.formula}</code></p>
    <p><strong>Source:</strong> ${ndvi.source}</p>
    <p><strong>Masking:</strong> ${ndvi.masking}</p>
    <p><strong>Interpretation:</strong> ${ndvi.interpretation}</p>
  `;
}).catch((error) => setText("ndvi-methodology", `Could not load methodology: ${error.message}`));
