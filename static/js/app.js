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

const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "map-legend");
  div.innerHTML = `
    <h4>Risk Legend</h4>
    <div><span class="swatch low"></span> Low</div>
    <div><span class="swatch medium"></span> Medium</div>
    <div><span class="swatch high"></span> High</div>
  `;
  return div;
};
legend.addTo(map);

let selectedPoint = { ...DEFAULT_COORD };
let selectedMarker = L.marker([selectedPoint.lat, selectedPoint.lng]).addTo(map);
let riskCircle = null;
let routeLine = null;

const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");
const chatSuggestions = document.getElementById("chatSuggestions");
const chatSendBtn = document.getElementById("chatSendBtn");
const languageSelect = document.getElementById("languageSelect");

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

map.on("click", (event) => {
  selectedPoint = event.latlng;
  selectedMarker.setLatLng(event.latlng);
  appendChat("BahaWatch", "Location updated. Ask me what you want next.");
});

chatForm.addEventListener("submit", submitChat);
chatSuggestions.addEventListener("click", submitSuggestion);

appendChat("BahaWatch", "Ask me anything like check risk, nearest center, or fastest route.");

async function submitSuggestion(event) {
  const button = event.target.closest(".chat-suggestion");
  if (!button) {
    return;
  }

  const message = button.dataset.message?.trim();
  if (!message) {
    return;
  }
  await submitChat(null, message);
}

async function submitChat(event, messageOverride) {
  if (event) {
    event.preventDefault();
  }

  const message = (messageOverride ?? chatInput.value).trim();
  if (!message) {
    return;
  }

  if (!messageOverride) {
    chatInput.value = "";
  }

  appendChat("You", message);
  chatSendBtn.disabled = true;

  const payload = {
    message,
    lat: selectedPoint.lat,
    lng: selectedPoint.lng,
    language: languageSelect.value,
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
    chatSendBtn.disabled = false;
    chatInput.focus();
    return;
  }

  appendChat("BahaWatch", data.reply || "No response returned.");
  if (data.map_payload) {
    if (data.map_payload.type === "route" && data.map_payload.route) {
      renderChatRoute(data.map_payload.route);
    } else if (data.map_payload.type === "risk") {
      renderRiskMarker(data.map_payload);
    }
  }

  chatSendBtn.disabled = false;
  chatInput.focus();
}

function renderRiskMarker(payload) {
  if (!payload || typeof payload.lat !== "number" || typeof payload.lng !== "number") {
    return;
  }

  if (riskCircle) {
    map.removeLayer(riskCircle);
  }

  riskCircle = L.circle([payload.lat, payload.lng], {
    radius: 500,
    color: pointRiskColor(payload.risk_level || payload.risk_score),
    fillColor: pointRiskColor(payload.risk_level || payload.risk_score),
    fillOpacity: 0.2,
  }).addTo(map);
}

function renderChatRoute(route) {
  if (!Array.isArray(route) || route.length === 0) {
    return;
  }

  if (routeLine) {
    map.removeLayer(routeLine);
  }

  const latlngs = route.map((point) => [point.lat, point.lng]);
  routeLine = L.polyline(latlngs, {
    color: "#1d6fa3",
    weight: 5,
  }).addTo(map);
  map.fitBounds(routeLine.getBounds(), { padding: [30, 30] });
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
