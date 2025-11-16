console.log("[SCREENCARE] Service Worker loaded");

let isDetecting = false;
let statusPollInterval = null;
let lastAlertTime = {};

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  console.log("[SCREENCARE] Service Worker message:", msg.type);

  if (msg.type === "START") {
    isDetecting = true;
    startStatusPolling();
    sendResponse({ success: true });
    return true;
  } else if (msg.type === "STOP") {
    isDetecting = false;
    if (statusPollInterval) clearInterval(statusPollInterval);
    sendResponse({ success: true });
    return true;
  }
});

function startStatusPolling() {
  // Stop any existing polling
  if (statusPollInterval) clearInterval(statusPollInterval);

  // Poll every 500ms
  statusPollInterval = setInterval(async () => {
    try {
      const response = await fetch("http://localhost:5000/status");
      if (response.ok) {
        const status = await response.json();
        checkAndShowAlerts(status);
      }
    } catch (err) {
      console.error("[SCREENCARE] Status poll error:", err);
    }
  }, 500);
}

function checkAndShowAlerts(status) {
  const now = Date.now();

  // Check for no face alert
  if (status.alerts.no_face_alert) {
    showNotification("no_face", "👤 We can't find you!", "Please make sure your face is visible to the camera");
  }

  // Check for bad posture alert
  if (status.alerts.bad_alert) {
    showNotification("bad", "🚨 Bad Posture!", "Move back from the screen");
  }

  // Check for warning alert
  if (status.alerts.warning_alert) {
    showNotification("warning", "⚠️ Posture Warning", "Adjust your posture to maintain good positioning");
  }
}

function showNotification(type, title, message) {
  const now = Date.now();

  // Only show alert once every 3 seconds per type
  if (lastAlertTime[type] && (now - lastAlertTime[type]) < 3000) {
    return;
  }

  lastAlertTime[type] = now;

  const colors = {
    bad: "%23ef4444",
    warning: "%23eab308",
    no_face: "%237bd6c4"
  };

  chrome.notifications.create({
    type: "basic",
    iconUrl: `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E%3Ccircle cx='24' cy='24' r='22' fill='${colors[type]}'/%3E%3C/svg%3E`,
    title: title,
    message: message,
    priority: 2
  });
}
