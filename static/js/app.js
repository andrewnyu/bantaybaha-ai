const DEFAULT_COORD = { lat: 10.6769, lng: 122.9518 };
const NEGROS_BOUNDS = {
  south: 9.0,
  north: 10.95,
  west: 122.15,
  east: 123.55,
};

const chatCard = document.getElementById("chatCard");
const statusFlags = document.getElementById("statusFlags");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatLog = document.getElementById("chatLog");
const chatSuggestions = document.getElementById("chatSuggestions");
const chatSendBtn = document.getElementById("chatSendBtn");
const languageSelect = document.getElementById("languageSelect");
const mapNode = document.getElementById("map");

const isOpenAIConfigured = chatCard?.dataset?.openaiConfigured === "1";

let map = null;
let mapEnabled = false;
let selectedPoint = { ...DEFAULT_COORD };
let selectedMarker = null;
let riskCircle = null;
let routeLine = null;

const shownWarnings = new Set();

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

const addStatusFlag = (message, type = "warn") => {
  if (!statusFlags) {
    return;
  }

  const key = `${type}:${message}`;
  if (shownWarnings.has(key)) {
    return;
  }

  shownWarnings.add(key);
  const flag = document.createElement("div");
  flag.className = `status-flag status-flag-${type}`;
  flag.textContent = message;
  statusFlags.appendChild(flag);
};

const initFallbackWarnings = () => {
  if (!isOpenAIConfigured) {
    addStatusFlag(
      "OpenAI API key is not configured. This assistant uses local rule-based responses.",
      "warn"
    );
  }

  if (typeof L === "undefined" || !mapNode) {
    addStatusFlag(
      "Map service is unavailable. Chat remains fully usable, but map visuals are disabled.",
      "warn"
    );
  }
};

const initMap = () => {
  if (typeof L === "undefined" || !mapNode) {
    initFallbackWarnings();
    return;
  }

  try {
    map = L.map("map", {
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

    selectedMarker = L.marker([selectedPoint.lat, selectedPoint.lng]).addTo(map);
    map.on("click", (event) => {
      selectedPoint = event.latlng;
      if (selectedMarker) {
        selectedMarker.setLatLng(event.latlng);
      }
      appendChat("BahaWatch", "Location updated. Ask me what you want next.");
    });

    mapEnabled = true;
  } catch (error) {
    mapEnabled = false;
    addStatusFlag("Map failed to initialize. Chat remains available without map visuals.", "warn");
  }

  initFallbackWarnings();
};

initMap();

chatForm.addEventListener("submit", submitChat);
chatSuggestions.addEventListener("click", submitSuggestion);

appendChat(
  "BahaWatch",
  "Hi there — I can help with flood risk, nearest evacuation center, and route options. Ask me anything."
);

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

  try {
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

    appendChat("BahaWatch", data.reply || "No response returned.");

    if (data.map_payload && mapEnabled) {
      if (data.map_payload.type === "route" && data.map_payload.route) {
        renderChatRoute(data.map_payload.route);
      } else if (data.map_payload.type === "risk") {
        renderRiskMarker(data.map_payload);
      }
    } else if (data.map_payload) {
      addStatusFlag("Map visuals are unavailable in this session. I still provided the text answer above.", "warn");
    }
  } catch (error) {
    appendChat("BahaWatch", "I couldn't reach the chat service just now. Please try again in a moment.");
  } finally {
    chatSendBtn.disabled = false;
    chatInput.focus();
  }
}

function renderRiskMarker(payload) {
  if (!mapEnabled || !map) {
    return;
  }

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
  if (!mapEnabled || !map) {
    return;
  }

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
