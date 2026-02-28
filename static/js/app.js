const DEFAULT_COORD = { lat: 10.6769, lng: 122.9518 };
const NEGROS_BOUNDS = {
  south: 9.0,
  north: 10.95,
  west: 122.15,
  east: 123.55,
};

const map = L.map("map", {
  minZoom: 8,
  maxZoom: 19,
  maxBoundsViscosity: 1.0,
});

const mapBounds = L.latLngBounds(
  [NEGROS_BOUNDS.south, NEGROS_BOUNDS.west],
  [NEGROS_BOUNDS.north, NEGROS_BOUNDS.east]
);
map.fitBounds(mapBounds);
map.setMaxBounds(mapBounds.pad(0.15));

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const riskPointsLayer = L.layerGroup().addTo(map);
const riskRiversLayer = L.layerGroup();
const riskRoadsLayer = L.layerGroup();

let selectedPoint = { ...DEFAULT_COORD };
let selectedMarker = L.marker([selectedPoint.lat, selectedPoint.lng]).addTo(map);
let riskCircle = null;
let routeLine = null;
let centerMarkers = [];
let nearestCenters = [];

const hoursRange = document.getElementById("hoursRange");
const hoursValue = document.getElementById("hoursValue");
const riskOutput = document.getElementById("riskOutput");
const riskAreaOutput = document.getElementById("riskAreaOutput");
const evacOutput = document.getElementById("evacOutput");
const routeOutput = document.getElementById("routeOutput");
const routeMode = document.getElementById("routeMode");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");
const riskAreaBtn = document.getElementById("riskAreaBtn");
const riskAreaRivers = document.getElementById("toggleRivers");
const riskAreaRoads = document.getElementById("toggleFloodedRoads");

hoursRange.addEventListener("input", () => {
  hoursValue.textContent = hoursRange.value;
});

const pointRiskColor = (levelOrScore) => {
  if (typeof levelOrScore === "number") {
    if (levelOrScore >= 65) return "#c62828";
    if (levelOrScore >= 35) return "#ef6c00";
    return "#2e7d32";
  }

  if (levelOrScore === "HIGH") return "#c62828";
  if (levelOrScore === "MEDIUM") return "#ef6c00";
  return "#2e7d32";
};

const riverStyle = (feature) => {
  const level = feature?.properties?.risk_level || "LOW";
  if (level === "HIGH") return { color: "#c62828", weight: 4, opacity: 0.9 };
  if (level === "MEDIUM") return { color: "#f9a825", weight: 3.5, opacity: 0.85 };
  return { color: "#1e88e5", weight: 3, opacity: 0.8 };
};

const roadStyle = (feature) => {
  const level = feature?.properties?.risk_level || "LOW";
  if (level === "HIGH") return { color: "#d84315", weight: 5, opacity: 0.95 };
  if (level === "MEDIUM") return { color: "#f57c00", weight: 4, opacity: 0.85 };
  return { color: "#ef6c00", weight: 3, opacity: 0.7 };
};

const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "map-legend");
  div.innerHTML = `
    <h4>Risk Legend</h4>
    <div><span class="swatch low"></span> Low</div>
    <div><span class="swatch medium"></span> Medium</div>
    <div><span class="swatch high"></span> High</div>
    <div class="spacer"></div>
    <div><span class="swatch river"></span> River (highlight)</div>
    <div><span class="swatch road"></span> Road flood risk</div>
  `;
  return div;
};
legend.addTo(map);

map.on("click", async (event) => {
  selectedPoint = event.latlng;
  selectedMarker.setLatLng(event.latlng);
  await fetchRisk();
});

document.getElementById("riskBtn").addEventListener("click", fetchRisk);
document.getElementById("evacBtn").addEventListener("click", fetchEvacCenters);
document.getElementById("routeBtn").addEventListener("click", fetchRoute);
riskAreaBtn.addEventListener("click", fetchRiskArea);
riskAreaRivers.addEventListener("change", fetchRiskArea);
riskAreaRoads.addEventListener("change", fetchRiskArea);
chatForm.addEventListener("submit", submitChat);

async function fetchRisk() {
  const hours = Number(hoursRange.value);
  const url = `/api/risk/?lat=${selectedPoint.lat}&lng=${selectedPoint.lng}&hours=${hours}`;

  const response = await fetch(url);
  const data = await response.json();

  if (!response.ok) {
    riskOutput.textContent = data.error || "Risk lookup failed.";
    return;
  }

  riskOutput.innerHTML = [
    `<span class="risk-pill">${data.risk_level} • ${data.risk_score}</span>`,
    `Signals: ${data.explanation.join(", ")}`,
  ].join("<br/>");

  if (riskCircle) {
    map.removeLayer(riskCircle);
  }

  riskCircle = L.circle([selectedPoint.lat, selectedPoint.lng], {
    radius: 500,
    color: pointRiskColor(data.risk_level),
    fillColor: pointRiskColor(data.risk_level),
    fillOpacity: 0.2,
  }).addTo(map);
}

function clearRiskAreaLayers() {
  riskPointsLayer.clearLayers();
  riskRiversLayer.clearLayers();
  riskRoadsLayer.clearLayers();
}

function renderRiskArea(data) {
  const renderRivers = riskAreaRivers.checked;
  const renderRoads = riskAreaRoads.checked;
  const points = data.area_points || [];
  const rivers = data.rivers || { features: [] };
  const roads = data.roads || { features: [] };

  clearRiskAreaLayers();
  if (map.hasLayer(riskRiversLayer)) {
    map.removeLayer(riskRiversLayer);
  }
  if (map.hasLayer(riskRoadsLayer)) {
    map.removeLayer(riskRoadsLayer);
  }

  points.forEach((item) => {
    const marker = L.circleMarker([item.lat, item.lng], {
      radius: 7,
      color: pointRiskColor(item.risk_score),
      fillColor: pointRiskColor(item.risk_score),
      fillOpacity: 0.8,
      weight: 1,
    });
    marker.bindPopup(
      `Risk ${item.risk_level} (${item.risk_score})<br/>Impact in ${item.expected_peak_in_hours || "n/a"}h`
    );
    riskPointsLayer.addLayer(marker);
  });

  if (renderRivers && rivers.features && rivers.features.length > 0) {
    L.geoJSON(rivers, {
      style: riverStyle,
    }).addTo(riskRiversLayer);
    riskRiversLayer.addTo(map);
  }

  if (renderRoads && roads.features && roads.features.length > 0) {
    L.geoJSON(roads, {
      style: roadStyle,
    }).addTo(riskRoadsLayer);
    riskRoadsLayer.addTo(map);
  }

  if (!map.hasLayer(riskPointsLayer)) {
    map.addLayer(riskPointsLayer);
  }

  const warnings = data.meta?.warnings || [];
  const scanned = data.meta?.sampled_points ?? points.length;
  const shown = points.length;
  const riverCount = rivers.features ? rivers.features.length : 0;
  const roadCount = roads.features ? roads.features.length : 0;
  const warningText = warnings.length
    ? ` <br/>Warnings: ${warnings.join(" ")}`
    : "";

  riskAreaOutput.innerHTML = [
    `Scanned ${scanned} sample points (showing ${shown} at risk level threshold).`,
    `Risky rivers: ${riverCount}.`,
    `Floodable roads: ${roadCount}.`,
    `Runtime: ${data.meta?.runtime_ms}ms.`,
    `Source: ${data.meta?.source || "computed"}.${warningText}`,
  ].join("<br/>");
}

async function fetchRiskArea() {
  const hours = Number(hoursRange.value);
  const includeRivers = riskAreaRivers.checked ? "true" : "false";
  const includeRoads = riskAreaRoads.checked ? "true" : "false";
  const maxPoints = 140;

  const params = new URLSearchParams({
    hours: String(hours),
    severity: "high",
    max_points: String(maxPoints),
    include_rivers: includeRivers,
    include_roads: includeRoads,
  });

  riskAreaOutput.textContent = "Scanning Negros...";
  const response = await fetch(`/api/risk-area/?${params.toString()}`);
  const data = await response.json();

  if (!response.ok) {
    riskAreaOutput.textContent = data.error || "Risk area scan failed.";
    return;
  }

  renderRiskArea(data);
}

async function fetchEvacCenters() {
  clearCenterMarkers();
  const url = `/api/evac-centers/?lat=${selectedPoint.lat}&lng=${selectedPoint.lng}`;
  const response = await fetch(url);
  const data = await response.json();

  if (!response.ok) {
    evacOutput.textContent = data.error || "Could not load centers.";
    return;
  }

  nearestCenters = data.centers || [];
  if (!nearestCenters.length) {
    evacOutput.textContent = "No centers loaded. Run migrations to seed fixtures.";
    return;
  }

  nearestCenters.forEach((center) => {
    const marker = L.marker([center.latitude, center.longitude]).addTo(map).bindPopup(`${center.name}<br/>Capacity: ${center.capacity}`);
    centerMarkers.push(marker);
  });

  evacOutput.innerHTML = nearestCenters
    .map((center, index) => `${index + 1}. ${center.name}<br/>${center.distance_km} km · cap ${center.capacity}`)
    .join("<br/><br/>");
  if (!evacOutput.innerHTML) {
    evacOutput.innerHTML = "No centers found.";
  }
}

async function fetchRoute() {
  if (!nearestCenters.length) {
    await fetchEvacCenters();
  }

  if (!nearestCenters.length) {
    routeOutput.textContent = "No destination center available.";
    return;
  }

  const destination = nearestCenters[0];
  const mode = routeMode.value;
  const url = `/api/safe-route/?origin_lat=${selectedPoint.lat}&origin_lng=${selectedPoint.lng}&dest_lat=${destination.latitude}&dest_lng=${destination.longitude}&mode=${mode}`;

  const response = await fetch(url);
  const data = await response.json();

  if (!response.ok) {
    routeOutput.textContent = data.error || "Route computation failed.";
    return;
  }

  if (routeLine) {
    map.removeLayer(routeLine);
  }

  const latlngs = data.route.map((point) => [point.lat, point.lng]);
  routeLine = L.polyline(latlngs, {
    color: mode === "fastest" ? "#6d4c41" : "#1d6fa3",
    weight: 5,
  }).addTo(map);

  map.fitBounds(routeLine.getBounds(), { padding: [30, 30] });
  routeOutput.textContent = [
    `Distance: ${data.total_distance} km`,
    `Hazard exposure: ${data.hazard_exposure}`,
    `Mode: ${mode}`,
  ].join("\n");
}

async function submitChat(event) {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) {
    return;
  }

  appendChat("You", message);
  chatInput.value = "";

  const payload = {
    message,
    lat: selectedPoint.lat,
    lng: selectedPoint.lng,
  };

  const response = await fetch("/api/chat/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    appendChat("BahaWatch", data.error || "Chat request failed.");
    return;
  }

  const actionText = data.actions_taken && data.actions_taken.length
    ? `<br/><br/>Actions: ${data.actions_taken.join(", ")}`
    : "";
  appendChat("BahaWatch", `${data.reply}${actionText}`);
}

function appendChat(author, text) {
  const isUser = author === "You";
  const line = document.createElement("div");
  line.className = `chat-message ${isUser ? "user" : "bot"}`;

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  const sender = `<span class="chat-meta">${author}</span>`;
  const safeText = typeof text === "string" ? text : JSON.stringify(text);
  bubble.innerHTML = `${sender}<br/>${safeText}`;
  line.appendChild(bubble);
  chatLog.appendChild(line);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function clearCenterMarkers() {
  centerMarkers.forEach((marker) => map.removeLayer(marker));
  centerMarkers = [];
}
