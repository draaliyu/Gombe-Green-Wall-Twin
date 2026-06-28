export class LiveSky {
  constructor(shell, options = {}) {
    this.shell = typeof shell === "string" ? document.getElementById(shell) : shell;
    this.canvas = document.createElement("canvas");
    this.canvas.className = options.className || "live-sky-canvas";
    this.canvas.setAttribute("aria-hidden", "true");
    this.shell?.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d", { alpha: true });
    this.weather = null;
    this.layers = { celestial: true, clouds: true, wind: true, rain: true };
    this.running = true;
    this.phase = 0;
    this.stars = Array.from({ length: 110 }, (_, index) => ({
      x: ((index * 73) % 997) / 997,
      y: ((index * 193) % 991) / 991 * 0.62,
      r: 0.5 + ((index * 17) % 12) / 10,
      p: ((index * 31) % 100) / 100 * Math.PI * 2,
    }));
    this.clouds = Array.from({ length: 18 }, (_, index) => ({
      x: ((index * 137) % 1000) / 1000,
      y: 0.06 + ((index * 71) % 330) / 1000,
      s: 0.55 + ((index * 29) % 70) / 100,
      p: ((index * 43) % 100) / 100 * Math.PI * 2,
    }));
    this.rain = Array.from({ length: 130 }, (_, index) => ({
      x: ((index * 97) % 1000) / 1000,
      y: ((index * 223) % 1000) / 1000,
      l: 8 + ((index * 37) % 22),
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
    const dpr = Math.min(window.devicePixelRatio || 1, window.innerWidth < 760 ? 1.1 : 1.5);
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
    this.phase += 0.012;
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
    ctx.clearRect(0, 0, w, h);

    if (this.layers.celestial && !isDay) {
      const night = ctx.createLinearGradient(0, 0, 0, h);
      night.addColorStop(0, "rgba(2,8,25,.60)");
      night.addColorStop(0.55, "rgba(3,14,23,.28)");
      night.addColorStop(1, "rgba(1,8,13,.12)");
      ctx.fillStyle = night;
      ctx.fillRect(0, 0, w, h);
      ctx.save();
      ctx.globalCompositeOperation = "screen";
      this.stars.forEach((star) => {
        const alpha = (0.3 + 0.55 * (0.5 + 0.5 * Math.sin(this.phase * 2.4 + star.p))) * (1 - clouds / 130);
        ctx.fillStyle = `rgba(225,241,255,${alpha})`;
        ctx.beginPath();
        ctx.arc(star.x * w, star.y * h, star.r, 0, Math.PI * 2);
        ctx.fill();
      });
      const now = Date.now();
      const sunsetMs = new Date(weather.sunset || now - 1).getTime();
      const sunriseMs = new Date(weather.sunrise || now + 1).getTime();
      const nightElapsed = now > sunsetMs ? now - sunsetMs : Math.max(0, now + 86400000 - sunsetMs);
      const nightDuration = Math.max(1, sunriseMs + (sunriseMs < sunsetMs ? 86400000 : 0) - sunsetMs);
      const nightProgress = Math.max(0, Math.min(1, nightElapsed / nightDuration));
      const moonX = w * (0.14 + nightProgress * 0.72);
      const moonY = h * (0.28 - Math.sin(nightProgress * Math.PI) * 0.18);
      const moonR = Math.max(16, Math.min(34, w * 0.025));
      const glow = ctx.createRadialGradient(moonX, moonY, 0, moonX, moonY, moonR * 3.1);
      glow.addColorStop(0, "rgba(240,248,255,.95)");
      glow.addColorStop(0.3, "rgba(198,226,255,.32)");
      glow.addColorStop(1, "rgba(160,210,255,0)");
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(moonX, moonY, moonR * 3.1, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(244,248,238,.90)";
      ctx.beginPath(); ctx.arc(moonX, moonY, moonR, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    } else if (this.layers.celestial) {
      const now = Date.now();
      const sunriseMs = new Date(weather.sunrise || now - 1).getTime();
      const sunsetMs = new Date(weather.sunset || now + 1).getTime();
      const daylightProgress = Math.max(0, Math.min(1, (now - sunriseMs) / Math.max(1, sunsetMs - sunriseMs)));
      const sunX = w * (0.14 + daylightProgress * 0.72);
      const sunY = h * (0.30 - Math.sin(daylightProgress * Math.PI) * 0.20);
      const sunR = Math.max(20, Math.min(42, w * 0.03));
      const glow = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, sunR * 4.4);
      glow.addColorStop(0, "rgba(255,250,205,.96)");
      glow.addColorStop(0.18, "rgba(255,205,87,.48)");
      glow.addColorStop(1, "rgba(255,176,57,0)");
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(sunX, sunY, sunR * 4.4, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(255,238,157,.88)";
      ctx.beginPath(); ctx.arc(sunX, sunY, sunR, 0, Math.PI * 2); ctx.fill();
    }

    const cloudCount = this.layers.clouds ? Math.max(1, Math.round(this.clouds.length * clouds / 100)) : 0;
    ctx.save();
    ctx.globalCompositeOperation = isDay ? "source-over" : "screen";
    for (let index = 0; index < cloudCount; index += 1) {
      const cloud = this.clouds[index];
      const speed = 0.003 + wind * 0.00042;
      const x = ((cloud.x + this.phase * speed * Math.cos(direction)) % 1.35 + 1.35) % 1.35 - 0.15;
      const y = cloud.y + Math.sin(this.phase * 0.4 + cloud.p) * 0.025;
      this.drawCloud(x * w, y * h, 70 * cloud.s, isDay ? 0.12 + clouds / 600 : 0.10 + clouds / 850);
    }
    ctx.restore();

    if (this.layers.wind) this.drawWind(wind, direction);
    if (this.layers.rain && (rain > 0 || Number(weather.weather_code) >= 200 && Number(weather.weather_code) < 600)) this.drawRain(rain, wind, direction);

    if (weather.visibility_km != null && Number(weather.visibility_km) < 8) {
      ctx.fillStyle = `rgba(204,181,132,${Math.min(0.16, (8 - Number(weather.visibility_km)) * 0.022)})`;
      ctx.fillRect(0, 0, w, h);
    }
  }

  drawCloud(x, y, size, alpha) {
    const ctx = this.ctx;
    const gradient = ctx.createRadialGradient(x, y, size * 0.1, x, y, size);
    gradient.addColorStop(0, `rgba(245,249,244,${alpha * 1.4})`);
    gradient.addColorStop(0.55, `rgba(207,220,214,${alpha})`);
    gradient.addColorStop(1, "rgba(189,205,200,0)");
    ctx.fillStyle = gradient;
    [[0, 0, 1], [-0.45, 0.14, 0.70], [0.42, 0.12, 0.78], [-0.08, -0.28, 0.72]].forEach(([ox, oy, scale]) => {
      ctx.beginPath();
      ctx.ellipse(x + ox * size, y + oy * size, size * scale, size * 0.48 * scale, 0, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  drawWind(wind, direction) {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const count = Math.min(28, 8 + Math.round(wind * 2));
    ctx.save();
    ctx.globalCompositeOperation = "screen";
    ctx.lineWidth = 1.1;
    for (let i = 0; i < count; i += 1) {
      const baseX = ((i * 83 + this.phase * (22 + wind * 5)) % (w + 180)) - 90;
      const baseY = 55 + ((i * 61) % Math.max(100, h - 110));
      const length = 45 + wind * 12 + (i % 4) * 10;
      const dx = Math.sin(direction) * length;
      const dy = -Math.cos(direction) * length;
      ctx.strokeStyle = `rgba(124,255,222,${0.08 + Math.min(0.24, wind / 40)})`;
      ctx.beginPath();
      ctx.moveTo(baseX, baseY);
      ctx.quadraticCurveTo(baseX + dx * 0.5 + Math.sin(this.phase + i) * 10, baseY + dy * 0.5, baseX + dx, baseY + dy);
      ctx.stroke();
    }
    ctx.restore();
  }

  drawRain(rain, wind, direction) {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const count = Math.min(this.rain.length, 25 + Math.round(rain * 35));
    const drift = Math.sin(direction) * (6 + wind * 1.8);
    ctx.save();
    ctx.strokeStyle = `rgba(100,185,255,${Math.min(0.62, 0.22 + rain * 0.08)})`;
    ctx.lineWidth = 1.2;
    for (let i = 0; i < count; i += 1) {
      const drop = this.rain[i];
      const y = ((drop.y * h + this.phase * (260 + rain * 55)) % (h + 40)) - 20;
      const x = ((drop.x * w + this.phase * drift * 8) % (w + 30)) - 15;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + drift, y + drop.l);
      ctx.stroke();
    }
    ctx.restore();
  }
}
