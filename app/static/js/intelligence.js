import {
  AOI, createMap, fetchJson, fitNorth, fitState, LiveSocket, updateConnection, formatPercent, formatNumber, showToast,
} from "./common.js?v=4.0.0";

const page = document.body.dataset.page || "services";
const $ = (id) => document.getElementById(id);
const text = (id, value) => { const node = $(id); if (node) node.textContent = value; };
const pct = (value, digits = 1) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(digits)}%` : "—";
const number = (value, digits = 1, suffix = "") => Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)}${suffix}` : "—";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
let latestFrame = null;
let adminToken = sessionStorage.getItem("gombe_admin_token") || "";

function setActiveNav() {
  document.querySelectorAll("[data-nav]").forEach((link) => link.classList.toggle("active", link.dataset.nav === page));
}

function updateLiveTime(value = new Date()) {
  document.querySelectorAll("[data-live-time]").forEach((node) => {
    node.textContent = `Live update: ${new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })} WAT`;
  });
}

function resizeCanvas(canvas, height = null) {
  if (!canvas) return null;
  const dpr = Math.min(window.devicePixelRatio || 1, window.innerWidth < 760 ? 1.25 : 2);
  const rect = canvas.getBoundingClientRect();
  const cssHeight = height || rect.height || 220;
  const width = Math.max(300, rect.width || canvas.parentElement?.clientWidth || 600);
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height: cssHeight };
}

function drawLineChart(canvas, series, options = {}) {
  const setup = resizeCanvas(canvas, options.height);
  if (!setup) return;
  const { ctx, width, height } = setup;
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 44, right: 18, top: 18, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const all = series.flatMap((item) => item.values.filter(Number.isFinite));
  const min = options.min ?? Math.min(...all, 0);
  const max = options.max ?? Math.max(...all, 1);
  ctx.strokeStyle = "rgba(142,214,202,.13)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + plotH * i / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    ctx.fillStyle = "rgba(189,218,214,.65)"; ctx.font = "10px sans-serif"; ctx.textAlign = "right";
    ctx.fillText((max - (max - min) * i / 4).toFixed(options.digits ?? 2), pad.left - 7, y + 3);
  }
  const colors = options.colors || ["#4ce5a7", "#e7b45a", "#66e7ef", "#ef5a55", "#b38bff", "#ff8b4a"];
  series.forEach((item, index) => {
    const values = item.values;
    ctx.beginPath();
    values.forEach((value, i) => {
      if (!Number.isFinite(value)) return;
      const x = pad.left + (values.length <= 1 ? 0 : plotW * i / (values.length - 1));
      const y = pad.top + plotH * (1 - (value - min) / Math.max(max - min, 1e-9));
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = colors[index % colors.length]; ctx.lineWidth = index === 0 ? 2.4 : 1.7; ctx.stroke();
  });
  if (options.labels?.length) {
    ctx.fillStyle = "rgba(192,218,214,.7)"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
    const step = Math.max(1, Math.floor(options.labels.length / 6));
    options.labels.forEach((label, i) => {
      if (i % step && i !== options.labels.length - 1) return;
      const x = pad.left + (options.labels.length <= 1 ? 0 : plotW * i / (options.labels.length - 1));
      ctx.fillText(String(label).slice(0, 10), x, height - 8);
    });
  }
  const legend = options.legend || series.map((item) => item.name);
  ctx.textAlign = "left"; ctx.font = "10px sans-serif";
  legend.forEach((label, i) => { ctx.fillStyle = colors[i % colors.length]; ctx.fillRect(pad.left + i * 130, 4, 12, 3); ctx.fillStyle = "#bed1ce"; ctx.fillText(label, pad.left + 18 + i * 130, 8); });
}

function drawBars(canvas, values, labels, options = {}) {
  const setup = resizeCanvas(canvas, options.height);
  if (!setup) return;
  const { ctx, width, height } = setup;
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 38, right: 15, top: 18, bottom: 34 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const max = options.max || Math.max(...values.map((v) => Math.abs(v)), 1);
  const hasNegative = values.some((v) => v < 0);
  const baseY = hasNegative ? pad.top + plotH / 2 : pad.top + plotH;
  const barW = Math.max(2, plotW / Math.max(values.length, 1) * .72);
  values.forEach((value, index) => {
    const x = pad.left + (index + .5) * plotW / values.length - barW / 2;
    const h = Math.abs(value) / max * (hasNegative ? plotH / 2 : plotH);
    const y = value >= 0 ? baseY - h : baseY;
    const gradient = ctx.createLinearGradient(0, y, 0, y + h);
    gradient.addColorStop(0, value >= 0 ? "#4ce5a7" : "#ef5a55");
    gradient.addColorStop(1, value >= 0 ? "#17785f" : "#8c292e");
    ctx.fillStyle = gradient; ctx.fillRect(x, y, barW, h);
  });
  ctx.strokeStyle = "rgba(180,225,215,.3)"; ctx.beginPath(); ctx.moveTo(pad.left, baseY); ctx.lineTo(width - pad.right, baseY); ctx.stroke();
  ctx.fillStyle = "rgba(192,218,214,.7)"; ctx.font = "9px sans-serif"; ctx.textAlign = "center";
  const step = Math.max(1, Math.floor(labels.length / 7));
  labels.forEach((label, i) => { if (i % step === 0 || i === labels.length - 1) ctx.fillText(String(label).slice(0, 7), pad.left + (i + .5) * plotW / labels.length, height - 10); });
}

function drawRadarChart(canvas, labels, values) {
  const setup = resizeCanvas(canvas, 230); if (!setup) return;
  const { ctx, width, height } = setup;
  ctx.clearRect(0, 0, width, height);
  const centerX = width / 2, centerY = height / 2 + 7, radius = Math.min(width, height) * .35;
  ctx.strokeStyle = "rgba(124,225,202,.18)"; ctx.fillStyle = "rgba(76,229,167,.18)";
  for (let level = 1; level <= 5; level += 1) {
    ctx.beginPath(); labels.forEach((_, i) => { const angle = -Math.PI / 2 + i / labels.length * Math.PI * 2; const r = radius * level / 5; const x = centerX + Math.cos(angle) * r, y = centerY + Math.sin(angle) * r; if (!i) ctx.moveTo(x, y); else ctx.lineTo(x, y); }); ctx.closePath(); ctx.stroke();
  }
  ctx.beginPath(); values.forEach((value, i) => { const angle = -Math.PI / 2 + i / labels.length * Math.PI * 2; const r = radius * Math.max(0, Math.min(100, value)) / 100; const x = centerX + Math.cos(angle) * r, y = centerY + Math.sin(angle) * r; if (!i) ctx.moveTo(x, y); else ctx.lineTo(x, y); }); ctx.closePath(); ctx.fill(); ctx.strokeStyle = "#4ce5a7"; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = "#c9dad7"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  labels.forEach((label, i) => { const angle = -Math.PI / 2 + i / labels.length * Math.PI * 2; ctx.fillText(label.replaceAll("_", " "), centerX + Math.cos(angle) * (radius + 22), centerY + Math.sin(angle) * (radius + 22)); });
}

function startAmbient() {
  const canvas = $("ambient-earth-canvas"); if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let particles = [];
  function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; particles = Array.from({ length: window.innerWidth < 760 ? 28 : 65 }, () => ({ x: Math.random() * canvas.width, y: Math.random() * canvas.height, r: 1 + Math.random() * 2, s: .08 + Math.random() * .25, a: .12 + Math.random() * .35 })); }
  function frame() { ctx.clearRect(0, 0, canvas.width, canvas.height); const gradient = ctx.createRadialGradient(canvas.width * .5, canvas.height * .15, 0, canvas.width * .5, canvas.height * .15, canvas.width * .75); gradient.addColorStop(0, "rgba(53,169,143,.16)"); gradient.addColorStop(1, "rgba(0,0,0,0)"); ctx.fillStyle = gradient; ctx.fillRect(0, 0, canvas.width, canvas.height); particles.forEach((p) => { p.y -= p.s; p.x += Math.sin(p.y * .01) * .08; if (p.y < -5) { p.y = canvas.height + 5; p.x = Math.random() * canvas.width; } ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fillStyle = `rgba(98,230,193,${p.a})`; ctx.fill(); }); requestAnimationFrame(frame); }
  resize(); window.addEventListener("resize", resize); frame();
}

function addImageOverlay(map, id, url, opacity = .65) {
  const coordinates = [[AOI.west, AOI.north], [AOI.east, AOI.north], [AOI.east, AOI.south], [AOI.west, AOI.south]];
  const add = () => {
    if (!map.getSource(id)) map.addSource(id, { type: "image", url: `${url}?t=${Date.now()}`, coordinates });
    if (!map.getLayer(id)) map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": opacity, "raster-fade-duration": 0 } }, "lga-outline");
  };
  if (map.loaded()) add(); else map.once("administrativeready", add);
}

function evidenceHtml(items) {
  return (items || []).map((item) => `<article><h4>${escapeHtml(item.title || item.kind || "Evidence")}</h4><p>${escapeHtml(item.body || item.text || "")}</p></article>`).join("");
}

async function login(password) {
  const response = await fetchJson("/api/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
  adminToken = response.token; sessionStorage.setItem("gombe_admin_token", adminToken); return response;
}

async function adminFetch(url, options = {}) {
  const headers = new Headers(options.headers || {}); headers.set("Authorization", `Bearer ${adminToken}`); if (!headers.has("Content-Type") && options.body) headers.set("Content-Type", "application/json");
  return fetchJson(url, { ...options, headers });
}

const services = [
  ["◷", "Temporal Change", "/timeline", "Replay greenness, rainfall and scenario change through time."],
  ["☂", "Rainfall & Drought", "/drought", "Dry spells, anomalies, water balance and rainy-season onset."],
  ["▦", "Land Cover", "/landcover", "Nine-class cover probabilities with source confidence."],
  ["⌁", "Sentinel-1 Radar", "/radar", "Cloud-independent structure and moisture-sensitive evidence."],
  ["♧", "Restoration Suitability", "/restoration", "Screen sites and optimise alternative Green Wall routes."],
  ["◉", "Carbon & Ecosystems", "/ecosystems", "Biomass uncertainty and ecosystem-service scenario scores."],
  ["⚠", "Fire, Erosion & Water", "/risks", "Thermal anomalies, erosion, runoff and infiltration."],
  ["⇄", "Scenario Comparison", "/scenarios", "Compare intervention, drought, fire and maintenance pathways."],
  ["⌖", "Field Verification", "/field", "Protected geotagged evidence and verification status."],
  ["▤", "Project Registry", "/projects", "Track planting targets, maintenance and survival inspections."],
  ["✦", "Explainable Prediction", "/predictions", "Protected retraining, uncertainty and feature influence."],
  ["▣", "Satellite-to-Ground", "/compare", "Synchronized observed, classified and simulated views."],
];

async function initServices() {
  const grid = $("service-hub-grid");
  if (grid) grid.innerHTML = services.map(([icon, name, href, description]) => `<a class="service-tile" href="${href}"><i>${icon}</i><div><h3>${name}</h3><p>${description}</p></div><span>Open service →</span></a>`).join("");
  const [summary, health] = await Promise.all([fetchJson("/api/intelligence/summary"), fetchJson("/api/health")]);
  const metrics = $("services-metrics");
  if (metrics) metrics.innerHTML = [
    ["NDVI trend", summary.temporal.trend], ["Drought", `${summary.drought?.score ?? "—"}/100`], ["Radar RVI", summary.radar.mean_rvi ?? "—"], ["FIRMS", summary.fire.count ?? 0], ["Carbon", number(summary.carbon.carbon_t, 0, " t")], ["Combined risk", pct(summary.risks.combined)], ["Projects", summary.projects], ["Field records", summary.field_observations],
  ].map(([label, value]) => `<div><small>${label}</small><strong>${value}</strong></div>`).join("");
  text("services-mode", summary.temporal.mode);
  const alerts = $("services-alerts"); if (alerts) alerts.innerHTML = renderAlerts(summary.alerts);
  const sources = $("services-sources"); if (sources) sources.innerHTML = [
    ["Copernicus", health.copernicus_configured], ["Global Forest Watch", health.gfw_configured], ["OpenWeather", health.weather_configured], ["NASA FIRMS", health.firms_configured], ["Administrator", health.admin_configured],
  ].map(([name, ready]) => `<div><span>${name}</span><b class="${ready ? "live" : "demo"}">${ready ? "configured" : "fallback / unavailable"}</b></div>`).join("");
}

function renderAlerts(alerts = []) { return alerts.map((item) => `<div class="alert-item ${item.severity}"><i></i><div><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.body)}</p></div></div>`).join(""); }

async function initTimeline() {
  const data = await fetchJson("/api/temporal"); const points = data.points || [];
  text("timeline-mode", data.mode); const slider = $("timeline-slider"); if (!points.length) return;
  slider.max = points.length - 1; slider.value = points.length - 1;
  const map = createMap("timeline-map", { pitch: 40 }); map.once("administrativeready", () => { fitState(map, 50); addImageOverlay(map, "timeline-ndvi-layer", "/api/ndvi/texture.png", .74); });
  $("timeline-before").style.backgroundImage = "url('/api/ndvi/texture.png')"; $("timeline-after").style.backgroundImage = "url('/api/simulation/texture.png')";
  const chart = $("timeline-chart"); drawLineChart(chart, [{ name: "NDVI", values: points.map((p) => Number(p.ndvi)) }, { name: "Vegetated", values: points.map((p) => Number(p.vegetated_fraction)) }, { name: "Desert", values: points.map((p) => Number(p.desert_fraction)) }], { labels: points.map((p) => p.period), min: 0, max: 1 });
  function select(index) { const p = points[index]; text("timeline-period", p.period); text("timeline-ndvi", number(p.ndvi, 3)); const selected = $("timeline-selected"); if (selected) selected.innerHTML = `<div><small>Rainfall</small><strong>${number(p.rain_mm,1," mm")}</strong></div><div><small>Vegetated fraction</small><strong>${pct(p.vegetated_fraction)}</strong></div><div><small>Desert pressure</small><strong>${pct(p.desert_fraction)}</strong></div><div><small>Evidence mode</small><strong>${escapeHtml(p.mode)}</strong></div>`; }
  select(points.length - 1); slider.addEventListener("input", () => select(Number(slider.value)));
  let playing = false, timer; $("timeline-play")?.addEventListener("click", () => { playing = !playing; $("timeline-play").textContent = playing ? "Ⅱ Pause" : "▶ Play"; clearInterval(timer); if (playing) timer = setInterval(() => { slider.value = (Number(slider.value) + 1) % points.length; select(Number(slider.value)); }, 850); });
  $("swipe-control")?.addEventListener("input", (event) => { const v = event.target.value; $("timeline-before").style.clipPath = `inset(0 ${100 - v}% 0 0)`; $("timeline-after").style.clipPath = `inset(0 0 0 ${v}%)`; });
  const interp = $("timeline-interpretation"); if (interp) interp.innerHTML = evidenceHtml([{ title: "Trend", body: `The timeline is classified as ${data.trend}; year-on-year NDVI change is ${Number(data.year_on_year_ndvi_change).toFixed(3)}.` }, { title: "Data provenance", body: data.note }, { title: "Limitation", body: data.limitations }]);
}

function animateDroughtSky(data) {
  const canvas = $("drought-sky"); if (!canvas) return; const ctx = canvas.getContext("2d"); let t = 0; const score = Number(data.drought_screen?.score || 0); const rain = Number(data.totals_mm?.["7"] || 0);
  function resize() { canvas.width = canvas.clientWidth * Math.min(devicePixelRatio, 1.5); canvas.height = canvas.clientHeight * Math.min(devicePixelRatio, 1.5); }
  function frame() { const dpr = Math.min(devicePixelRatio,1.5); const w=canvas.width/dpr,h=canvas.height/dpr; ctx.setTransform(dpr,0,0,dpr,0,0); const g=ctx.createLinearGradient(0,0,0,h); g.addColorStop(0, score>60?"#b35f3b":"#2f7288");g.addColorStop(.6,score>60?"#d29b5c":"#72999b");g.addColorStop(1,"#725734");ctx.fillStyle=g;ctx.fillRect(0,0,w,h); const sunX=w*(.2+.1*Math.sin(t*.0002));ctx.beginPath();ctx.arc(sunX,h*.22,34,0,Math.PI*2);ctx.fillStyle=`rgba(255,220,107,${.65+score/300})`;ctx.shadowBlur=45;ctx.shadowColor="#ffd66e";ctx.fill();ctx.shadowBlur=0; const clouds=Math.max(2,Math.min(12,Math.round(rain/10)));for(let i=0;i<clouds;i++){const x=(i*170+t*.01*(1+i*.02))%(w+300)-150;const y=70+(i%4)*45;ctx.fillStyle="rgba(230,244,239,.32)";ctx.beginPath();ctx.ellipse(x,y,70,22,0,0,Math.PI*2);ctx.fill();} if(rain>15){ctx.strokeStyle="rgba(120,210,255,.45)";for(let i=0;i<80;i++){const x=(i*47+t*.09)%w;const y=(i*83+t*.12)%h;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x-5,y+17);ctx.stroke();}} t+=16;requestAnimationFrame(frame); } resize();window.addEventListener("resize",resize);frame();
}

async function initDrought() {
  const data = await fetchJson("/api/rainfall"); text("rainfall-mode", data.mode); text("drought-score", data.drought_screen?.score ?? "—"); text("drought-category", data.drought_screen?.category ?? "—"); $("drought-cinema")?.style.setProperty("--drought-angle", `${data.drought_screen?.score || 0}%`);
  animateDroughtSky(data);
  const telemetry = $("rain-telemetry"); if (telemetry) telemetry.innerHTML = [["7-day rain", number(data.totals_mm?.["7"],1," mm")],["30-day rain",number(data.totals_mm?.["30"],1," mm")],["Dry days",data.consecutive_dry_days ?? "—"],["Onset",data.rainy_season_onset || "Not detected"]].map(([a,b])=>`<div><small>${a}</small><strong>${b}</strong></div>`).join("");
  const daily = data.daily || []; drawBars($("rainfall-chart"), daily.map((d)=>Number(d.rain_mm)), daily.map((d)=>d.date), { height:280 }); const monthly=data.monthly||[]; drawBars($("monthly-rain-chart"),monthly.map((m)=>Number(m.rain_mm)),monthly.map((m)=>m.period),{height:220});
  const metrics=$("water-balance-metrics");if(metrics)metrics.innerHTML=[["30-day balance",number(data.water_balance_30d_mm,1," mm")],["Monthly anomaly",number(data.latest_month_anomaly_percent,1,"%")],["Soil moisture",number(data.soil_moisture_latest,3)],["Drought category",data.drought_screen?.category||"—"]].map(([a,b])=>`<div><small>${a}</small><strong>${b}</strong></div>`).join("");
  const interp=$("drought-interpretation");if(interp)interp.innerHTML=evidenceHtml([...(data.interpretation||[]),{title:"Limitation",body:data.limitations}]);
}

async function initLandcover() {
  const data=await fetchJson("/api/landcover"); text("landcover-mode",data.mode);text("landcover-dominant",String(data.dominant_class||"—").replaceAll("_"," "));text("landcover-confidence",`Mean class confidence: ${pct(data.mean_confidence)}.`);
  const map=createMap("landcover-map",{pitch:35});map.once("administrativeready",()=>{fitState(map,45);addImageOverlay(map,"landcover-layer","/api/landcover/texture.png",.76);});$("landcover-state")?.addEventListener("click",()=>fitState(map));$("landcover-north")?.addEventListener("click",()=>fitNorth(map));$("landcover-full")?.addEventListener("click",()=>document.getElementById("landcover-map")?.parentElement?.requestFullscreen?.());
  const entries=Object.entries(data.classes||{});drawBars($("landcover-chart"),entries.map(([,v])=>Number(v)*100),entries.map(([k])=>k.replaceAll("_"," ")),{height:220,max:100});const legend=$("landcover-legend");if(legend)legend.innerHTML=`<b>Land-cover classes</b>${entries.map(([k,v])=>`<div><span>${k.replaceAll("_"," ")}</span><strong>${pct(v)}</strong></div>`).join("")}`;const note=$("landcover-note");if(note)note.innerHTML=evidenceHtml([{title:"Production mode",body:data.note},{title:"Attribution",body:data.attribution},{title:"Limitation",body:data.limitations}]);
}

function animateRadar() { const canvas=$("radar-sweep");if(!canvas)return;const ctx=canvas.getContext("2d");let angle=0;function resize(){canvas.width=canvas.clientWidth;canvas.height=canvas.clientHeight}function frame(){ctx.clearRect(0,0,canvas.width,canvas.height);const x=canvas.width*.5,y=canvas.height*.5,r=Math.max(canvas.width,canvas.height)*.55;const g=ctx.createConicGradient(angle,x,y);g.addColorStop(0,"rgba(87,255,220,.0)");g.addColorStop(.04,"rgba(87,255,220,.34)");g.addColorStop(.12,"rgba(87,255,220,.0)");ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();for(let i=1;i<5;i++){ctx.beginPath();ctx.arc(x,y,r*i/5,0,Math.PI*2);ctx.strokeStyle="rgba(93,235,215,.12)";ctx.stroke()}angle+=.012;requestAnimationFrame(frame)}resize();window.addEventListener("resize",resize);frame(); }

async function initRadar() { const data=await fetchJson("/api/radar");text("radar-rvi",number(data.mean_rvi,2));text("radar-mode",data.mode);const map=createMap("radar-map",{pitch:45});map.once("administrativeready",()=>{fitNorth(map,45);addImageOverlay(map,"radar-layer","/api/radar/texture.png",.72);});animateRadar();const metrics=$("radar-metrics");if(metrics)metrics.innerHTML=[["VV backscatter",number(data.mean_vv_db,1," dB")],["VH backscatter",number(data.mean_vh_db,1," dB")],["Valid coverage",pct(data.valid_fraction)],["Source",data.source]].map(([a,b])=>`<div><small>${a}</small><strong>${b}</strong></div>`).join("");const interp=$("radar-interpretation");if(interp)interp.innerHTML=evidenceHtml([...(data.interpretation||[]),{title:"Limitation",body:data.limitations}]);drawLineChart($("radar-comparison"),[{name:"RVI profile",values:(data.grid||[]).slice(0,24).map((row)=>row.reduce((a,b)=>a+Number(b),0)/Math.max(row.length,1))}],{height:220,min:0,max:1,labels:(data.grid||[]).slice(0,24).map((_,i)=>`row ${i+1}`)}); }

async function initRestoration() { const data=await fetchJson("/api/suitability");text("suitability-mode",data.mode);const map=createMap("restoration-map",{pitch:48});let mapReadyResolve;const mapReady=new Promise((resolve)=>{mapReadyResolve=resolve});map.once("administrativeready",()=>{fitNorth(map,45);addImageOverlay(map,"suitability-layer","/api/suitability/texture.png",.72);mapReadyResolve();});const classes=$("suitability-classes");if(classes)classes.innerHTML=Object.entries(data.classes||{}).map(([k,v])=>`<div><small>${k.replaceAll("_"," ")}</small><strong>${pct(v)}</strong></div>`).join("");const factors=$("suitability-factors");if(factors)factors.innerHTML=(data.factors||[]).map((f)=>`<div><b>${escapeHtml(f.name)}</b><p>Weight: ${(f.weight*100).toFixed(0)}%</p></div>`).join("")+`<div><b>Limitation</b><p>${escapeHtml(data.limitations)}</p></div>`;
  let start=null,end=null,mode="start";$("route-start")?.addEventListener("click",()=>{mode="start";text("route-status","Tap the map to set the route start.")});$("route-end")?.addEventListener("click",()=>{mode="end";text("route-status","Tap the map to set the route end.")});map.on("click",(event)=>{if(mode==="start"){start=[event.lngLat.lng,event.lngLat.lat];mode="end";text("route-status","Start set. Tap to set route end.")}else{end=[event.lngLat.lng,event.lngLat.lat];text("route-status","End set. Generate route options.")}});$("route-clear")?.addEventListener("click",()=>{start=end=null;["route-0","route-1","route-2"].forEach((id)=>{if(map.getLayer(id))map.removeLayer(id);if(map.getSource(id))map.removeSource(id)});text("route-status","Route selection cleared.")});$("route-generate")?.addEventListener("click",async()=>{text("route-status","Optimising routes…");const routes=await fetchJson("/api/suitability/routes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({start,end})});renderRoutes(map,routes);text("route-status",`${routes.routes.length} route options generated.`)});const defaults=await fetchJson("/api/suitability/routes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({start:null,end:null})});await mapReady;renderRoutes(map,defaults); }

function renderRoutes(map,data){const colors=["#4ce5a7","#e7b45a","#66e7ef"];const cards=$("route-cards");if(cards)cards.innerHTML=(data.routes||[]).map((r,i)=>`<article class="route-card"><h4>${escapeHtml(r.name)}</h4><p><b>${number(r.length_km,1," km")}</b> • mean suitability ${pct(r.mean_suitability)}</p><small>${escapeHtml(r.screening_note)}</small></article>`).join("");(data.routes||[]).forEach((route,index)=>{const id=`route-${index}`;const geo={type:"Feature",geometry:{type:"LineString",coordinates:route.coordinates},properties:{}};if(map.getSource(id))map.getSource(id).setData(geo);else map.addSource(id,{type:"geojson",data:geo});if(!map.getLayer(id))map.addLayer({id,type:"line",source:id,paint:{"line-color":colors[index],"line-width":4-index*.6,"line-opacity":.9,"line-blur":.3}},"lga-labels")});}

function animateEcosystemGlobe(){const canvas=$("ecosystem-globe");if(!canvas)return;const ctx=canvas.getContext("2d");let a=0;function resize(){canvas.width=canvas.clientWidth;canvas.height=canvas.clientHeight}function frame(){ctx.clearRect(0,0,canvas.width,canvas.height);const r=Math.min(canvas.width,canvas.height)*.34,cx=canvas.width*.48,cy=canvas.height*.5;const g=ctx.createRadialGradient(cx-r*.3,cy-r*.4,5,cx,cy,r);g.addColorStop(0,"#72e2a4");g.addColorStop(.5,"#175b43");g.addColorStop(1,"#06271f");ctx.fillStyle=g;ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();ctx.save();ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.clip();ctx.strokeStyle="rgba(136,250,191,.35)";for(let i=-5;i<=5;i++){ctx.beginPath();ctx.ellipse(cx+Math.sin(a+i)*r*.1,cy+i*r*.14,r*.95,Math.max(3,r*.07),a*.1,0,Math.PI*2);ctx.stroke()}for(let i=0;i<60;i++){const x=cx+Math.sin(i*12.989+a)*r*.85,y=cy+Math.sin(i*7.13-a*.4)*r*.75;ctx.fillStyle=`rgba(92,230,139,${.2+(i%5)*.08})`;ctx.beginPath();ctx.arc(x,y,2+(i%3),0,Math.PI*2);ctx.fill()}ctx.restore();a+=.006;requestAnimationFrame(frame)}resize();window.addEventListener("resize",resize);frame();}

async function initEcosystems(){const data=await fetchJson("/api/carbon");animateEcosystemGlobe();text("carbon-mode",data.mode);text("carbon-total",number(data.estimated_total_carbon_t,0," t C"));text("biomass-density",number(data.aboveground_biomass_density_mg_ha,1," Mg/ha"));text("biomass-uncertainty",`Screening uncertainty ±${number(data.uncertainty_mg_ha,1," Mg/ha")}`);text("carbon-gain",number(data.scenario_annual_carbon_gain_t,1," t C/yr"));text("co2-total",number(data.estimated_total_co2e_t,0," t CO₂e"));const entries=Object.entries(data.ecosystem_service_scores||{});drawRadarChart($("ecosystem-radar"),entries.map(([k])=>k),entries.map(([,v])=>Number(v)));const note=$("carbon-note");if(note)note.innerHTML=evidenceHtml([{title:"Production mode",body:data.note},{title:"Limitation",body:data.limitations}]);}

function animateRiskParticles(hotspots=[]){const canvas=$("risk-particles");if(!canvas)return;const ctx=canvas.getContext("2d");let particles=[];function resize(){canvas.width=canvas.clientWidth;canvas.height=canvas.clientHeight;particles=Array.from({length:Math.max(35,hotspots.length*20)},(_,i)=>({x:Math.random()*canvas.width,y:Math.random()*canvas.height,s:.4+Math.random()*1.4,a:.2+Math.random()*.5,kind:i<hotspots.length*8?"fire":"sand"}))}function frame(){ctx.clearRect(0,0,canvas.width,canvas.height);particles.forEach((p)=>{p.x+=p.s;p.y+=Math.sin(p.x*.02)*.2;if(p.x>canvas.width+5)p.x=-5;ctx.fillStyle=p.kind==="fire"?`rgba(255,96,45,${p.a})`:`rgba(236,184,82,${p.a})`;ctx.beginPath();ctx.arc(p.x,p.y,p.kind==="fire"?2.5:1.2,0,Math.PI*2);ctx.fill()});requestAnimationFrame(frame)}resize();window.addEventListener("resize",resize);frame();}

async function initRisks(){const [risk,fire,alerts]=await Promise.all([fetchJson("/api/risks"),fetchJson("/api/fires"),fetchJson("/api/alerts")]);const map=createMap("risk-map",{pitch:48});map.once("administrativeready",()=>{fitNorth(map,45);addImageOverlay(map,"risk-layer","/api/risks/texture.png",.73);if(fire.hotspots?.length){const geo={type:"FeatureCollection",features:fire.hotspots.map((h)=>({type:"Feature",geometry:{type:"Point",coordinates:[h.longitude,h.latitude]},properties:h}))};map.addSource("firms",{type:"geojson",data:geo});map.addLayer({id:"firms-glow",type:"circle",source:"firms",paint:{"circle-radius":["interpolate",["linear"],["get","frp_mw"],0,7,20,20],"circle-color":"#ff513b","circle-opacity":.45,"circle-blur":.55}});map.addLayer({id:"firms-core",type:"circle",source:"firms",paint:{"circle-radius":4,"circle-color":"#fff2a4","circle-stroke-color":"#ff5a32","circle-stroke-width":2}})}});animateRiskParticles(fire.hotspots||[]);text("fire-mode",fire.mode);text("fire-count",fire.hotspot_count);text("fire-interpretation",fire.interpretation);const metrics=$("risk-metrics");if(metrics)metrics.innerHTML=[["Wind erosion",pct(risk.wind_erosion_mean)],["Runoff",pct(risk.runoff_mean)],["Infiltration",pct(risk.infiltration_mean)],["Fire exposure",pct(risk.fire_exposure_mean)],["Combined",pct(risk.combined_risk_mean)]].map(([a,b])=>`<div><small>${a}</small><strong>${b}</strong></div>`).join("");const al=$("risk-alerts");if(al)al.innerHTML=renderAlerts(alerts);const interp=$("risk-interpretation");if(interp)interp.innerHTML=evidenceHtml([{title:"Combined attention",body:`The current combined screening score averages ${pct(risk.combined_risk_mean)} across the analysis grid.`},{title:"Thermal evidence",body:fire.interpretation},{title:"Limitation",body:risk.limitations}]);}

async function initScenarios(){const data=await fetchJson("/api/scenarios");const scenarios=data.scenarios||[];let step=0,playing=false,timer;const chart=$("scenario-chart");function draw(){text("scenario-step",`Step ${step}`);drawLineChart(chart,scenarios.map((s)=>({name:s.name,values:s.series.slice(0,step+1).map((p)=>Number(p.vegetation))})),{height:360,min:0,max:1,labels:scenarios[0]?.series.slice(0,step+1).map((p)=>p.step)||[]});}draw();const cards=$("scenario-cards");if(cards)cards.innerHTML=scenarios.map((s)=>`<article class="scenario-card"><h4>${escapeHtml(s.name)}</h4><p>Vegetation ${number(s.outcome.vegetation_change*100,1," pp")} • Desert ${number(s.outcome.desert_change*100,1," pp")}</p><small>Scenario assumptions: aridity ${s.parameters.aridity}, rainfall ${s.parameters.rainfall}, restoration ${s.parameters.restoration}.</small></article>`).join("");$("scenario-play")?.addEventListener("click",()=>{playing=!playing;$("scenario-play").textContent=playing?"Ⅱ Pause":"▶ Animate";clearInterval(timer);if(playing)timer=setInterval(()=>{step=(step+1)%61;draw()},180)});}

async function initField(){const map=createMap("field-map",{pitch:20,zoom:7.3});map.once("administrativeready",()=>fitNorth(map,35));async function load(){const records=await fetchJson("/api/field/observations");text("field-count",`${records.length} records`);const table=$("field-records");if(table)table.innerHTML=records.length?records.map((r)=>`<div class="record-row"><span>#${r.id}</span><div><b>${escapeHtml(r.observation_type)}</b><small>${escapeHtml(r.lga||"")} • ${escapeHtml(r.observer)}</small></div><span class="status-chip">${escapeHtml(r.status)}</span><span>${r.survival_percent==null?"—":`${r.survival_percent}%`}</span></div>`).join(""):"<p>No field records yet.</p>";const geo=toPointGeo(records);const addRecords=()=>{if(map.getSource("field-records"))map.getSource("field-records").setData(geo);else{map.addSource("field-records",{type:"geojson",data:geo});map.addLayer({id:"field-points",type:"circle",source:"field-records",paint:{"circle-radius":6,"circle-color":["match",["get","status"],"verified","#4ce5a7","rejected","#ef5a55","#e7b45a"],"circle-stroke-color":"#031319","circle-stroke-width":2}})}};if(map.loaded())addRecords();else map.once("administrativeready",addRecords)}await load();$("admin-login-form")?.addEventListener("submit",async(e)=>{e.preventDefault();try{await login($("admin-password").value);text("admin-status","Administrator session active.");showToast("Administrator login successful") }catch(err){text("admin-status","Authentication failed.");showToast("Authentication failed")}});$("field-form")?.addEventListener("submit",async(e)=>{e.preventDefault();try{await adminFetch("/api/field/observations",{method:"POST",body:JSON.stringify({observer:$("field-observer").value,latitude:Number($("field-lat").value),longitude:Number($("field-lon").value),lga:$("field-lga").value||null,observation_type:$("field-type").value,tree_count:$("field-trees").value?Number($("field-trees").value):null,survival_percent:$("field-survival").value?Number($("field-survival").value):null,species:$("field-species").value||null,notes:$("field-notes").value||null,metadata:{source:"field-page"}})});e.target.reset();await load();showToast("Field observation stored") }catch(err){showToast(`Unable to submit: ${err.message}`)}});}

function toPointGeo(records){return{type:"FeatureCollection",features:records.map((r)=>({type:"Feature",geometry:{type:"Point",coordinates:[r.longitude,r.latitude]},properties:{status:r.status,type:r.observation_type}}))}}

async function initProjects(){async function load(){const projects=await fetchJson("/api/projects");text("project-count",`${projects.length} projects`);const list=$("project-list");if(list)list.innerHTML=projects.length?projects.map((p)=>{const target=Number(p.target_trees||0),planted=Number(p.planted_trees||0),progress=target?Math.min(100,planted/target*100):0;const latest=p.inspections?.[0];return`<article class="project-card"><h4>${escapeHtml(p.name)}</h4><p>${escapeHtml(p.lga||"Gombe")} • ${escapeHtml(p.status)}</p><div class="progress"><i style="width:${progress}%"></i></div><small>${planted.toLocaleString()} / ${target.toLocaleString()} trees${latest?` • latest survival ${latest.survival_percent??"—"}%`:""}</small></article>`}).join(""):"<p>No restoration projects registered.</p>"}await load();$("project-login-form")?.addEventListener("submit",async(e)=>{e.preventDefault();try{await login($("project-password").value);text("project-admin-status","Administrator session active") }catch{ text("project-admin-status","Authentication failed") }});$("project-form")?.addEventListener("submit",async(e)=>{e.preventDefault();try{await adminFetch("/api/projects",{method:"POST",body:JSON.stringify({name:$("project-name").value,organisation:$("project-org").value||null,lga:$("project-lga").value||null,status:$("project-status").value,target_trees:$("project-target").value?Number($("project-target").value):null,planted_trees:$("project-planted").value?Number($("project-planted").value):null,species:$("project-species").value||null,notes:$("project-notes").value||null,geometry:{}})});e.target.reset();await load();showToast("Project registered") }catch(err){showToast(`Unable to create project: ${err.message}`)}});}

async function initPredictions(){const [status,forecast]=await Promise.all([fetchJson("/api/predictions/status"),fetchJson("/api/predictions/forecast?months=12")]);text("prediction-mode",forecast.training_mode||"not trained");const stat=$("prediction-status");if(stat)stat.innerHTML=[["Trained",status.trained?"Yes":"No"],["Samples",status.model?.samples??0],["Target",status.model?.target||"Next-month NDVI"],["Minimum samples",status.minimum_samples]].map(([a,b])=>`<div><small>${a}</small><strong>${b}</strong></div>`).join("");renderPrediction(forecast);$("prediction-login")?.addEventListener("submit",async(e)=>{e.preventDefault();try{await login($("prediction-password").value);text("prediction-admin-message","Administrator session active.") }catch{ text("prediction-admin-message","Authentication failed.") }});$("retrain-model")?.addEventListener("click",async()=>{try{text("prediction-admin-message","Training…");const model=await adminFetch("/api/admin/predictions/retrain",{method:"POST"});text("prediction-admin-message",`Model trained with ${model.samples} samples.`);renderPrediction(await fetchJson("/api/predictions/forecast?months=12"))}catch(err){text("prediction-admin-message",`Training failed: ${err.message}`)}});$("backfill-temporal")?.addEventListener("click",async()=>{try{text("prediction-admin-message","Requesting 12 Sentinel monthly mosaics. This can take several minutes…");const result=await adminFetch("/api/admin/temporal/backfill",{method:"POST",body:JSON.stringify({months:12})});text("prediction-admin-message",`Backfill complete: ${result.successful}/${result.requested_months} months.`)}catch(err){text("prediction-admin-message",`Backfill failed: ${err.message}`)}});}

function renderPrediction(data){if(!data.available){text("prediction-limitations",data.reason);return}const p=data.predictions||[];drawLineChart($("prediction-chart"),[{name:"Predicted NDVI",values:p.map((x)=>Number(x.ndvi))},{name:"Lower",values:p.map((x)=>Number(x.lower))},{name:"Upper",values:p.map((x)=>Number(x.upper))}],{height:280,min:-.1,max:.9,labels:p.map((x)=>x.period)});const m=$("prediction-metrics");if(m)m.innerHTML=[["MAE",number(data.metrics?.mae,3)],["RMSE",number(data.metrics?.rmse,3)],["R²",number(data.metrics?.r2,3)],["Training mode",data.training_mode]].map(([a,b])=>`<div><small>${a}</small><strong>${b}</strong></div>`).join("");const imp=data.feature_importance||[];drawBars($("prediction-importance"),imp.map((x)=>x.importance*100),imp.map((x)=>x.feature),{height:220,max:100});const l=$("prediction-limitations");if(l)l.innerHTML=evidenceHtml([{title:"Interpretation",body:"The band around the prediction expands with forecast horizon and validation error."},{title:"Limitation",body:data.limitations}]);}

async function initCompare(){const [temporal,land]=await Promise.all([fetchJson("/api/temporal"),fetchJson("/api/landcover")]);const ndviMap=createMap("compare-ndvi",{pitch:25});const lcMap=createMap("compare-landcover",{pitch:25});ndviMap.once("administrativeready",()=>{fitNorth(ndviMap,25);addImageOverlay(ndviMap,"compare-ndvi-layer","/api/ndvi/texture.png",.78)});lcMap.once("administrativeready",()=>{fitNorth(lcMap,25);addImageOverlay(lcMap,"compare-lc-layer","/api/landcover/texture.png",.78)});ndviMap.on("move",()=>{if(!lcMap._syncing){lcMap._syncing=true;lcMap.jumpTo({center:ndviMap.getCenter(),zoom:ndviMap.getZoom(),bearing:ndviMap.getBearing(),pitch:ndviMap.getPitch()});lcMap._syncing=false}});const canvas=$("compare-ground");animateGround(canvas);const points=temporal.points||[];const slider=$("compare-time");slider.max=Math.max(0,points.length-1);slider.value=slider.max;function select(){const p=points[Number(slider.value)];text("compare-period",p?.period||"—");const explanation=$("compare-explanation");if(explanation)explanation.innerHTML=evidenceHtml([{title:"Observed greenness",body:`The selected timeline point has NDVI ${p?.ndvi??"—"}.`},{title:"Classified cover",body:`Current dominant cover is ${land.dominant_class}; classification mode is ${land.mode}.`},{title:"Ground simulation",body:"The immersive panel visualises model state, not a photograph of the selected location."}])}slider.addEventListener("input",select);select();}

function animateGround(canvas){if(!canvas)return;const ctx=canvas.getContext("2d");let t=0;function resize(){canvas.width=canvas.clientWidth;canvas.height=canvas.clientHeight}function frame(){const w=canvas.width,h=canvas.height;const sky=ctx.createLinearGradient(0,0,0,h*.55);sky.addColorStop(0,"#163c5b");sky.addColorStop(1,"#9db7a6");ctx.fillStyle=sky;ctx.fillRect(0,0,w,h*.55);const ground=ctx.createLinearGradient(0,h*.5,0,h);ground.addColorStop(0,"#6a7540");ground.addColorStop(1,"#574022");ctx.fillStyle=ground;ctx.fillRect(0,h*.5,w,h*.5);for(let i=0;i<70;i++){const x=(i*97)%w,y=h*.55+(i%13)/13*h*.38;const sway=Math.sin(t*.02+i)*3;ctx.strokeStyle="#594528";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+sway,y-25-(i%4)*8);ctx.stroke();ctx.fillStyle=i%5?"#2f7a42":"#79933f";ctx.beginPath();ctx.arc(x+sway,y-28-(i%4)*8,6+(i%3)*2,0,Math.PI*2);ctx.fill()}for(let i=0;i<8;i++){const x=(i*180+t*.35)%(w+220)-110;ctx.fillStyle="rgba(240,250,247,.35)";ctx.beginPath();ctx.ellipse(x,70+(i%3)*28,70,20,0,0,Math.PI*2);ctx.fill()}t+=1;requestAnimationFrame(frame)}resize();window.addEventListener("resize",resize);frame();}

function initLiveSocket(){new LiveSocket((frame)=>{latestFrame=frame;updateLiveTime(frame.generated_at)},updateConnection)}

setActiveNav();startAmbient();initLiveSocket();
const initialisers={services:initServices,timeline:initTimeline,drought:initDrought,landcover:initLandcover,radar:initRadar,restoration:initRestoration,ecosystems:initEcosystems,risks:initRisks,scenarios:initScenarios,field:initField,projects:initProjects,predictions:initPredictions,compare:initCompare};
(initialisers[page]||(()=>Promise.resolve()))().catch((error)=>{console.error(error);showToast(`Unable to load ${page}: ${error.message}`)});
