const DEFAULT_COORD = { lat: 14.5995, lng: 120.9842 };

const map = L.map("map").setView([DEFAULT_COORD.lat, DEFAULT_COORD.lng], 12);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

let selectedPoint = { ...DEFAULT_COORD };
let selectedMarker = L.marker([selectedPoint.lat, selectedPoint.lng]).addTo(map);
let riskCircle = null;
let routeLine = null;
let centerMarkers = [];
let nearestCenters = [];

const hoursRange = document.getElementById("hoursRange");
const hoursValue = document.getElementById("hoursValue");
const riskOutput = document.getElementById("riskOutput");
const evacOutput = document.getElementById("evacOutput");
const routeOutput = document.getElementById("routeOutput");
const routeMode = document.getElementById("routeMode");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");

hoursRange.addEventListener("input", () => {
  hoursValue.textContent = hoursRange.value;
});

map.on("click", async (event) => {
  selectedPoint = event.latlng;
  selectedMarker.setLatLng(event.latlng);
  await fetchRisk();
});

document.getElementById("riskBtn").addEventListener("click", fetchRisk);
document.getElementById("evacBtn").addEventListener("click", fetchEvacCenters);
document.getElementById("routeBtn").addEventListener("click", fetchRoute);
chatForm.addEventListener("submit", submitChat);

function riskColor(level) {
  if (level === "HIGH") {
    return "#c62828";
  }
  if (level === "MEDIUM") {
    return "#ef6c00";
  }
  return "#2e7d32";
}

async function fetchRisk() {
  const hours = Number(hoursRange.value);
  const url = `/api/risk/?lat=${selectedPoint.lat}&lng=${selectedPoint.lng}&hours=${hours}`;

  const response = await fetch(url);
  const data = await response.json();

  if (!response.ok) {
    riskOutput.textContent = data.error || "Risk lookup failed.";
    return;
  }

  const text = [
    `Risk Score: ${data.risk_score}`,
    `Level: ${data.risk_level}`,
    `Signals: ${data.explanation.join(", ")}`,
  ].join("\n");
  riskOutput.textContent = text;

  if (riskCircle) {
    map.removeLayer(riskCircle);
  }

  riskCircle = L.circle([selectedPoint.lat, selectedPoint.lng], {
    radius: 500,
    color: riskColor(data.risk_level),
    fillColor: riskColor(data.risk_level),
    fillOpacity: 0.2,
  }).addTo(map);
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
    const marker = L.marker([center.latitude, center.longitude])
      .addTo(map)
      .bindPopup(`${center.name}<br/>Capacity: ${center.capacity}`);
    centerMarkers.push(marker);
  });

  evacOutput.textContent = nearestCenters
    .map(
      (center, index) =>
        `${index + 1}. ${center.name} - ${center.distance_km} km (capacity ${center.capacity})`
    )
    .join("\n");
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
    color: mode === "safe" ? "#1d6fa3" : "#6d4c41",
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
    appendChat("Bot", data.error || "Chat request failed.");
    return;
  }

  appendChat("Bot", `${data.reply}\nActions: ${data.actions_taken.join(", ") || "none"}`);
}

function appendChat(author, text) {
  const line = document.createElement("div");
  line.className = "chat-line";
  line.innerHTML = `<strong>${author}:</strong> ${text}`;
  chatLog.appendChild(line);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function clearCenterMarkers() {
  centerMarkers.forEach((marker) => map.removeLayer(marker));
  centerMarkers = [];
}
