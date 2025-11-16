document.addEventListener("DOMContentLoaded", async () => {
  const btn = document.getElementById("toggleBtn");
  const stateHeadline = document.getElementById("stateHeadline");
  const stateDescription = document.getElementById("stateDescription");

  let isOn = false;
  let statusPollInterval = null;
  let lastAlertTime = {};

  // Check backend status on load
  try {
    const response = await fetch("http://localhost:5000/health");
    if (response.ok) {
      const health = await response.json();
      if (health.detecting) {
        isOn = true;
        btn.textContent = "🛑 Stop Detection";
        btn.className = "primary-btn btn-on";
        stateHeadline.textContent = "Screen Care is running";
        stateDescription.textContent = "Monitoring your posture and screen distance...";
        startStatusPolling();
      }
    }
  } catch (err) {
    console.error("Failed to check backend status:", err);
  }

  btn.addEventListener("click", async () => {
    const endpoint = isOn ? "http://localhost:5000/stop" : "http://localhost:5000/start";

    try {
      const response = await fetch(endpoint, { method: "POST" });
      if (response.ok) {
        isOn = !isOn;
        btn.textContent = isOn ? "🛑 Stop Detection" : "▶️ Start Detection";
        btn.className = isOn ? "primary-btn btn-on" : "primary-btn btn-off";

        if (isOn) {
          // Start polling status when detection is on
          startStatusPolling();
          stateHeadline.textContent = "Screen Care is running";
          stateDescription.textContent = "Monitoring your posture and screen distance...";
        } else {
          // Stop polling when detection is off
          if (statusPollInterval) clearInterval(statusPollInterval);
          stateHeadline.textContent = "Screen Care is paused";
          stateDescription.textContent = "Turn on Screen Care to watch over eye strain and posture while you work.";
        }
      }
    } catch (err) {
      console.error("Error:", err);
      alert("Failed to connect to backend. Make sure Flask is running on localhost:5000");
    }
  });

  function startStatusPolling() {
    // Poll every 500ms
    statusPollInterval = setInterval(async () => {
      try {
        const response = await fetch("http://localhost:5000/status");
        if (response.ok) {
          const status = await response.json();
          updateUI(status);
        }
      } catch (err) {
        console.error("Status poll error:", err);
      }
    }, 500);
  }

  function updateUI(status) {
    // Check for no face alert
    if (status.alerts.no_face_alert) {
      showAlert("no_face", "👤 We can't find you!", "Please make sure your face is visible to the camera");
    }

    // Check for bad posture alert (after 3 seconds)
    if (status.alerts.bad_alert) {
      showAlert("bad", "🚨 Bad Posture!", "Move back from the screen");
    }

    // Check for warning alert (after 3 seconds)
    if (status.alerts.warning_alert) {
      showAlert("warning", "⚠️ Posture Warning", "Adjust your posture to maintain good positioning");
    }

    // Update status text
    const distanceStr = status.face_size ? status.face_size.toFixed(3) : "N/A";
    stateHeadline.textContent = `${status.posture_status.charAt(0).toUpperCase() + status.posture_status.slice(1)} Posture`;
    stateDescription.textContent = `Distance: ${distanceStr} | Face Detected: ${status.is_face_detected ? "Yes" : "No"}`;
  }

  function showAlert(type, title, message) {
    const now = Date.now();

    // Only show alert once every 3 seconds per type
    if (lastAlertTime[type] && (now - lastAlertTime[type]) < 3000) {
      return;
    }

    lastAlertTime[type] = now;

    // Create and show notification
    const alertDiv = document.createElement("div");
    alertDiv.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: ${type === 'bad' ? '#ef4444' : type === 'warning' ? '#eab308' : '#7bd6c4'};
      color: white;
      padding: 16px 20px;
      border-radius: 8px;
      font-weight: 500;
      font-size: 14px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      z-index: 10000;
      max-width: 300px;
      word-wrap: break-word;
    `;

    alertDiv.innerHTML = `<strong>${title}</strong><br>${message}`;
    document.body.appendChild(alertDiv);

    // Remove after 3 seconds
    setTimeout(() => {
      alertDiv.remove();
    }, 3000);
  }
});
