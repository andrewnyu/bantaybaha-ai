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
let chatUnlocked = false;
const OPENAI_KEY_STORAGE = "bahawatch-openai-key-v1";

const riskOutput = document.getElementById("riskOutput");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");
const chatCard = document.getElementById("chatCard");
const chatSendBtn = document.getElementById("chatSendBtn");
const chatSuggestions = document.getElementById("chatSuggestions");
const openaiKeyInput = document.getElementById("openaiKeyInput");
const storedOpenAIKey = localStorage.getItem(OPENAI_KEY_STORAGE);
if (storedOpenAIKey) {
  openaiKeyInput.value = storedOpenAIKey;
}

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
  if (!chatUnlocked) {
    riskOutput.textContent = "Point selected. Click Check Flood Risk to continue.";
  }
});

lockChat();

document.getElementById("riskBtn").addEventListener("click", fetchRisk);
chatForm.addEventListener("submit", submitChat);
chatSuggestions.addEventListener("click", submitSuggestion);
openaiKeyInput.addEventListener("change", () => {
  const keyValue = openaiKeyInput.value.trim();
  if (keyValue) {
    localStorage.setItem(OPENAI_KEY_STORAGE, keyValue);
  } else {
    localStorage.removeItem(OPENAI_KEY_STORAGE);
  }
});

function lockChat() {
  chatCard.classList.add("locked");
  chatInput.disabled = true;
  chatSendBtn.disabled = true;
  openaiKeyInput.disabled = true;
  chatSuggestions
    .querySelectorAll("button")
    .forEach((button) => (button.disabled = true));
}

function unlockChat() {
  if (chatUnlocked) {
    return;
  }

  chatUnlocked = true;
  chatCard.classList.remove("locked");
  chatInput.disabled = false;
  chatSendBtn.disabled = false;
  openaiKeyInput.disabled = false;
  chatSuggestions
    .querySelectorAll("button")
    .forEach((button) => (button.disabled = false));
}

async function fetchRisk() {
  const url = `/api/risk/?lat=${selectedPoint.lat}&lng=${selectedPoint.lng}&hours=3`;

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

  unlockChat();
  if (!document.getElementById("chatLog").children.length) {
    appendChat(
      "BahaWatch",
      "Risk checked. You can ask follow-ups or use one of the quick suggestions."
    );
  }
}

async function submitSuggestion(event) {
  const button = event.target.closest(".chat-suggestion");
  if (!button || button.disabled || !chatUnlocked) {
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
  if (!message || !chatUnlocked) {
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
  };

  const openAIKey = openaiKeyInput.value.trim();
  if (openAIKey) {
    payload.openai_key = openAIKey;
  }

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
  } else {
    const actionText = data.actions_taken && data.actions_taken.length
      ? `<br/><br/>Actions: ${data.actions_taken.join(", ")}`
      : "";
    appendChat("BahaWatch", `${data.reply}${actionText}`);
    if (data.map_payload && data.map_payload.route) {
      renderChatRoute(data.map_payload.route);
    }
  }

  chatSendBtn.disabled = false;
  chatInput.focus();
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
