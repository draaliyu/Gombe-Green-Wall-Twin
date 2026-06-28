export class LiveSky {
  constructor(shell, options = {}) {
    this.shell = typeof shell === "string" ? document.getElementById(shell) : shell;
    this.canvas = document.createElement("canvas");
    this.canvas.className = options.className || "live-sky-canvas";
    this.canvas.setAttribute("aria-hidden", "true");
    this.shell?.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d", { alpha: true, desynchronized: true });
    this.weather = null;
    this.layers = { celestial: true, clouds: true, wind: true, rain: true, haze: true };
    this.running = true;
    this.phase = 0;
    this.quality = window.innerWidth < 760 || navigator.connection?.saveData ? 0.55 : 1;
    this.stars = Array.from({ length: Math.round(190 * this.quality) }, (_, index) => ({
      x: ((index * 73) % 997) / 997,
      y: ((index * 193) % 991) / 991 * 0.72,
      r: 0.45 + ((index * 17) % 13) / 10,
      p: ((index * 31) % 100) / 100 * Math.PI * 2,
    }));
    this.clouds = Array.from({ length: Math.max(10, Math.round(30 * this.quality)) }, (_, index) => ({
      x: ((index * 137) % 1000) / 1000,
      y: 0.04 + ((index * 71) % 500) / 1000,
      s: 0.45 + ((index * 29) % 95) / 100,
      p: ((index * 43) % 100) / 100 * Math.PI * 2,
      depth: 0.35 + ((index * 53) % 65) / 100,
    }));
    this.rain = Array.from({ length: Math.max(80, Math.round(280 * this.quality)) }, (_, index) => ({
      x: ((index * 97) % 1000) / 1000,
      y: ((index * 223) % 1000) / 1000,
      l: 7 + ((index * 37) % 25),
    }));
    this.resizeObserver = new ResizeObserver(() => this.resize());
    if (this.shell) this.resizeObserver.observe(this.shell);
    document.addEventListener("visibilitychange", () => { this.running = !document.hidden; });
    this.resize();
    this.animate();
  }

  update(weather) { this.weather = weather || null; }

  setLayer(name, visible) {
    if (Object.prototype.hasOwnProperty.call(this.layers, name)) this.layers[name] = Boolean(visible);
  }

  resize() {
    if (!this.shell || !this.ctx) return;
    const rect = this.shell.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, window.innerWidth < 760 ? 1 : 1.45);
    this.canvas.width = Math.max(1, Math.round(rect.width * dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * dpr));
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.width = rect.width;
    this.height = rect.height;
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    if (!this.running || !this.ctx || !this.width || !this.weather) return;
    this.phase += 0.0105 * this.quality;
    this.draw();
  }

  draw() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const weather = this.weather;
    const isDay = Boolean(weather.is_daylight);
    const clouds = Math.max(0, Math.min(100, Number(weather.cloud_cover_percent) || 0));
    const rain = Math.max(0, Number(weather.rain_1h_mm) || 0);
    const wind = Math.max(0, Number(weather.wind_speed_mps) || 0);
    const direction = (Number(weather.wind_direction_deg) || 0) * Math.PI / 180;
    const visibility = weather.visibility_km == null ? 12 : Number(weather.visibility_km);
    ctx.clearRect(0, 0, w, h);

    if (this.layers.celestial) {
      if (!isDay) this.drawNight(ctx, w, h, weather, clouds);
      else this.drawDay(ctx, w, h, weather, clouds);
    }

    const cloudCount = this.layers.clouds ? Math.max(0, Math.round(this.clouds.length * clouds / 100)) : 0;
    ctx.save();
    ctx.globalCompositeOperation = isDay ? "screen" : "lighter";
    for (let index = 0; index < cloudCount; index += 1) {
      const cloud = this.clouds[index];
      const speed = 0.0022 + wind * 0.00038;
      const x = ((cloud.x + this.phase * speed * Math.sin(direction) * (0.7 + cloud.depth)) % 1.35 + 1.35) % 1.35 - 0.17;
      const y = cloud.y + Math.sin(this.phase * 0.45 + cloud.p) * 0.024;
      const size = (75 + cloud.depth * 75) * cloud.s;
      this.drawCloud(x * w, y * h, size, isDay ? 0.10 + clouds / 330 : 0.08 + clouds / 500, clouds, cloud.depth);
    }
    ctx.restore();

    if (this.layers.wind) this.drawWind(wind, direction);
    const rainyCode = Number(weather.weather_code) >= 200 && Number(weather.weather_code) < 600;
    if (this.layers.rain && (rain > 0 || rainyCode)) this.drawRain(rain, wind, direction);
    if (Number(weather.weather_code) >= 200 && Number(weather.weather_code) < 300 && Math.sin(this.phase * 10) > 0.991) {
      ctx.fillStyle = "rgba(225,242,255,.42)";
      ctx.fillRect(0, 0, w, h);
    }
    if (this.layers.haze && visibility < 9) {
      const alpha = Math.min(0.22, (9 - visibility) * 0.025);
      const haze = ctx.createLinearGradient(0, 0, 0, h);
      haze.addColorStop(0, `rgba(204,181,132,${alpha * 0.25})`);
      haze.addColorStop(1, `rgba(204,181,132,${alpha})`);
      ctx.fillStyle = haze;
      ctx.fillRect(0, 0, w, h);
    }
  }

  drawDay(ctx, w, h, weather, clouds) {
    const now = Date.now();
    const sunrise = new Date(weather.sunrise || now - 1).getTime();
    const sunset = new Date(weather.sunset || now + 1).getTime();
    const progress = Math.max(0, Math.min(1, (now - sunrise) / Math.max(1, sunset - sunrise)));
    const sunX = w * (0.11 + progress * 0.78);
    const sunY = h * (0.31 - Math.sin(progress * Math.PI) * 0.22);
    const sunR = Math.max(18, Math.min(42, w * 0.027));
    const glow = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, sunR * 5.1);
    glow.addColorStop(0, "rgba(255,252,217,.98)");
    glow.addColorStop(0.15, "rgba(255,209,98,.48)");
    glow.addColorStop(1, "rgba(255,176,57,0)");
    ctx.fillStyle = glow;
    ctx.beginPath(); ctx.arc(sunX, sunY, sunR * 5.1, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = `rgba(255,242,166,${Math.max(.35, 1 - clouds / 135)})`;
    ctx.beginPath(); ctx.arc(sunX, sunY, sunR, 0, Math.PI * 2); ctx.fill();
    const horizon = ctx.createLinearGradient(0, h * .55, 0, h);
    horizon.addColorStop(0, "rgba(255,197,96,0)");
    horizon.addColorStop(1, `rgba(255,190,96,${0.05 + (1 - clouds / 100) * .12})`);
    ctx.fillStyle = horizon; ctx.fillRect(0, h * .52, w, h * .48);
  }

  drawNight(ctx, w, h, weather, clouds) {
    const night = ctx.createLinearGradient(0, 0, 0, h);
    night.addColorStop(0, "rgba(2,7,28,.62)");
    night.addColorStop(0.55, "rgba(3,14,28,.30)");
    night.addColorStop(1, "rgba(1,8,13,.12)");
    ctx.fillStyle = night; ctx.fillRect(0, 0, w, h);
    ctx.save(); ctx.globalCompositeOperation = "screen";
    this.stars.forEach((star) => {
      const alpha = (0.24 + 0.68 * (0.5 + 0.5 * Math.sin(this.phase * 2.5 + star.p))) * (1 - clouds / 125);
      ctx.fillStyle = `rgba(225,241,255,${alpha})`;
      ctx.beginPath(); ctx.arc(star.x * w, star.y * h, star.r, 0, Math.PI * 2); ctx.fill();
    });
    const now = Date.now();
    const sunset = new Date(weather.sunset || now - 1).getTime();
    let sunrise = new Date(weather.sunrise || now + 1).getTime();
    if (sunrise < sunset) sunrise += 86400000;
    const adjustedNow = now < sunset ? now + 86400000 : now;
    const progress = Math.max(0, Math.min(1, (adjustedNow - sunset) / Math.max(1, sunrise - sunset)));
    const moonX = w * (0.12 + progress * 0.76);
    const moonY = h * (0.30 - Math.sin(progress * Math.PI) * 0.19);
    const moonR = Math.max(13, Math.min(31, w * 0.024));
    const glow = ctx.createRadialGradient(moonX, moonY, 0, moonX, moonY, moonR * 4);
    glow.addColorStop(0, "rgba(240,248,255,.96)"); glow.addColorStop(.3, "rgba(161,207,255,.29)"); glow.addColorStop(1, "rgba(160,210,255,0)");
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(moonX, moonY, moonR * 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = `rgba(244,248,238,${Math.max(.3, 1 - clouds / 120)})`;
    ctx.beginPath(); ctx.arc(moonX, moonY, moonR, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  drawCloud(x, y, size, alpha, cover, depth) {
    const ctx = this.ctx;
    const dark = Math.min(.72, cover / 140 + depth * .08);
    const gradient = ctx.createRadialGradient(x, y, size * 0.08, x, y, size);
    gradient.addColorStop(0, `rgba(${244 - dark * 65},${248 - dark * 58},${244 - dark * 52},${alpha * 1.45})`);
    gradient.addColorStop(0.58, `rgba(${193 - dark * 42},${210 - dark * 39},${207 - dark * 35},${alpha})`);
    gradient.addColorStop(1, "rgba(159,180,180,0)");
    ctx.fillStyle = gradient;
    [[0,0,1],[-.43,.14,.68],[.42,.12,.78],[-.08,-.27,.72],[.1,.27,.62]].forEach(([ox, oy, scale]) => {
      ctx.beginPath(); ctx.ellipse(x + ox * size, y + oy * size, size * scale, size * .47 * scale, 0, 0, Math.PI * 2); ctx.fill();
    });
  }

  drawWind(wind, direction) {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const count = Math.min(Math.round(32 * this.quality), 7 + Math.round(wind * 2.4));
    ctx.save(); ctx.globalCompositeOperation = "screen";
    for (let index = 0; index < count; index += 1) {
      const progress = ((this.phase * (.7 + wind * .09) + index * .083) % 1.25) - .12;
      const baseX = progress * w;
      const baseY = 45 + ((index * 67) % Math.max(100, h - 90));
      const length = 45 + wind * 13 + (index % 4) * 10;
      const dx = Math.sin(direction) * length + length * .58;
      const dy = -Math.cos(direction) * length * .52;
      const gradient = ctx.createLinearGradient(baseX, baseY, baseX + dx, baseY + dy);
      gradient.addColorStop(0, "rgba(66,160,255,0)"); gradient.addColorStop(.55, "rgba(86,210,244,.18)"); gradient.addColorStop(1, "rgba(85,255,197,.38)");
      ctx.strokeStyle = gradient; ctx.lineWidth = 1 + (index % 3) * .25;
      ctx.beginPath(); ctx.moveTo(baseX, baseY); ctx.quadraticCurveTo(baseX + dx * .5, baseY + dy * .5 + Math.sin(this.phase + index) * 13, baseX + dx, baseY + dy); ctx.stroke();
    }
    ctx.restore();
  }

  drawRain(rain, wind, direction) {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const count = Math.min(this.rain.length, 25 + Math.round(rain * 45));
    const drift = Math.sin(direction) * (5 + wind * 1.9);
    ctx.save(); ctx.strokeStyle = `rgba(104,185,255,${Math.min(.72, .22 + rain * .11)})`; ctx.lineWidth = 1.1;
    for (let index = 0; index < count; index += 1) {
      const drop = this.rain[index];
      const y = ((drop.y * h + this.phase * (280 + rain * 70)) % (h + 40)) - 20;
      const x = ((drop.x * w + this.phase * drift * 8) % (w + 30)) - 15;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + drift, y + drop.l); ctx.stroke();
    }
    ctx.restore();
  }
}
