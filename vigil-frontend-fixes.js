// ============================================================
// VIGIL FRONTEND - BACKEND INTEGRATION FIXES
// ============================================================
// Replace the relevant functions in your HTML with these fixed versions

const API = "http://127.0.0.1:8000";

// ============================================================
// DATA LOADING FUNCTIONS - FIXED FOR ACTUAL BACKEND
// ============================================================

async function loadVehicles() {
  try {
    const res = await fetch(`${API}/vehicles`);
    const data = await res.json();

    vehiclesData = data; // Store for filtering
    const tbody = document.getElementById("vehicle-tbody");
    if (!tbody) return;

    tbody.innerHTML = data
      .map(
        (v) => `
          <tr>
            <td><span class="plate-tag">${v.plate}</span></td>
            <td style="color:var(--text)">${v.owner || 'N/A'}</td>
            <td style="color:var(--text2)">${v.phone || 'N/A'}</td>
            <td><span class="status-badge status-ok">${v.type || 'Guest'}</span></td>
            <td><span class="speed-val ${v.total_violations > 3 ? 'over' : 'ok'}">${v.total_violations || 0}</span></td>
            <td style="color:var(--text3);font-size:11px">${v.last_seen || 'Never'}</td>
            <td><button class="alert-btn warn" style="font-size:10px" onclick="showToast('Vehicle Details','${v.plate} · ${v.owner || 'Unknown'}','info')">View</button></td>
          </tr>`
      )
      .join("");
    
    document.getElementById("vehicle-count-badge").textContent = `${data.length} vehicles`;
  } catch (error) {
    console.error("Error loading vehicles:", error);
    showToast("Error", "Failed to load vehicles", "info");
  }
}

async function loadEvents() {
  try {
    const res = await fetch(`${API}/events`);
    const data = await res.json();

    const tbody = document.getElementById("live-tbody");
    if (!tbody) return;

    // Get only the most recent 15 events for the live feed
    const recentEvents = data.slice(0, 15);

    tbody.innerHTML = recentEvents
      .map((e) => {
        const isViolation = e.status === "VIOLATION";
        const zoneMap = { 1: "A", 2: "B", 3: "C" };
        const zoneName = zoneMap[e.zone_id] || `Zone ${e.zone_id}`;
        
        return `
          <tr class="${isViolation ? 'violation' : ''}">
            <td><span class="plate-tag">${e.plate}</span></td>
            <td><span class="speed-val ${isViolation ? 'over' : 'ok'}">${e.speed || 0} km/h</span></td>
            <td style="color:var(--text2)">${zoneName}</td>
            <td style="color:var(--text3)">${e.event_time || ''}</td>
            <td><span class="status-badge ${isViolation ? 'status-viol' : 'status-ok'}">${isViolation ? '⚠ VIOLATION' : '✓ OK'}</span></td>
          </tr>`;
      })
      .join("");
  } catch (error) {
    console.error("Error loading events:", error);
  }
}

async function loadNotifications() {
  try {
    const res = await fetch(`${API}/notifications`);
    const data = await res.json();

    const container = document.getElementById("notif-list");
    if (!container) return;

    notificationsData = data.map(n => ({
      type: n.type || 'sys',
      title: n.message || 'System Notification',
      detail: `${n.plate || 'Unknown'} · ${n.owner || ''} ${n.phone ? '· ' + n.phone : ''}`,
      time: n.sent_time || '',
      status: n.delivery_status?.toLowerCase() || 'delivered'
    }));

    renderNotifications('all');
    
    // Update badge counts
    const failed = notificationsData.filter(n => n.status === 'failed').length;
    const notifBadge = document.getElementById("notif-badge");
    const bellCount = document.getElementById("bell-count");
    
    if (notifBadge) {
      notifBadge.textContent = failed || "";
      notifBadge.style.display = failed ? "" : "none";
    }
    if (bellCount) {
      bellCount.textContent = failed || data.length;
    }
  } catch (error) {
    console.error("Error loading notifications:", error);
  }
}

function renderNotifications(filter = "all") {
  const el = document.getElementById("notif-list");
  if (!el || !notificationsData) return;
  
  const filtered = filter === "all" 
    ? notificationsData 
    : notificationsData.filter((n) => n.type === filter);
    
  el.innerHTML = filtered
    .map((n) => {
      const isViolation = n.title && n.title.toLowerCase().includes('violation');
      
      return `
        <div class="notif-card ${isViolation ? 'viol' : ''}">
          <div class="notif-icon">
            ${n.type === 'sms' ? '📱' : n.type === 'email' ? '📧' : isViolation ? '🚨' : 'ℹ️'}
          </div>
          <div class="notif-content">
            <div class="notif-title">${n.title}</div>
            <div class="notif-sub">${n.detail}</div>
            <div class="notif-footer">
              <span class="notif-time">${n.time}</span>
              <span class="status ${n.status}">
                ${n.status === 'delivered' ? '✓ Delivered' : 
                  n.status === 'pending' ? '⏳ Pending' : '✗ Failed'}
              </span>
            </div>
          </div>
        </div>`;
    })
    .join("");
}

async function loadStats() {
  try {
    const res = await fetch(`${API}/stats`);
    const data = await res.json();

    const statTotal = document.getElementById("stat-total");
    const statViolations = document.getElementById("stat-violations");
    
    if (statTotal) statTotal.textContent = data.vehicles || 0;
    if (statViolations) statViolations.textContent = data.violations || 0;
  } catch (error) {
    console.error("Error loading stats:", error);
  }
}

async function loadZones() {
  try {
    const res = await fetch(`${API}/zones`);
    const data = await res.json();

    const container = document.getElementById("zone-list");
    if (!container) return;

    container.innerHTML = data
      .map((z) => {
        const riskColor = z.risk_level === 'HIGH' ? 'var(--red)' : 
                         z.risk_level === 'MEDIUM' ? 'var(--accent)' : 'var(--green)';
        
        return `
          <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:5px;margin-bottom:4px;background:var(--bg3);cursor:pointer" 
               onmouseover="this.style.background='var(--panel2)'" 
               onmouseout="this.style.background='var(--bg3)'">
            <div style="width:8px;height:8px;border-radius:50%;background:${riskColor}"></div>
            <div style="flex:1;font-family:var(--mono);font-size:11px;color:var(--text2)">${z.name}</div>
            <div style="font-family:var(--mono);font-size:10px;color:var(--text3)">${z.speed_limit}km/h</div>
            <div style="font-family:var(--mono);font-size:10px;color:${riskColor}">${z.accident_count || 0}⚠</div>
          </div>`;
      })
      .join("");

    // Also update the zone limits mini display
    renderZoneLimitsMini(data);
  } catch (error) {
    console.error("Error loading zones:", error);
  }
}

function renderZoneLimitsMini(zones) {
  const el = document.getElementById("zone-limits-mini");
  if (!el || !zones) return;
  
  el.innerHTML = zones.slice(0, 4)
    .map((z) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--border)">
        <span style="font-family:var(--mono);font-size:11px;color:var(--text2)">${z.name}</span>
        <span style="font-family:var(--mono);font-size:12px;color:var(--accent)">${z.speed_limit} km/h</span>
      </div>`)
    .join("");
}

async function loadLogs() {
  try {
    const res = await fetch(`${API}/events?limit=100`);
    const data = await res.json();

    logsData = data.map(e => ({
      time: new Date(e.event_time),
      plate: e.plate,
      speed: e.speed,
      zone: e.zone_id,
      camera: e.camera_id || 'CAM-00',
      violation: e.status === 'VIOLATION'
    }));

    const container = document.getElementById("log-entries");
    if (!container) return;

    document.getElementById("log-count").textContent = `${data.length} events`;

    container.innerHTML = logsData
      .map((l) => `
        <div class="log-entry ${l.violation ? 'critical' : ''}">
          <div class="log-time">${l.time.toLocaleTimeString('en-IN', { hour12: false }).slice(0, 8)}</div>
          <div class="log-plate">${l.plate}</div>
          <div class="log-speed speed-val ${l.violation ? 'over' : 'ok'}">${l.speed} km/h</div>
          <div class="log-location">${l.zone}</div>
          <div style="font-family:var(--mono);font-size:11px;color:var(--text3);min-width:70px">${l.camera}</div>
          <div class="log-type">
            <span class="status-badge ${l.violation ? 'status-viol' : 'status-ok'}">
              ${l.violation ? 'VIOLATION' : 'NORMAL'}
            </span>
          </div>
        </div>`)
      .join("");
  } catch (error) {
    console.error("Error loading logs:", error);
  }
}

async function loadMapFromBackend() {
  try {
    const res = await fetch(`${API}/zones`);
    const zones = await res.json();

    // Initialize Leaflet map
    const map = L.map("campus-map").setView([26.187, 91.691], 15);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    // Map zone names to approximate IIT Guwahati locations
    const zoneLocations = {
      'A': [26.1875, 91.6905],
      'B': [26.1902, 91.6938],
      'C': [26.184, 91.697]
    };

    zones.forEach((z) => {
      const loc = zoneLocations[z.name] || [26.187 + Math.random() * 0.02, 91.691 + Math.random() * 0.02];
      const color = z.risk_level === 'HIGH' ? 'red' : z.risk_level === 'MEDIUM' ? 'orange' : 'green';
      
      L.circleMarker(loc, {
        radius: 8,
        fillColor: color,
        color: '#000',
        weight: 1,
        opacity: 1,
        fillOpacity: 0.6
      })
        .addTo(map)
        .bindPopup(`<b>Zone ${z.name}</b><br>Limit: ${z.speed_limit} km/h<br>Risk: ${z.risk_level}`);
    });
  } catch (error) {
    console.error("Error loading map:", error);
  }
}

async function loadTopOffenders() {
  try {
    const res = await fetch(`${API}/vehicles`);
    const data = await res.json();

    const top = data
      .filter(v => v.total_violations > 0)
      .sort((a, b) => b.total_violations - a.total_violations)
      .slice(0, 7);

    const container = document.getElementById("top-offenders");
    if (!container) return;

    container.innerHTML = top
      .map((v, i) => `
        <div class="offender-row">
          <div class="offender-rank">#${i + 1}</div>
          <div class="offender-plate">${v.plate}</div>
          <div style="flex:1;font-family:var(--body);font-size:12px;color:var(--text3)">${v.owner || 'Unknown'}</div>
          <div class="offender-bar">
            <div class="offender-bar-fill" style="width:${Math.min(100, (v.total_violations / 8) * 100)}%"></div>
          </div>
          <div class="offender-count">${v.total_violations}×</div>
        </div>`)
      .join("");
  } catch (error) {
    console.error("Error loading top offenders:", error);
  }
}

async function loadCharts() {
  try {
    const res = await fetch(`${API}/events`);
    const data = await res.json();

    const speeds = data.map((e) => e.speed || 0);

    // ===== MONTHLY VIOLATIONS CHART
    const ctx = document.getElementById("chart-monthly");
    if (ctx) {
      const gradient = ctx.getContext("2d").createLinearGradient(0, 0, 0, 300);
      gradient.addColorStop(0, "rgba(56,189,248,0.5)");
      gradient.addColorStop(1, "rgba(56,189,248,0)");

      new Chart(ctx, {
        type: "line",
        data: {
          labels: data.slice(0, 30).map((_, i) => `Day ${i + 1}`),
          datasets: [{
            label: "Speed",
            data: speeds.slice(0, 30),
            borderColor: "#38bdf8",
            backgroundColor: gradient,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: "#94a3b8" } } },
          scales: {
            x: { ticks: { color: "#64748b", maxTicksLimit: 10 } },
            y: { ticks: { color: "#64748b" } },
          },
        },
      });
    }

    // ===== SPEED DISTRIBUTION CHART
    const chartDist = document.getElementById("chart-dist");
    if (chartDist) {
      new Chart(chartDist, {
        type: "bar",
        data: {
          labels: ["0-20", "20-40", "40+"],
          datasets: [{
            label: "Vehicles",
            data: [
              speeds.filter((s) => s < 20).length,
              speeds.filter((s) => s >= 20 && s < 40).length,
              speeds.filter((s) => s >= 40).length,
            ],
            backgroundColor: ["#10b981", "#f59e0b", "#ef4444"],
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: "#94a3b8" } } },
          scales: {
            x: { ticks: { color: "#64748b" } },
            y: { ticks: { color: "#64748b" } },
          },
        },
      });
    }

    // ===== PEAK HOURS CHART
    const chartHours = document.getElementById("chart-hours");
    if (chartHours) {
      // Group violations by hour
      const hourCounts = new Array(24).fill(0);
      data.forEach(e => {
        if (e.status === 'VIOLATION' && e.event_time) {
          const hour = new Date(e.event_time).getHours();
          hourCounts[hour]++;
        }
      });

      new Chart(chartHours, {
        type: "bar",
        data: {
          labels: Array.from({ length: 24 }, (_, i) => `${i}:00`),
          datasets: [{
            label: "Violations",
            data: hourCounts,
            backgroundColor: "#3b82f6",
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: "#94a3b8" } } },
          scales: {
            x: { ticks: { color: "#64748b", maxTicksLimit: 8 } },
            y: { ticks: { color: "#64748b" } },
          },
        },
      });
    }
  } catch (error) {
    console.error("Error loading charts:", error);
  }
}

async function loadHeatmap() {
  try {
    const res = await fetch(`${API}/events`);
    const data = await res.json();

    const container = document.getElementById("heatmap-grid-container");
    if (!container) return;

    const violations = data.filter(e => e.status === 'VIOLATION').length;
    
    container.innerHTML = `
      <div style="font-family:var(--mono);font-size:12px;color:var(--text2);margin-bottom:10px">
        Total Events: ${data.length} | Violations: ${violations} | Compliance: ${Math.round((1 - violations/data.length) * 100)}%
      </div>`;
  } catch (error) {
    console.error("Error loading heatmap:", error);
  }
}

// ============================================================
// INITIALIZATION - UPDATED
// ============================================================

function init() {
  console.log("VIGIL Dashboard Initializing...");

  // Load all data from backend
  loadVehicles();
  loadEvents();
  loadNotifications();
  loadStats();
  loadZones();
  loadLogs();
  
  // Build live feed (will be updated periodically)
  buildLiveFeed();
  
  // Seed some alerts for demo
  for (let i = 0; i < 3; i++) {
    alertsData.push({
      plate: PLATES[i % PLATES.length],
      speed: 45 + Math.floor(Math.random() * 20),
      limit: 35,
      zone: "Zone A",
      time: new Date(Date.now() - i * 120000),
    });
  }
  
  renderLiveTable();
  renderAlerts();
  renderSettings();
  
  // Initialize dashboard charts
  setTimeout(() => initDashboardCharts(), 100);
  
  // Periodic updates
  setInterval(updateLive, 5000); // Reload events every 5 seconds
  setInterval(loadStats, 10000); // Update stats every 10 seconds
  setInterval(loadNotifications, 15000); // Update notifications every 15 seconds
  
  // Initial toast
  setTimeout(() => showToast("System Online", "Connected to backend API", "info"), 1200);
}

// Modified updateLive to reload from backend
function updateLive() {
  loadEvents(); // Reload events from backend
  loadStats(); // Update stats
}

console.log("Vigil Frontend Fixes Loaded ✅");
