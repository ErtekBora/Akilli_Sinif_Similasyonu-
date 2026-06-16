/* ── CONFIG ─────────────────────────────────────────────────────────── */
const API_BASE      = "http://localhost:8000";
const CLASSROOMS    = ["B-201", "B-202", "B-203"];
let   activeClassroom = "B-201";   // aktif sekme
const POLL_INTERVAL = 5000;
const MAX_POINTS    = 40;
const latestTimestamps = {};

/* ── CLASSROOM SCHEDULES (for timeline) ──────────────────────────── */
const SCHEDULES = {
  "B-201": [[8,10],[11,13],[14,16]],
  "B-202": [[9,11],[13,15]],
  "B-203": [[8,9],[10,12],[15,17]],
};
const TIMELINE_START = 8;
const TIMELINE_END   = 17;

/* ── CHART.JS DEFAULTS ───────────────────────────────────────────────── */
Chart.defaults.color       = "#5a7a96";
Chart.defaults.borderColor = "#1e2d3d";
Chart.defaults.font.family = "'Space Mono', monospace";
Chart.defaults.font.size   = 10;

/* ── CHART FACTORY ───────────────────────────────────────────────────── */
function makeChart(canvasId, label, color, bandMin = null, bandMax = null) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [{ label, data: [], borderColor: color,
        backgroundColor: color + "18", borderWidth: 2,
        pointRadius: 2, pointHoverRadius: 5, tension: 0.3, fill: true }]
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#0d1318", borderColor: "#1e2d3d", borderWidth: 1 }
      },
      scales: {
        x: { grid: { color: "#111820" }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
        y: { grid: { color: "#111820" }, ticks: { maxTicksLimit: 5 },
             ...(bandMin !== null ? { suggestedMin: bandMin - 3, suggestedMax: bandMax + 3 } : {}) }
      }
    }
  });
}

const charts = {
  energy: makeChart("chartEnergy", "Güç (W)",       "#00e5a0"),
  lux:    makeChart("chartLux",    "Işık (lx)",     "#ffae00"),
  temp:   makeChart("chartTemp",   "Sıcaklık (°C)", "#38b4ff", 18, 26),
  co2:    makeChart("chartCo2",    "CO₂ (ppm)",     "#ff3d5a"),
};

/* ── RADAR CHART ───────────────────────────────────────────────────── */
const radarChart = new Chart(
  document.getElementById("radarChart").getContext("2d"), {
  type: "radar",
  data: {
    labels: ["Enerji Verimliliği", "Isil Konfor", "Hava Kalitesi"],
    datasets: [{
      label: "En İyi Senaryo",
      data: [0, 0, 0],
      backgroundColor: "rgba(0,229,160,0.12)",
      borderColor: "#00e5a0",
      pointBackgroundColor: "#00e5a0",
      pointRadius: 4,
      borderWidth: 2,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: true,
    plugins: { legend: { display: false } },
    scales: {
      r: {
        min: 0, max: 1,
        ticks: { stepSize: 0.25, color: "#3d6080", backdropColor: "transparent", font: { size: 9 } },
        grid: { color: "#1e2d3d" },
        angleLines: { color: "#1e2d3d" },
        pointLabels: { color: "#5a7a96", font: { size: 10, family: "'Barlow Condensed', sans-serif" } },
      }
    }
  }
});

function updateRadar(rows) {
  if (!rows || !rows.length) return;
  const best = rows.find(r => r.is_optimal) || rows[0];
  // xi1=energy (lower=better, invert), xi2=light, xi3=temp
  radarChart.data.datasets[0].data = [
    parseFloat(best.energy_coeff_xi1.toFixed(3)),
    parseFloat(best.temp_coeff_xi3.toFixed(3)),
    parseFloat(best.light_coeff_xi2.toFixed(3)),
  ];
  radarChart.update();
}

/* ── SINIF SEKMESİ DEĞİŞTİRME ───────────────────────────────────────── */
function switchClassroom(id) {
  activeClassroom = id;

  // Sekme stillerini güncelle
  CLASSROOMS.forEach(cls => {
    const tab = document.getElementById("tab-" + cls);
    if (tab) tab.classList.toggle("active", cls === id);
  });

  // Başlık etiketini güncelle
  const lbl = document.getElementById("activeClsLabel");
  if (lbl) lbl.textContent = id;

  // Grafikleri sıfırla
  Object.values(charts).forEach(c => {
    c.data.labels = [];
    c.data.datasets[0].data = [];
    c.update("none");
  });

  // Yeni sınıfın verisini hemen çek
  fetchHistory();
  fetchSummary();
  fetchScenarios();
  fetchLatest();
}

/* ── UTILS ───────────────────────────────────────────────────────────── */
function formatTime(isoStr) {
  // Z ekini kaldır — simülasyon saatini yerel saat olarak göster
  const clean = isoStr.replace('Z', '');
  const d = new Date(clean);
  return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function pushToChart(chart, label, value) {
  chart.data.labels.push(label);
  chart.data.datasets[0].data.push(value);
  if (chart.data.labels.length > MAX_POINTS) {
    chart.data.labels.shift();
    chart.data.datasets[0].data.shift();
  }
  chart.update("none");
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setKpiCard(cardId, statusClass) {
  const el = document.getElementById(cardId);
  if (!el) return;
  el.classList.remove("ok", "warn", "bad");
  if (statusClass) el.classList.add(statusClass);
}

function setConstraint(suffix, ok) {
  const item  = document.getElementById("c-" + suffix);
  const badge = document.getElementById("b-" + suffix);
  if (!item || !badge) return;
  item.classList.remove("ok", "bad");
  item.classList.add(ok ? "ok" : "bad");
  badge.textContent = ok ? "SAĞLANDI ✓" : "İHLAL ✗";
}

function setLiveStatus(state) {
  const dot   = document.getElementById("pulseDot");
  const label = document.getElementById("liveLabel");
  dot.classList.remove("live", "error");
  if (state === "live")       { dot.classList.add("live");  label.textContent = "CANLI"; }
  if (state === "error")      { dot.classList.add("error"); label.textContent = "BAĞLANTI YOK"; }
  if (state === "connecting") { label.textContent = "BAĞLANIYOR"; }
}

/* ── FETCH: ANLK VERİ ────────────────────────────────────────────────── */
async function fetchLatest() {
  try {
    const res = await fetch(`${API_BASE}/api/data/latest?classroom_id=${activeClassroom}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const d = await res.json();
    const isNewSample = latestTimestamps[activeClassroom] !== d.timestamp;
    latestTimestamps[activeClassroom] = d.timestamp;

    setLiveStatus("live");
    setText("lastUpdate", formatTime(d.timestamp));

    const energy = d.total_energy_w;
    setText("kpiEnergy", energy.toFixed(0));
    setKpiCard("card-energy", "ok");

    const temp = d.temperature_indoor;
    setText("kpiTemp", temp.toFixed(1));
    const tempTolerance = d.temp_tolerance_c ?? 0.5;
    const tempOk = temp >= (20 + tempTolerance) && temp <= (24 - tempTolerance);
    setKpiCard("card-temp", tempOk ? "ok" : "bad");
    const rawTemp = d.temperature_raw ?? temp;
    const humidity = d.humidity_percent;
    setText(
      "kpiTempSub",
      `Ham: ${rawTemp.toFixed(1)} °C · ±${tempTolerance.toFixed(1)} °C` +
        (humidity != null ? ` · Nem: %${humidity.toFixed(1)}` : "")
    );
    if (d.capture_interval_ms) {
      setText("captureInterval", `${(d.capture_interval_ms / 1000).toFixed(0)} sn`);
    }

    setText("kpiLux", d.total_light_lux.toFixed(0));
    setKpiCard("card-lux", d.lighting_ok ? "ok" : "bad");

    const co2 = d.co2_ppm;
    setText("kpiCo2", co2);
    setKpiCard("card-co2", co2 <= 800 ? "ok" : co2 <= 1000 ? "warn" : "bad");

    const occEl = document.getElementById("kpiOccupancy");
    occEl.textContent = d.occupancy_u === 1 ? "DOLU" : "BOŞ";
    occEl.style.color = d.occupancy_u === 1 ? "var(--accent)" : "var(--text-dim)";

    setConstraint("lighting", d.lighting_ok);
    setConstraint("thermal",  d.thermal_ok);
    setConstraint("co2",      d.co2_ok);
    setConstraint("capacity", d.capacity_ok);

    renderLights(d.lights || [], d.ac_power_w);

    if (isNewSample) {
      const t = formatTime(d.timestamp);
      pushToChart(charts.energy, t, energy);
      pushToChart(charts.lux,    t, d.total_light_lux);
      pushToChart(charts.temp,   t, temp);
      pushToChart(charts.co2,    t, co2);
    }

  } catch (err) {
    setLiveStatus("error");
    console.warn("fetchLatest:", err.message);
  }
}

/* ── RENDER LIGHTS + HVAC ───────────────────────────────────────── */
function renderLights(lights, acPowerW) {
  const grid = document.getElementById("lightsGrid");
  if (!lights.length && !acPowerW) {
    grid.innerHTML = '<div class="no-data">Lamba verisi yok</div>';
    return;
  }

  const lampCards = lights.map(l => `
    <div class="light-card">
      <div class="light-id">${l.light_id}</div>
      <div class="light-bar-track">
        <div class="light-bar-fill" style="width:${(l.power_level_x * 100).toFixed(0)}%"></div>
      </div>
      <div class="light-stats">
        <div class="light-stat">Seviye (x)<span>${(l.power_level_x * 100).toFixed(0)}%</span></div>
        <div class="light-stat">Güç<span>${l.actual_power_w.toFixed(1)} W</span></div>
        <div class="light-stat">İşık<span>${l.contributed_lux.toFixed(0)} lx</span></div>
      </div>
    </div>
  `).join("");

  // HVAC card — AC load% = P_ac / 900 (max AC watts in simulator)
  const acLoad   = acPowerW != null ? Math.min(100, (acPowerW / 900) * 100) : 0;
  const acActive = acPowerW > 0;
  const hvacCard = `
    <div class="hvac-card">
      <div class="hvac-id">HVAC — Klima</div>
      <div class="hvac-label">Kompresör Yükü</div>
      <div class="hvac-bar-track">
        <div class="hvac-bar-fill" style="width:${acLoad.toFixed(0)}%"></div>
      </div>
      <div class="hvac-stats">
        <div class="hvac-stat">Yük<span>${acLoad.toFixed(0)}%</span></div>
        <div class="hvac-stat">Güç<span>${acPowerW != null ? acPowerW.toFixed(0) : '—'} W</span></div>
        <div class="hvac-stat">Durum<span style="color:${acActive ? 'var(--accent)' : 'var(--text-dim)'}">${acActive ? 'AKTİF' : 'PASIF'}</span></div>
      </div>
    </div>
  `;

  grid.innerHTML = lampCards + hvacCard;
}

/* ── FETCH: KPI ÖZET ─────────────────────────────────────────────────── */
async function fetchSummary() {
  try {
    const res = await fetch(`${API_BASE}/api/summary/?classroom_id=${activeClassroom}`);
    if (!res.ok) return;
    const d = await res.json();
    setText("kpiEnergyAvg", d.avg_energy_w != null ? d.avg_energy_w.toFixed(0) : "—");
    setText("kpiGrd",       d.best_grd_score != null ? d.best_grd_score.toFixed(3) : "—");
    setText("kpiScenario",  d.best_scenario_id ?? "—");
    setKpiCard("card-grd",  d.best_grd_score ? "ok" : null);
  } catch (err) {
    console.warn("fetchSummary:", err.message);
  }
}

/* ── FETCH: GRA TABLOSU ──────────────────────────────────────────────── */
async function fetchScenarios() {
  try {
    const res = await fetch(`${API_BASE}/api/scenarios/?classroom_id=${activeClassroom}`);
    if (!res.ok) return;
    const rows = await res.json();
    const tbody = document.getElementById("graBody");
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="no-data">Optimizasyon verisi bekleniyor…</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr class="${r.is_optimal ? 'optimal' : ''}">
        <td>${r.scenario_id}</td>
        <td>${r.energy_coeff_xi1.toFixed(3)}</td>
        <td>${r.light_coeff_xi2.toFixed(3)}</td>
        <td>${r.temp_coeff_xi3.toFixed(3)}</td>
        <td><span class="grd-score">${r.grd_score_G.toFixed(3)}</span></td>
        <td>${r.is_optimal ? '<span class="optimal-badge">EN İYİ</span>' : "—"}</td>
      </tr>
    `).join("");
    updateRadar(rows);
  } catch (err) {
    console.warn("fetchScenarios:", err.message);
  }
}

/* ── FETCH: GEÇMİŞ VERİ ─────────────────────────────────────────────── */
async function fetchHistory() {
  try {
    const res = await fetch(`${API_BASE}/api/data/history?classroom_id=${activeClassroom}&limit=${MAX_POINTS}`);
    if (!res.ok) return;
    const rows = await res.json();
    latestTimestamps[activeClassroom] = rows.length ? rows[0].timestamp : undefined;
    [...rows].reverse().forEach(d => {
      const t = formatTime(d.timestamp);
      pushToChart(charts.energy, t, d.total_energy_w);
      pushToChart(charts.lux,    t, d.total_light_lux);
      pushToChart(charts.temp,   t, d.temperature_indoor);
      pushToChart(charts.co2,    t, d.co2_ppm);
    });
  } catch (err) {
    console.warn("fetchHistory:", err.message);
  }
}

/* ── SCHEDULE TIMELINE ─────────────────────────────────────────────── */
function renderTimeline() {
  const container = document.getElementById("scheduleTimeline");
  const axis      = document.getElementById("timelineAxis");
  const totalHours = TIMELINE_END - TIMELINE_START;

  container.innerHTML = CLASSROOMS.map(cls => {
    const schedule = SCHEDULES[cls];
    const hours = Array.from({length: totalHours}, (_, i) => {
      const h = TIMELINE_START + i;
      const occupied = schedule.some(([s, e]) => h >= s && h < e);
      return `<div class="timeline-hour${occupied ? ' occupied' : ''}" title="${h}:00–${h+1}:00 — ${occupied ? 'DOLU' : 'BOŞ'}"></div>`;
    }).join("");
    return `
      <div class="timeline-row">
        <div class="timeline-label">${cls}</div>
        <div class="timeline-track">${hours}</div>
      </div>`;
  }).join("");

  // Axis labels
  axis.innerHTML = Array.from({length: totalHours + 1}, (_, i) =>
    `<div class="timeline-axis-label">${TIMELINE_START + i}:00</div>`
  ).join("");
}

/* ── BAŞLATMA ───────────────────────────────────────────────────────── */
async function init() {
  setLiveStatus("connecting");
  renderTimeline();           // static — draw immediately
  await fetchHistory();
  await fetchSummary();
  await fetchScenarios();
  await fetchLatest();

  setInterval(fetchLatest,    POLL_INTERVAL);
  setInterval(fetchSummary,   POLL_INTERVAL * 3);
  setInterval(fetchScenarios, POLL_INTERVAL * 4);
}

document.addEventListener("DOMContentLoaded", init);
