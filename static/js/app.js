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
const mapNode = document.getElementById("map");
const locationSearchInput = document.getElementById("locationSearchInput");
const locationSearchBtn = document.getElementById("locationSearchBtn");
const myLocationBtn = document.getElementById("myLocationBtn");
const selectedLocationLabel = document.getElementById("selectedLocationLabel");
const demoWeatherToggle = document.getElementById("demoWeatherToggle");
const demoRainfallInput = document.getElementById("demoRainfallInput");
const demoHoursInput = document.getElementById("demoHoursInput");
const demoScenarioSelect = document.getElementById("demoScenarioSelect");
const demoWeatherContext = document.getElementById("demoWeatherContext");
const demoUpstreamWeatherInput = document.getElementById("demoUpstreamWeatherInput");
const generateUpstreamNodesBtn = document.getElementById("generateUpstreamNodesBtn");
const clearDemoRainfallBtn = document.getElementById("clearDemoRainfallBtn");
const weatherSourceStatus = document.getElementById("weatherSourceStatus");
const demoTabStatus = document.getElementById("demoTabStatus");
const weatherModeIndicator = document.getElementById("weatherModeIndicator");
const tabLinks = document.querySelectorAll(".tab-link");
const tabPanels = document.querySelectorAll("[data-tab-panel]");

const isOpenAIConfigured = chatCard?.dataset?.openaiConfigured === "1";
const SETTINGS_STORAGE_KEY = "bahawatch_weather_settings_v1";

let map = null;
let mapEnabled = false;
let selectedPoint = { ...DEFAULT_COORD };
let selectedMarker = null;
let routeLine = null;
let routeDestinationMarker = null;
let evacCenterMarkers = [];
let riskCircle = null;
const chatHistory = [];
let selectedAddress = { barangay: "n/a", city: "n/a", raw: {} };
let reverseLookupRequestId = 0;
let chatLoadingBubble = null;
let weatherSettings = {
  demoModeEnabled: false,
  demoRainfall: "10,22,45,30,12,5",
  demoUpstreamWeather: "",
  forecastHours: 3,
  demoScenario: "custom",
};

const DEMO_SCENARIOS = {
  custom: {
    label: "Custom",
    rainfall: null,
  },
  high_rain: {
    label: "High rain (typhoon level)",
    rainfall: [140, 165, 150, 130, 110, 95],
    upstream: null,
  },
  medium_rain: {
    label: "Medium rain",
    rainfall: [50, 45, 40, 32, 25, 18],
    upstream: null,
  },
  no_rain_high_upstream: {
    label: "No rain, high upstream rain",
    rainfall: [0, 0, 0, 0, 0, 0],
    upstream: [120, 135, 115, 95, 70, 55],
  },
};

const shownWarnings = new Set();

const centerMarkerIcon =
  typeof L !== "undefined"
    ? L.divIcon({
        className: "evac-center-icon",
        html: '<div class="evac-center-icon-inner">🏥</div>',
        iconSize: [28, 28],
        iconAnchor: [14, 28],
        popupAnchor: [0, -30],
      })
    : null;

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

const loadWeatherSettings = () => {
  const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
  if (!raw) {
    return;
  }

  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return;
    }

    weatherSettings.demoModeEnabled = Boolean(parsed.demoModeEnabled);
    if (typeof parsed.demoRainfall === "string") {
      weatherSettings.demoRainfall = parsed.demoRainfall;
    }
    if (typeof parsed.demoUpstreamWeather === "string") {
      weatherSettings.demoUpstreamWeather = parsed.demoUpstreamWeather;
    }
    if (Number.isFinite(parsed.forecastHours)) {
      weatherSettings.forecastHours = Math.min(6, Math.max(1, Number(parsed.forecastHours)));
    }
    if (typeof parsed.demoScenario === "string" && DEMO_SCENARIOS[parsed.demoScenario]) {
      weatherSettings.demoScenario = parsed.demoScenario;
    }
  } catch (error) {
    // Keep defaults.
  }
};

const saveWeatherSettings = () => {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(weatherSettings));
};

const parseDemoRainfallValues = (value) => {
  if (value == null) {
    return [];
  }

  if (typeof value === "number") {
    if (!Number.isFinite(value) || value < 0) {
      throw new Error("Demo rainfall values must be non-negative.");
    }
    return [Number(value.toFixed(1))];
  }

  if (Array.isArray(value)) {
    const values = [];
    for (const item of value) {
      const next = Number(item);
      if (!Number.isFinite(next)) {
        throw new Error("Invalid demo rainfall value. Use numbers only.");
      }
      if (next < 0) {
        throw new Error("Demo rainfall values must be non-negative.");
      }
      values.push(next);
    }

    return values.slice(0, 6).map((v) => Number(v.toFixed(1)));
  }

  if (typeof value !== "string") {
    throw new Error("Demo rainfall input must be a string, number, or array.");
  }

  const raw = value.trim();
  if (!raw) {
    return [];
  }

  let items = [];
  if (raw.startsWith("[") && raw.endsWith("]")) {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error("Demo rainfall JSON must be an array.");
    }
    items = parsed;
  } else {
    items = raw.split(",");
  }

  const values = [];
  for (const item of items) {
    const token = String(item).trim();
    if (!token) {
      throw new Error("Demo rainfall list contains empty values.");
    }
    const next = Number(token);
    if (!Number.isFinite(next)) {
      throw new Error("Invalid demo rainfall value. Use numbers only.");
    }
    if (next < 0) {
      throw new Error("Demo rainfall values must be non-negative.");
    }
    values.push(next);
  }

  return values.slice(0, 6).map((v) => Number(v.toFixed(1)));
};

const normalizeDemoUpstreamNodeKey = (lat, lng) => {
  const latValue = Number(lat);
  const lngValue = Number(lng);
  if (!Number.isFinite(latValue) || !Number.isFinite(lngValue)) {
    return "";
  }
  return `${latValue.toFixed(5)},${lngValue.toFixed(5)}`;
};

const parseDemoUpstreamWeather = (value, fallbackRainfall = []) => {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw) {
    return [];
  }

  let parsed = [];
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error("Demo upstream weather must be valid JSON.");
  }

  if (!Array.isArray(parsed)) {
    throw new Error("Demo upstream weather must be an array of objects.");
  }

  const cleaned = [];
  const fallback = Array.isArray(fallbackRainfall) ? fallbackRainfall : [];
  let fallbackCount = 0;
  for (const entry of parsed) {
    if (!entry || typeof entry !== "object") {
      throw new Error("Each upstream weather entry must be an object.");
    }

    const lat = Number(entry.lat);
    const lng = Number(entry.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      throw new Error("Each upstream weather entry must include valid lat/lng.");
    }

    const rawRainfall = entry.demo_rainfall ?? entry.rainfall ?? entry.values ?? [];
    let parsedRainfall = [];
    const hasRainfallValue =
      rawRainfall !== undefined &&
      rawRainfall !== null &&
      !(typeof rawRainfall === "string" && rawRainfall.trim() === "") &&
      !(Array.isArray(rawRainfall) && rawRainfall.length === 0);

    if (hasRainfallValue) {
      try {
        parsedRainfall = parseDemoRainfallValues(rawRainfall);
      } catch (error) {
        parsedRainfall = fallback.slice();
        fallbackCount += 1;
      }
    } else if (fallback.length) {
      parsedRainfall = fallback.slice();
      fallbackCount += 1;
    }

    if (!hasRainfallValue && !fallback.length) {
      parsedRainfall = [];
    }

    cleaned.push({
      lat,
      lng,
      demo_rainfall: parsedRainfall,
    });
  }

  if (fallbackCount > 0 && demoRainfallInput) {
    const fallbackText = fallback.length ? "using local demo rainfall" : "with empty values";
    setDemoTabStatus(
      `Filled ${fallbackCount} upstream node${fallbackCount > 1 ? "s" : ""} ${fallbackText}.`,
      "info"
    );
  }

  return cleaned;
};

const formatRainfallPreview = (values) => {
  if (!Array.isArray(values) || values.length === 0) {
    return "0 mm/hr";
  }

  if (values.length > 3) {
    return `${values.slice(0, 3).join(", ")}... (${values.length}h)`;
  }

  return values.join(", ");
};

const applyDemoScenario = (scenarioKey, options = {}) => {
  const scenario = DEMO_SCENARIOS[scenarioKey] || DEMO_SCENARIOS.custom;
  const nextScenario = Object.keys(DEMO_SCENARIOS).includes(scenarioKey)
    ? scenarioKey
    : "custom";

  weatherSettings.demoScenario = nextScenario;

  if (nextScenario !== "custom" && Array.isArray(scenario.rainfall)) {
    const valueText = scenario.rainfall.join(",");
    weatherSettings.demoRainfall = valueText;
    if (demoRainfallInput) {
      demoRainfallInput.value = valueText;
    }
  }

  if (demoScenarioSelect) {
    demoScenarioSelect.value = nextScenario;
  }

  if (!options.skipStatus) {
    if (nextScenario === "custom") {
      setDemoTabStatus("Using custom manual rainfall inputs.", "info");
    } else if (nextScenario === "no_rain_high_upstream") {
      setDemoTabStatus(
        "Scenario set: no local rain, high upstream rain. Click Generate upstream nodes to populate per-node overrides.",
        "info"
      );
    } else {
      setDemoTabStatus(`Scenario set: ${scenario.label}.`, "info");
    }
  }

  saveWeatherSettings();
  syncWeatherSettingsUI();
};

const setDemoTabStatus = (message, level = "info") => {
  if (!demoTabStatus) {
    return;
  }

  const text = (message || "").trim();
  demoTabStatus.textContent = text || "Ready for demo weather input.";

  demoTabStatus.classList.remove("status-info", "status-warn", "status-error");
  demoTabStatus.classList.add(`status-${level}`);
};

const setWeatherModeIndicator = (mode, label) => {
  if (!weatherModeIndicator) {
    return;
  }

  const states = {
    live: {
      className: "live",
      label: "Live OpenWeather forecast",
    },
    demo: {
      className: "demo",
      label: "Demo scenario active",
    },
    invalid: {
      className: "warn",
      label: "Demo mode: invalid rainfall input",
    },
  };

  const current = states[mode] || states.live;
  weatherModeIndicator.className = `weather-mode-chip ${current.className}`;
  weatherModeIndicator.textContent = label || current.label;
};

const parseDemoHours = (value, fallback = 3) => {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(6, Math.max(1, parsed));
};

const buildDemoLocationLabel = () => {
  const barangay = selectedAddress?.barangay || "n/a";
  const city = selectedAddress?.city || "n/a";

  if (barangay !== "n/a" && city !== "n/a") {
    return `${barangay}, ${city}`;
  }

  if (barangay !== "n/a") {
    return barangay;
  }

  if (city !== "n/a") {
    return city;
  }

  const latText = Number.isFinite(selectedPoint.lat)
    ? selectedPoint.lat.toFixed(4)
    : "n/a";
  const lngText = Number.isFinite(selectedPoint.lng)
    ? selectedPoint.lng.toFixed(4)
    : "n/a";
  return `${latText}, ${lngText}`;
};

const updateDemoContextText = () => {
  if (!demoWeatherContext) {
    return;
  }

  const hours = parseDemoHours(weatherSettings.forecastHours, 3);
  demoWeatherContext.textContent = `Set weather in ${buildDemoLocationLabel()} for next ${hours} hour${hours > 1 ? "s" : ""}.`;
};

const syncWeatherSettingsUI = () => {
  const clampedHours = parseDemoHours(weatherSettings.forecastHours, 3);
  weatherSettings.forecastHours = clampedHours;
  let demoModeValid = false;

  if (demoWeatherToggle) {
    demoWeatherToggle.checked = Boolean(weatherSettings.demoModeEnabled);
  }
  if (demoHoursInput) {
    demoHoursInput.disabled = !Boolean(weatherSettings.demoModeEnabled);
    demoHoursInput.value = String(clampedHours);
  }
  if (demoScenarioSelect) {
    const selectedScenario = DEMO_SCENARIOS[weatherSettings.demoScenario]
      ? weatherSettings.demoScenario
      : "custom";
    demoScenarioSelect.value = selectedScenario;
    weatherSettings.demoScenario = selectedScenario;
  }
  if (demoRainfallInput) {
    demoRainfallInput.disabled = !Boolean(weatherSettings.demoModeEnabled);
    if (demoRainfallInput.value !== weatherSettings.demoRainfall) {
      demoRainfallInput.value = weatherSettings.demoRainfall;
    }
  }
  if (demoUpstreamWeatherInput) {
    demoUpstreamWeatherInput.disabled = !Boolean(weatherSettings.demoModeEnabled);
    if (demoUpstreamWeatherInput.value !== weatherSettings.demoUpstreamWeather) {
      demoUpstreamWeatherInput.value = weatherSettings.demoUpstreamWeather;
    }
  }
  if (generateUpstreamNodesBtn) {
    generateUpstreamNodesBtn.disabled = !Boolean(weatherSettings.demoModeEnabled);
  }
  if (clearDemoRainfallBtn) {
    clearDemoRainfallBtn.disabled = !Boolean(weatherSettings.demoModeEnabled);
  }

  if (weatherSettings.demoModeEnabled) {
    try {
      const parsed = parseDemoRainfallValues(weatherSettings.demoRainfall);
      demoModeValid = true;
      if (weatherSourceStatus) {
        weatherSourceStatus.textContent = `Current source: DEMO (${formatRainfallPreview(parsed)}) for ${clampedHours}h`;
      }
    } catch (error) {
      demoModeValid = false;
      if (weatherSourceStatus) {
        weatherSourceStatus.textContent = `Current source: DEMO (${clampedHours}h, invalid input).`;
      }
    }
    if (demoModeValid) {
      setWeatherModeIndicator("demo");
    } else {
      setWeatherModeIndicator("invalid");
    }
  } else {
    demoModeValid = true;
    if (weatherSourceStatus) {
      weatherSourceStatus.textContent = "Current source: live OpenWeather forecast";
    }
    setWeatherModeIndicator("live");
  }

  updateDemoContextText();
};

const formatAddressLabel = (address = {}) => {
  const barangay =
    address.barangay ||
    address.suburb ||
    address.quarter ||
    address.neighbourhood ||
    address.village ||
    address.hamlet ||
    "n/a";

  const city =
    address.city || address.town || address.municipality || address.county || "n/a";

  return { barangay, city };
};

const updateSelectedLocationLabel = () => {
  if (!selectedLocationLabel) {
    return;
  }

  const lat = Number.isFinite(selectedPoint.lat)
    ? selectedPoint.lat.toFixed(5)
    : "n/a";
  const lng = Number.isFinite(selectedPoint.lng)
    ? selectedPoint.lng.toFixed(5)
    : "n/a";
  const barangay = selectedAddress?.barangay || "n/a";
  const city = selectedAddress?.city || "n/a";
  selectedLocationLabel.textContent = `Barangay: ${barangay}, City: ${city} (${lat}, ${lng})`;
  updateDemoContextText();
};

const resolveReverseAddress = async (lat, lng, requestId) => {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return;
  }

  const lookupId = requestId ?? ++reverseLookupRequestId;
  const params = new URLSearchParams({
    format: "jsonv2",
    lat: String(lat),
    lon: String(lng),
    addressdetails: "1",
    zoom: "18",
  });

  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/reverse?${params.toString()}`
    );
    if (!response.ok) {
      throw new Error("reverse geocode request failed");
    }

    const data = await response.json();
    if (lookupId !== reverseLookupRequestId) {
      return;
    }

    const address = data?.address || {};
    const formatted = formatAddressLabel(address);
    selectedAddress = {
      barangay: formatted.barangay,
      city: formatted.city,
      raw: address,
    };
    updateSelectedLocationLabel();
  } catch (error) {
    if (lookupId !== reverseLookupRequestId) {
      return;
    }

    selectedAddress = {
      barangay: "n/a",
      city: "n/a",
      raw: selectedAddress.raw || {},
    };
    addStatusFlag("Could not resolve address for this location.", "warn");
    updateSelectedLocationLabel();
    updateDemoContextText();
  }
};

const generateUpstreamNodePayloadFromRisk = async () => {
  if (!generateUpstreamNodesBtn) {
    return;
  }

  if (!demoWeatherToggle?.checked) {
    setDemoTabStatus("Enable demo mode before generating upstream nodes.", "warn");
    return;
  }

  const hours = parseDemoHours(weatherSettings.forecastHours, 3);
  generateUpstreamNodesBtn.disabled = true;

  let baselineRainfall = [];
  try {
    baselineRainfall = parseDemoRainfallValues(demoRainfallInput?.value);
  } catch (error) {
    setDemoTabStatus(error.message || "Invalid demo rainfall values.", "error");
    generateUpstreamNodesBtn.disabled = false;
    return;
  }

  const params = new URLSearchParams({
    lat: String(selectedPoint.lat),
    lng: String(selectedPoint.lng),
    hours: String(hours),
    weather_mode: "demo",
    demo_rainfall: baselineRainfall.join(","),
  });

  try {
    const response = await fetch(`/api/risk/?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      setDemoTabStatus(data.error || "Could not generate upstream nodes.", "error");
      return;
    }

    const nodes = data?.upstream_summary?.dominant_upstream_points;
    if (!Array.isArray(nodes) || nodes.length === 0) {
      setDemoTabStatus("No upstream nodes returned for this location.", "warn");
      return;
    }

    let currentOverrides = [];
    try {
      currentOverrides = parseDemoUpstreamWeather(weatherSettings.demoUpstreamWeather, baselineRainfall);
    } catch (error) {
      currentOverrides = [];
    }
    const overrideMap = new Map();
    currentOverrides.forEach((item) => {
      overrideMap.set(
        normalizeDemoUpstreamNodeKey(item.lat, item.lng),
        item.demo_rainfall ?? []
      );
    });

    const generated = nodes.map((node) => {
      const key = normalizeDemoUpstreamNodeKey(node.lat, node.lng);
      const scenarioProfile = DEMO_SCENARIOS[weatherSettings.demoScenario]?.upstream;
      return {
        lat: Number(node.lat),
        lng: Number(node.lng),
        demo_rainfall:
          overrideMap.get(key) ||
          scenarioProfile ||
          baselineRainfall.slice(),
      };
    });

    weatherSettings.demoUpstreamWeather = JSON.stringify(generated, null, 2);
    saveWeatherSettings();
    syncWeatherSettingsUI();
    setDemoTabStatus(
      `Generated ${generated.length} upstream nodes. Add per-node rainfall in JSON above.`,
      "info"
    );
  } catch (error) {
    setDemoTabStatus("Failed to fetch upstream nodes for demo override.", "error");
  } finally {
    generateUpstreamNodesBtn.disabled = !Boolean(weatherSettings.demoModeEnabled);
  }
};

const setSelectedPoint = (latlng, origin = "manual") => {
  if (!latlng) {
    return;
  }

  const lat = Number(latlng.lat);
  const lng = Number(latlng.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    return;
  }

  selectedPoint = { lat, lng };

  if (mapEnabled && map) {
    if (selectedMarker) {
      selectedMarker.setLatLng([lat, lng]);
    } else {
      selectedMarker = L.marker([lat, lng]).addTo(map);
    }

    if (origin === "search" || origin === "my_location") {
      map.setView([lat, lng], Math.max(map.getZoom(), 14));
    }
  }

  const lookupId = ++reverseLookupRequestId;
  selectedAddress = {
    barangay: "n/a",
    city: "n/a",
    raw: {},
  };
  updateSelectedLocationLabel();
  resolveReverseAddress(lat, lng, lookupId);
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
    setSelectedPoint(selectedPoint, "init");

    map.on("click", (event) => {
      setSelectedPoint(event.latlng, "click");
    });

    mapEnabled = true;
  } catch (error) {
    mapEnabled = false;
    addStatusFlag("Map failed to initialize. Chat remains available without map visuals.", "warn");
  }

  initFallbackWarnings();
};

const switchTab = (selectedTab) => {
  if (!tabLinks.length) {
    return;
  }

  tabLinks.forEach((tab) => {
    const isActive = tab.getAttribute("data-tab") === selectedTab;
    tab.classList.toggle("active", isActive);
  });

  tabPanels.forEach((panel) => {
    const isPanelActive = panel.getAttribute("data-tab-panel") === selectedTab;
    panel.classList.toggle("active", isPanelActive);
  });

  syncWeatherSettingsUI();
};

loadWeatherSettings();
syncWeatherSettingsUI();
initMap();
updateSelectedLocationLabel();
if (tabLinks.length > 0) {
  const activeTab = document.querySelector('.tab-link.active')?.getAttribute("data-tab") || "home";
  switchTab(activeTab);
}

if (tabLinks.length > 0) {
  tabLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const targetTab = link.getAttribute("data-tab");
      if (targetTab) {
        switchTab(targetTab);
      }
    });
  });
}

if (locationSearchInput && locationSearchBtn) {
  const runSearch = () => {
    searchLocation(locationSearchInput.value);
  };

  locationSearchBtn.addEventListener("click", runSearch);
  locationSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });
}

if (myLocationBtn) {
  myLocationBtn.addEventListener("click", getCurrentLocation);
}

if (demoWeatherToggle) {
  demoWeatherToggle.addEventListener("change", () => {
    weatherSettings.demoModeEnabled = demoWeatherToggle.checked;
    saveWeatherSettings();
    syncWeatherSettingsUI();
  });
}

if (demoScenarioSelect) {
  demoScenarioSelect.addEventListener("change", () => {
    applyDemoScenario(demoScenarioSelect.value);
  });
}

if (demoRainfallInput) {
  demoRainfallInput.addEventListener("input", () => {
    weatherSettings.demoRainfall = demoRainfallInput.value;
    weatherSettings.demoScenario = "custom";
    if (demoScenarioSelect) {
      demoScenarioSelect.value = "custom";
    }
    saveWeatherSettings();
    syncWeatherSettingsUI();
  });
}

if (demoHoursInput) {
  demoHoursInput.addEventListener("input", () => {
    weatherSettings.forecastHours = parseDemoHours(demoHoursInput.value, 3);
    saveWeatherSettings();
    syncWeatherSettingsUI();
  });
}

if (generateUpstreamNodesBtn) {
  generateUpstreamNodesBtn.addEventListener("click", generateUpstreamNodePayloadFromRisk);
}

if (demoUpstreamWeatherInput) {
  demoUpstreamWeatherInput.addEventListener("input", () => {
    weatherSettings.demoUpstreamWeather = demoUpstreamWeatherInput.value;
    weatherSettings.demoScenario = "custom";
    if (demoScenarioSelect) {
      demoScenarioSelect.value = "custom";
    }
    saveWeatherSettings();
  });
}

if (clearDemoRainfallBtn) {
  clearDemoRainfallBtn.addEventListener("click", () => {
    weatherSettings.demoRainfall = "";
    weatherSettings.demoUpstreamWeather = "";
    weatherSettings.demoModeEnabled = true;
    weatherSettings.demoScenario = "custom";
    if (demoScenarioSelect) {
      demoScenarioSelect.value = "custom";
    }
    saveWeatherSettings();
    syncWeatherSettingsUI();
    setDemoTabStatus("Demo rainfall values cleared (will be treated as zeros).", "warn");
  });
}

shuffleChatSuggestions();

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
  shuffleChatSuggestions();
  await submitChat(null, message);
}

async function searchLocation(query) {
  const trimmedQuery = (query || "").trim();
  if (!trimmedQuery) {
    addStatusFlag("Enter a place name to search.", "warn");
    return;
  }

  if (locationSearchBtn) {
    locationSearchBtn.disabled = true;
  }

  const params = new URLSearchParams({
    format: "jsonv2",
    limit: "1",
    addressdetails: "1",
    countrycodes: "ph",
    bounded: "1",
    viewbox: `${NEGROS_BOUNDS.west},${NEGROS_BOUNDS.north},${NEGROS_BOUNDS.east},${NEGROS_BOUNDS.south}`,
    q: trimmedQuery,
  });

  try {
    const response = await fetch(`https://nominatim.openstreetmap.org/search?${params.toString()}`);
    if (!response.ok) {
      throw new Error("search request failed");
    }

    const data = await response.json();
    if (!Array.isArray(data) || data.length === 0) {
      addStatusFlag("No matching location found in Negros. Try a nearby place name.", "warn");
      return;
    }

    const first = data[0];
    const lat = Number(first.lat);
    const lng = Number(first.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      addStatusFlag("Search result had invalid coordinates.", "warn");
      return;
    }

    setSelectedPoint({ lat, lng }, "search");
  } catch (error) {
    addStatusFlag("Location search failed. Please try again.", "warn");
  } finally {
    if (locationSearchBtn) {
      locationSearchBtn.disabled = false;
    }
  }
}

function getCurrentLocation() {
  if (!myLocationBtn) {
    return;
  }

  if (!navigator.geolocation) {
    addStatusFlag("Geolocation is not supported by this browser.", "warn");
    return;
  }

  myLocationBtn.disabled = true;
  navigator.geolocation.getCurrentPosition(
    (position) => {
      myLocationBtn.disabled = false;
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      setSelectedPoint({ lat, lng }, "my_location");
    },
    () => {
      myLocationBtn.disabled = false;
      addStatusFlag("Unable to get your current location. Please allow location access.", "warn");
    },
    {
      enableHighAccuracy: true,
      timeout: 12000,
      maximumAge: 30000,
    }
  );
}

const extractRiskResultFromChatResponse = (response) => {
  if (!response || typeof response !== "object") {
    return null;
  }

  const toolOutputs = Array.isArray(response.tool_outputs) ? response.tool_outputs : [];
  for (const item of toolOutputs) {
    if (!item || item.tool !== "tool_get_risk") {
      continue;
    }

    const result = item.result;
    if (result && typeof result === "object") {
      return result;
    }
  }

  const mapPayload = response.map_payload;
  if (mapPayload && mapPayload.type === "risk" && typeof mapPayload.risk_score !== "undefined") {
    return {
      risk_score: mapPayload.risk_score,
      risk_level: mapPayload.risk_level,
      expected_peak_in_hours: null,
    };
  }

  return null;
};

const getRiskLevelClass = (riskScore) => {
  if (riskScore >= 65) {
    return "high";
  }
  if (riskScore >= 35) {
    return "medium";
  }
  return "low";
};

const appendRiskMeterBubble = (riskPayload) => {
  if (!chatLog || !riskPayload || typeof riskPayload !== "object") {
    return;
  }

  const scoreRaw = Number(riskPayload.risk_score);
  if (!Number.isFinite(scoreRaw)) {
    return;
  }

  const score = Math.max(0, Math.min(100, Math.round(scoreRaw)));
  const level = (riskPayload.risk_level || getRiskLevelClass(score)).toString().toUpperCase();
  const bandClass = getRiskLevelClass(score);
  const line = document.createElement("div");
  line.className = "chat-message bot";

  const riskLabel = `Flood risk: ${score}/100 (${level})`;
  const peakText =
    riskPayload.expected_peak_in_hours !== null && riskPayload.expected_peak_in_hours !== undefined
      ? `Peak expected in ${riskPayload.expected_peak_in_hours}h`
      : "";

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble chat-risk-meter";
  bubble.innerHTML = `
    <div class="chat-risk-meter-header">
      <span>${riskLabel}</span>
      <span class="chat-risk-level risk-${bandClass.toLowerCase()}">${level}</span>
    </div>
    <div class="chat-risk-track" role="presentation">
      <span class="chat-risk-fill risk-${bandClass.toLowerCase()}" style="width:${score}%"></span>
    </div>
    <span class="chat-meta">${peakText || "Forecast window up to selected hours."}</span>
  `;

  line.appendChild(bubble);
  chatLog.appendChild(line);
  chatLog.scrollTop = chatLog.scrollHeight;
};

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
  chatHistory.push({ role: "user", content: message });
  setChatBusy(true);
  addChatLoadingBubble();

  const payload = {
    message,
    lat: selectedPoint.lat,
    lng: selectedPoint.lng,
    hours: parseDemoHours(weatherSettings.forecastHours, 3),
    chat_history: chatHistory.slice(-10),
    weather_mode: demoWeatherToggle?.checked ? "demo" : "live",
  };

  if (demoWeatherToggle?.checked) {
    let baselineRainfall = [];
    try {
      baselineRainfall = parseDemoRainfallValues(demoRainfallInput?.value);
      payload.demo_rainfall = baselineRainfall;
      payload.demo_upstream_rainfall = parseDemoUpstreamWeather(
        demoUpstreamWeatherInput?.value,
        baselineRainfall
      );
    } catch (error) {
      addStatusFlag(error.message || "Invalid demo rainfall values.", "error");
      removeChatLoadingBubble();
      setChatBusy(false);
      return;
    }
    if (Array.isArray(payload.demo_upstream_rainfall) && payload.demo_upstream_rainfall.length === 0) {
      delete payload.demo_upstream_rainfall;
    }
  }

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
      removeChatLoadingBubble();
      appendChat("BahaWatch", data.error || "Chat request failed.");
      return;
    }

    const botReply = data.reply || "No response returned.";
    removeChatLoadingBubble();
    appendChat("BahaWatch", botReply);
    appendRiskMeterBubble(extractRiskResultFromChatResponse(data));
    chatHistory.push({ role: "assistant", content: botReply });

    if (data.map_payload && mapEnabled) {
      if (data.map_payload.type === "route" && data.map_payload.route) {
        renderChatRoute(data.map_payload);
      } else if (data.map_payload.type === "evac_centers") {
        renderEvacCenters(data.map_payload.centers || []);
      } else if (data.map_payload.type === "risk") {
        renderRiskMarker(data.map_payload);
      }
    } else if (data.map_payload) {
      addStatusFlag("Map visuals are unavailable in this session. I still provided the text answer above.", "warn");
    }
  } catch (error) {
    removeChatLoadingBubble();
    appendChat("BahaWatch", "I couldn't reach the chat service just now. Please try again in a moment.");
  } finally {
    setChatBusy(false);
    chatInput.focus();
  }
}

function shuffleChatSuggestions() {
  if (!chatSuggestions) {
    return;
  }

  const chips = Array.from(chatSuggestions.children).filter((child) =>
    child.classList.contains("chat-suggestion")
  );
  for (let i = chips.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [chips[i], chips[j]] = [chips[j], chips[i]];
  }

  chips.forEach((chip) => chatSuggestions.appendChild(chip));
}

const setChatBusy = (isBusy) => {
  if (chatInput) {
    chatInput.disabled = isBusy;
  }

  if (chatSendBtn) {
    chatSendBtn.disabled = isBusy;
  }

  if (chatSuggestions) {
    const suggestionButtons = chatSuggestions.querySelectorAll(".chat-suggestion");
    suggestionButtons.forEach((button) => {
      button.disabled = isBusy;
    });
  }
};

const addChatLoadingBubble = (text = "Checking flood data...") => {
  if (!chatLog || chatLoadingBubble) {
    return;
  }

  const line = document.createElement("div");
  line.className = "chat-message bot";

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble chat-loading";
  const safeText = typeof text === "string" ? text : "Checking flood data...";
  bubble.innerHTML = `<span class="chat-meta">BahaWatch</span><br/><span>${safeText}<span class="chat-loading-spinner"></span></span>`;

  line.appendChild(bubble);
  chatLog.appendChild(line);
  chatLoadingBubble = line;
  chatLog.scrollTop = chatLog.scrollHeight;
};

const removeChatLoadingBubble = () => {
  if (!chatLoadingBubble || !chatLog) {
    return;
  }

  chatLog.removeChild(chatLoadingBubble);
  chatLoadingBubble = null;
};

function renderRiskMarker(payload) {
  clearRouteOverlays();
  clearEvacCenterMarkers();

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
  clearEvacCenterMarkers();

  if (!mapEnabled || !map) {
    return;
  }

  if (!route || !Array.isArray(route.route) || route.route.length === 0) {
    return;
  }

  clearRouteOverlays();

  const latlngs = route.route.map((point) => [point.lat, point.lng]);
  routeLine = L.polyline(latlngs, {
    color: "#1d6fa3",
    weight: 5,
  }).addTo(map);

  const destination = latlngs[latlngs.length - 1];
  if (route.is_evacuation_center && centerMarkerIcon && destination) {
    const label = route.destination_name || "Evacuation center";
    routeDestinationMarker = L.marker(destination, {
      icon: centerMarkerIcon,
    }).addTo(map);
    routeDestinationMarker.bindPopup(`<strong>${label}</strong>`);
  }

  map.fitBounds(routeLine.getBounds(), { padding: [30, 30] });
}

function renderEvacCenters(centers) {
  if (!mapEnabled || !map) {
    return;
  }

  clearRouteOverlays();
  clearEvacCenterMarkers();

  if (!Array.isArray(centers) || centers.length === 0) {
    return;
  }

  const centerPoints = [];
  centers.forEach((center) => {
    const lat = Number(center.latitude);
    const lng = Number(center.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return;
    }

    const marker = centerMarkerIcon
      ? L.marker([lat, lng], { icon: centerMarkerIcon })
      : L.marker([lat, lng]);
    const label = center.name || "Evacuation Center";
    const distance = center.distance_km ?? "";
    const distanceLabel = distance === "" ? "" : ` (${distance} km away)`;
    marker.bindPopup(`<strong>${label}</strong>${distanceLabel}`);
    marker.addTo(map);
    evacCenterMarkers.push(marker);
    centerPoints.push([lat, lng]);
  });

  if (centerPoints.length === 1) {
    map.setView(centerPoints[0], Math.max(map.getZoom(), 14));
    return;
  }

  const bounds = L.latLngBounds(centerPoints);
  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [35, 35] });
  }
}

function clearEvacCenterMarkers() {
  if (!map || evacCenterMarkers.length === 0) {
    return;
  }

  evacCenterMarkers.forEach((marker) => map.removeLayer(marker));
  evacCenterMarkers = [];
}

function clearRouteOverlays() {
  if (routeLine) {
    map.removeLayer(routeLine);
    routeLine = null;
  }

  if (routeDestinationMarker) {
    map.removeLayer(routeDestinationMarker);
    routeDestinationMarker = null;
  }
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
