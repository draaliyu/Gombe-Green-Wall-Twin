function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, Number(value) || 0));
}

function sizeCanvas(canvas, maxDpr = 1.5) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, maxDpr);
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { context, width: rect.width, height: rect.height, dpr };
}

function valueRange(values) {
  const numeric = values.filter(Number.isFinite);
  if (!numeric.length) return [0, 1];
  let minimum = Math.min(...numeric);
  let maximum = Math.max(...numeric);
  if (minimum === maximum) {
    minimum -= 1;
    maximum += 1;
  }
  const padding = (maximum - minimum) * 0.12;
  return [minimum - padding, maximum + padding];
}

export function drawLineChart(canvas, series, options = {}) {
  if (!canvas) return;
  const { context: ctx, width, height } = sizeCanvas(canvas, window.innerWidth < 760 ? 1 : 1.4);
  ctx.clearRect(0, 0, width, height);
  const padding = { left: 28, right: 12, top: 12, bottom: 20 };
  const allValues = series.flatMap((item) => item.values || []);
  const [minimum, maximum] = options.range || valueRange(allValues);
  const plotWidth = Math.max(1, width - padding.left - padding.right);
  const plotHeight = Math.max(1, height - padding.top - padding.bottom);
  ctx.strokeStyle = "rgba(132, 175, 168, .14)";
  ctx.lineWidth = 1;
  for (let index = 0; index < 4; index += 1) {
    const y = padding.top + plotHeight * index / 3;
    ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(width - padding.right, y); ctx.stroke();
  }
  series.forEach((item) => {
    const values = item.values || [];
    if (values.length < 2) return;
    ctx.strokeStyle = item.color || "#38e58d";
    ctx.lineWidth = item.width || 1.8;
    ctx.beginPath();
    values.forEach((value, index) => {
      const x = padding.left + plotWidth * index / Math.max(1, values.length - 1);
      const y = padding.top + plotHeight * (1 - (value - minimum) / Math.max(0.0001, maximum - minimum));
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
    if (item.fill) {
      const lastX = padding.left + plotWidth;
      ctx.lineTo(lastX, height - padding.bottom);
      ctx.lineTo(padding.left, height - padding.bottom);
      ctx.closePath();
      const gradient = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
      gradient.addColorStop(0, item.fill);
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = gradient;
      ctx.fill();
    }
  });
  ctx.fillStyle = "rgba(183, 207, 201, .72)";
  ctx.font = "8px system-ui";
  ctx.fillText(maximum.toFixed(options.decimals ?? 0), 3, padding.top + 3);
  ctx.fillText(minimum.toFixed(options.decimals ?? 0), 3, height - padding.bottom + 2);
  const labels = options.labels || [];
  if (labels.length) {
    ctx.textAlign = "center";
    const step = Math.max(1, Math.ceil(labels.length / 5));
    labels.forEach((label, index) => {
      if (index % step !== 0 && index !== labels.length - 1) return;
      const x = padding.left + plotWidth * index / Math.max(1, labels.length - 1);
      ctx.fillText(label, x, height - 5);
    });
    ctx.textAlign = "left";
  }
}

export function drawBarChart(canvas, values, options = {}) {
  if (!canvas) return;
  const { context: ctx, width, height } = sizeCanvas(canvas, window.innerWidth < 760 ? 1 : 1.4);
  ctx.clearRect(0, 0, width, height);
  const padding = { left: 26, right: 10, top: 10, bottom: 20 };
  const maximum = Math.max(1, ...values.map((item) => Number(item.value) || 0));
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const gap = 4;
  const barWidth = Math.max(2, plotWidth / Math.max(1, values.length) - gap);
  ctx.strokeStyle = "rgba(132,175,168,.13)";
  for (let index = 0; index < 4; index += 1) {
    const y = padding.top + plotHeight * index / 3;
    ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(width - padding.right, y); ctx.stroke();
  }
  values.forEach((item, index) => {
    const barHeight = plotHeight * (Number(item.value) || 0) / maximum;
    const x = padding.left + index * (barWidth + gap);
    const y = padding.top + plotHeight - barHeight;
    const gradient = ctx.createLinearGradient(0, y, 0, padding.top + plotHeight);
    gradient.addColorStop(0, item.color || options.color || "#36e3d3");
    gradient.addColorStop(1, "rgba(38,112,118,.45)");
    ctx.fillStyle = gradient;
    ctx.fillRect(x, y, barWidth, barHeight);
  });
  ctx.fillStyle = "rgba(183,207,201,.72)";
  ctx.font = "8px system-ui";
  ctx.fillText(maximum.toFixed(options.decimals ?? 1), 2, padding.top + 4);
  const step = Math.max(1, Math.ceil(values.length / 6));
  ctx.textAlign = "center";
  values.forEach((item, index) => {
    if (index % step !== 0 && index !== values.length - 1) return;
    const x = padding.left + index * (barWidth + gap) + barWidth / 2;
    ctx.fillText(item.label || "", x, height - 5);
  });
  ctx.textAlign = "left";
}

export function drawDonut(canvas, values) {
  if (!canvas) return;
  const { context: ctx, width, height } = sizeCanvas(canvas, 1.5);
  ctx.clearRect(0, 0, width, height);
  const total = Math.max(0.0001, values.reduce((sum, item) => sum + Math.max(0, Number(item.value) || 0), 0));
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.36;
  ctx.lineWidth = Math.max(9, radius * 0.26);
  ctx.lineCap = "butt";
  let angle = -Math.PI / 2;
  values.forEach((item) => {
    const next = angle + Math.PI * 2 * Math.max(0, Number(item.value) || 0) / total;
    ctx.strokeStyle = item.color;
    ctx.beginPath(); ctx.arc(cx, cy, radius, angle, next); ctx.stroke();
    angle = next;
  });
  ctx.strokeStyle = "rgba(190,230,218,.12)";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(cx, cy, radius + ctx.lineWidth * 7, 0, Math.PI * 2); ctx.stroke();
}

export class AtmosphereCanvas {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.circular = Boolean(options.circular);
    this.weather = null;
    this.phase = 0;
    this.running = true;
    this.quality = options.quality || (window.innerWidth < 760 ? 0.55 : 1);
    this.stars = Array.from({ length: Math.round(140 * this.quality) }, (_, index) => ({
      x: ((index * 71) % 997) / 997,
      y: ((index * 191) % 991) / 991,
      r: .45 + ((index * 19) % 11) / 10,
      p: ((index * 29) % 100) / 100 * Math.PI * 2,
    }));
    this.clouds = Array.from({ length: Math.max(8, Math.round(24 * this.quality)) }, (_, index) => ({
      x: ((index * 137) % 1000) / 1000,
      y: .12 + ((index * 67) % 500) / 1000,
      s: .55 + ((index * 31) % 85) / 100,
      p: index * .83,
    }));
    this.rain = Array.from({ length: Math.max(50, Math.round(210 * this.quality)) }, (_, index) => ({
      x: ((index * 97) % 1000) / 1000,
      y: ((index * 223) % 1000) / 1000,
      l: 7 + ((index * 37) % 18),
    }));
    this.resizeObserver = new ResizeObserver(() => this.draw());
    this.resizeObserver.observe(canvas);
    document.addEventListener("visibilitychange", () => { this.running = !document.hidden; });
    this.loop();
  }

  update(weather) { this.weather = weather; }

  loop() {
    requestAnimationFrame(() => this.loop());
    if (!this.running || !this.weather) return;
    this.phase += .011 * this.quality;
    this.draw();
  }

  draw() {
    if (!this.weather) return;
    const { context: ctx, width, height } = sizeCanvas(this.canvas, window.innerWidth < 760 ? 1 : 1.35);
    if (width < 2 || height < 2) return;
    ctx.clearRect(0, 0, width, height);
    const weather = this.weather;
    const isDay = Boolean(weather.is_daylight);
    const cloudCover = clamp(weather.cloud_cover_percent, 0, 100);
    const rain = Math.max(0, Number(weather.rain_1h_mm) || 0);
    const direction = (Number(weather.wind_direction_deg) || 0) * Math.PI / 180;
    const wind = Math.max(.2, Number(weather.wind_speed_mps) || 0);
    const sky = ctx.createLinearGradient(0, 0, 0, height);
    if (isDay) {
      sky.addColorStop(0, cloudCover > 65 ? "#506c78" : "#397fc2");
      sky.addColorStop(.58, cloudCover > 65 ? "#9aa4a0" : "#78b7e6");
      sky.addColorStop(1, "#d8bf86");
    } else {
      sky.addColorStop(0, "#010718"); sky.addColorStop(.62, "#071a31"); sky.addColorStop(1, "#244048");
    }
    ctx.fillStyle = sky; ctx.fillRect(0, 0, width, height);
    if (!isDay) {
      ctx.save(); ctx.globalCompositeOperation = "screen";
      this.stars.forEach((star) => {
        const alpha = (.25 + .75 * (.5 + .5 * Math.sin(this.phase * 2.4 + star.p))) * (1 - cloudCover / 125);
        ctx.fillStyle = `rgba(229,244,255,${alpha})`;
        ctx.beginPath(); ctx.arc(star.x * width, star.y * height * .76, star.r, 0, Math.PI * 2); ctx.fill();
      });
      ctx.restore();
    }
    const now = Date.now();
    const start = new Date(isDay ? weather.sunrise : weather.sunset).getTime();
    const endRaw = new Date(isDay ? weather.sunset : weather.sunrise).getTime();
    const end = endRaw <= start ? endRaw + 86400000 : endRaw;
    const adjustedNow = now < start ? now + 86400000 : now;
    const progress = clamp((adjustedNow - start) / Math.max(1, end - start), 0, 1);
    const celestialX = width * (.12 + progress * .76);
    const celestialY = height * (.38 - Math.sin(progress * Math.PI) * .27);
    const radius = Math.max(10, Math.min(30, width * .055));
    const glow = ctx.createRadialGradient(celestialX, celestialY, 0, celestialX, celestialY, radius * 4);
    glow.addColorStop(0, isDay ? "rgba(255,251,206,.98)" : "rgba(239,248,255,.96)");
    glow.addColorStop(.26, isDay ? "rgba(255,195,68,.44)" : "rgba(156,202,255,.27)");
    glow.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(celestialX, celestialY, radius * 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = isDay ? "#fff2a7" : "#f0f2e4"; ctx.beginPath(); ctx.arc(celestialX, celestialY, radius, 0, Math.PI * 2); ctx.fill();

    const count = Math.max(1, Math.round(this.clouds.length * cloudCover / 100));
    for (let index = 0; index < count; index += 1) {
      const cloud = this.clouds[index];
      const dx = Math.sin(direction) * this.phase * (.45 + wind * .08);
      const x = ((cloud.x + dx) % 1.35 + 1.35) % 1.35 - .18;
      const y = cloud.y + Math.sin(this.phase * .7 + cloud.p) * .03;
      this.drawCloud(ctx, x * width, y * height, 42 * cloud.s * (this.circular ? .75 : 1.15), isDay ? .48 : .30, cloudCover);
    }
    if (rain > 0 || (Number(weather.weather_code) >= 200 && Number(weather.weather_code) < 600)) {
      ctx.strokeStyle = `rgba(130,205,255,${clamp(.25 + rain * .09, .25, .78)})`;
      ctx.lineWidth = 1.1;
      const drops = Math.min(this.rain.length, 35 + Math.round(rain * 32));
      const drift = Math.sin(direction) * (4 + wind * 1.4);
      for (let index = 0; index < drops; index += 1) {
        const item = this.rain[index];
        const y = ((item.y * height + this.phase * (230 + rain * 60)) % (height + 30)) - 15;
        const x = ((item.x * width + this.phase * drift * 5) % (width + 30)) - 15;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + drift, y + item.l); ctx.stroke();
      }
    }
    if (Number(weather.weather_code) >= 200 && Number(weather.weather_code) < 300 && Math.sin(this.phase * 8) > .985) {
      ctx.fillStyle = "rgba(235,246,255,.55)"; ctx.fillRect(0, 0, width, height);
    }
    const visibility = weather.visibility_km == null ? 12 : Number(weather.visibility_km);
    if (visibility < 8) {
      ctx.fillStyle = `rgba(207,178,121,${clamp((8 - visibility) * .028, 0, .25)})`; ctx.fillRect(0, 0, width, height);
    }
  }

  drawCloud(ctx, x, y, size, alpha, cover) {
    const darkness = clamp(cover / 130, .12, .75);
    const gradient = ctx.createRadialGradient(x, y, size * .05, x, y, size * 1.2);
    gradient.addColorStop(0, `rgba(${230 - darkness * 65},${238 - darkness * 62},${235 - darkness * 55},${alpha})`);
    gradient.addColorStop(.56, `rgba(175,190,190,${alpha * .66})`);
    gradient.addColorStop(1, "rgba(130,150,155,0)");
    ctx.fillStyle = gradient;
    [[0,0,1],[-.42,.13,.68],[.4,.11,.76],[-.06,-.26,.71]].forEach(([ox, oy, scale]) => {
      ctx.beginPath(); ctx.ellipse(x + ox * size, y + oy * size, size * scale, size * .48 * scale, 0, 0, Math.PI * 2); ctx.fill();
    });
  }
}

export class WeatherFlowCanvas {
  constructor(canvas) {
    this.canvas = canvas;
    this.weather = null;
    this.forecast = [];
    this.running = true;
    this.phase = 0;
    this.cells = Array.from({ length: 32 }, (_, index) => ({
      x: ((index * 83) % 997) / 997,
      y: ((index * 173) % 991) / 991,
      p: index * .71,
      s: .45 + ((index * 31) % 70) / 100,
    }));
    document.addEventListener("visibilitychange", () => { this.running = !document.hidden; });
    this.loop();
  }
  update(weather, forecast) { this.weather = weather; this.forecast = forecast?.points || []; }
  setRunning(value) { this.running = value; }
  loop() { requestAnimationFrame(() => this.loop()); if (!this.running || !this.weather) return; this.phase += .012; this.draw(); }
  draw() {
    const { context: ctx, width, height } = sizeCanvas(this.canvas, window.innerWidth < 760 ? 1 : 1.35);
    ctx.clearRect(0, 0, width, height);
    const gradient = ctx.createLinearGradient(0, 0, width, height); gradient.addColorStop(0, "#061a2d"); gradient.addColorStop(1, "#08251f"); ctx.fillStyle = gradient; ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(100,174,180,.16)"; ctx.lineWidth = .7;
    for (let i = 0; i < 7; i += 1) { ctx.beginPath(); ctx.moveTo(0, height * (i + 1) / 8); ctx.bezierCurveTo(width * .32, height * (i + .2) / 8, width * .68, height * (i + 1.8) / 8, width, height * (i + 1) / 8); ctx.stroke(); }
    const direction = (Number(this.weather.wind_direction_deg) || 0) * Math.PI / 180;
    const speed = Math.max(.4, Number(this.weather.wind_speed_mps) || 0);
    const cloud = clamp(this.weather.cloud_cover_percent, 0, 100);
    const rain = Math.max(0, Number(this.weather.rain_1h_mm) || 0);
    const count = Math.max(3, Math.round(this.cells.length * Math.max(.12, cloud / 100)));
    ctx.globalCompositeOperation = "screen";
    for (let index = 0; index < count; index += 1) {
      const cell = this.cells[index];
      const x = ((cell.x + Math.sin(direction) * this.phase * (.02 + speed * .003)) % 1.25 + 1.25) % 1.25 - .12;
      const y = ((cell.y - Math.cos(direction) * this.phase * .006 + Math.sin(this.phase + cell.p) * .04) % 1.2 + 1.2) % 1.2 - .1;
      const radius = 15 + cell.s * 26;
      const radial = ctx.createRadialGradient(x * width, y * height, 0, x * width, y * height, radius);
      const wet = rain > 0 || (this.forecast[index]?.rain_3h_mm || 0) > 0;
      radial.addColorStop(0, wet ? "rgba(255,224,61,.82)" : "rgba(92,224,195,.55)");
      radial.addColorStop(.45, wet ? "rgba(74,222,119,.54)" : "rgba(56,150,212,.30)");
      radial.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = radial; ctx.beginPath(); ctx.arc(x * width, y * height, radius, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(236,249,244,.9)"; ctx.beginPath(); ctx.arc(width * .52, height * .58, 4, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = "#48a8ff"; ctx.lineWidth = 2; ctx.stroke();
  }
}

export class WindFlowCanvas {
  constructor(canvas) {
    this.canvas = canvas;
    this.weather = null;
    this.phase = 0;
    this.running = true;
    this.lines = Array.from({ length: window.innerWidth < 760 ? 22 : 44 }, (_, index) => ({ y: ((index * 79) % 997) / 997, p: index * .51 }));
    this.loop();
  }
  update(weather) { this.weather = weather; }
  loop() { requestAnimationFrame(() => this.loop()); if (!this.running || !this.weather || document.hidden) return; this.phase += .014; this.draw(); }
  draw() {
    const { context: ctx, width, height } = sizeCanvas(this.canvas, window.innerWidth < 760 ? 1 : 1.35);
    ctx.clearRect(0, 0, width, height);
    const background = ctx.createLinearGradient(0, 0, width, height); background.addColorStop(0, "#07162c"); background.addColorStop(1, "#092923"); ctx.fillStyle = background; ctx.fillRect(0, 0, width, height);
    const speed = Math.max(.4, Number(this.weather.wind_speed_mps) || 0);
    const angle = (Number(this.weather.wind_direction_deg) || 0) * Math.PI / 180;
    ctx.globalCompositeOperation = "screen";
    this.lines.forEach((line, index) => {
      const progress = ((this.phase * (.6 + speed * .08) + index * .071) % 1.25) - .12;
      const baseY = line.y * height;
      const startX = progress * width;
      const length = 45 + speed * 10;
      const dx = Math.sin(angle) * length + length;
      const dy = -Math.cos(angle) * length * .45;
      const gradient = ctx.createLinearGradient(startX, baseY, startX + dx, baseY + dy);
      gradient.addColorStop(0, "rgba(48,130,255,0)"); gradient.addColorStop(.5, "rgba(48,168,255,.62)"); gradient.addColorStop(1, "rgba(42,242,159,.9)");
      ctx.strokeStyle = gradient; ctx.lineWidth = 1 + (index % 3) * .3; ctx.beginPath(); ctx.moveTo(startX, baseY); ctx.bezierCurveTo(startX + dx * .35, baseY + Math.sin(this.phase + line.p) * 18, startX + dx * .72, baseY + dy * .65, startX + dx, baseY + dy); ctx.stroke();
    });
    ctx.globalCompositeOperation = "source-over";
  }
}
