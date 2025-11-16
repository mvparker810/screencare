// Offscreen document for displaying alerts
console.log("[SCREENCARE] Offscreen document loaded");

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "show_alert") {
    console.log("[SCREENCARE OFFSCREEN] Showing alert:", message);
    displayAlert(message);
    sendResponse({ success: true });
  }
  return true;
});

function displayAlert(message) {
  const { title, alertType, alertMessage } = message;

  // Color mapping based on alert type
  const colorMap = {
    bad: "#ef4444",
    warning: "#eab308",
    no_face: "#7bd6c4",
    low_blink: "#3b82f6"
  };

  const bgColor = colorMap[alertType] || "#3b82f6";

  // Create backdrop
  const backdrop = document.createElement("div");
  backdrop.className = "alert-backdrop";
  backdrop.style.background = `rgba(0, 0, 0, 0.6)`;

  // Create alert box
  const alertBox = document.createElement("div");
  alertBox.className = "alert-box";
  alertBox.style.borderTop = `5px solid ${bgColor}`;

  const titleEl = document.createElement("div");
  titleEl.className = "alert-title";
  titleEl.textContent = title;
  titleEl.style.color = bgColor;

  const messageEl = document.createElement("p");
  messageEl.className = "alert-message";
  messageEl.textContent = alertMessage;

  alertBox.appendChild(titleEl);
  alertBox.appendChild(messageEl);

  // Create container
  const container = document.createElement("div");
  container.className = "alert-container";
  container.appendChild(alertBox);

  // Add to body
  document.body.appendChild(backdrop);
  document.body.appendChild(container);

  // Remove after 3 seconds
  setTimeout(() => {
    alertBox.classList.add("fade-out");
    backdrop.classList.add("fade-out");
    setTimeout(() => {
      backdrop.remove();
      container.remove();
    }, 300);
  }, 3000);
}
