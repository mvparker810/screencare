// Content script to display Screen Care alerts on webpages
console.log("[SCREENCARE] Notification injector loaded on:", window.location.href);

let lastAlertTime = {};

// Test: Try to respond to any message to verify the content script is loaded
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("[SCREENCARE INJECTOR] Received message:", message);

  if (message.type === "alert") {
    console.log("[SCREENCARE INJECTOR] Displaying alert:", message.alertType);
    displayAlert(message.alertType, message.title, message.message);
    sendResponse({ success: true });
  } else if (message.type === "ping") {
    console.log("[SCREENCARE INJECTOR] Pong!");
    sendResponse({ success: true, message: "Injector is alive" });
  }

  return true; // Keep the channel open for async response
});

function displayAlert(type, title, message) {
  const now = Date.now();

  // Only show alert once every 3 seconds per type
  if (lastAlertTime[type] && (now - lastAlertTime[type]) < 3000) {
    return;
  }

  lastAlertTime[type] = now;

  const bgColors = {
    bad: "#ef4444",
    warning: "#eab308",
    no_face: "#7bd6c4",
    low_blink: "#3b82f6"
  };

  const bgColor = bgColors[type] || "#3b82f6";

  // Create backdrop
  const backdrop = document.createElement("div");
  backdrop.className = "screencare-backdrop";
  backdrop.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999998;
    animation: fadeIn 0.3s ease-out;
  `;

  // Create alert container
  const alertDiv = document.createElement("div");
  alertDiv.className = "screencare-alert";

  alertDiv.style.cssText = `
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: ${bgColor};
    color: white;
    padding: 40px 50px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 28px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
    z-index: 999999;
    max-width: 600px;
    word-wrap: break-word;
    line-height: 1.6;
    animation: popIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
    text-align: center;
  `;

  alertDiv.innerHTML = `<div style="margin-bottom: 15px;">${title}</div><div style="font-weight: 400; font-size: 18px; opacity: 0.95;">${message}</div>`;

  document.body.appendChild(backdrop);
  document.body.appendChild(alertDiv);

  // Remove after 3 seconds
  setTimeout(() => {
    alertDiv.style.animation = "popOut 0.3s ease-in";
    backdrop.style.animation = "fadeOut 0.3s ease-in";
    setTimeout(() => {
      alertDiv.remove();
      backdrop.remove();
    }, 300);
  }, 3000);
}

// Add CSS animations if not already present
if (!document.getElementById("screencare-styles")) {
  const style = document.createElement("style");
  style.id = "screencare-styles";
  style.textContent = `
    @keyframes popIn {
      from {
        transform: translate(-50%, -50%) scale(0.5);
        opacity: 0;
      }
      to {
        transform: translate(-50%, -50%) scale(1);
        opacity: 1;
      }
    }

    @keyframes popOut {
      from {
        transform: translate(-50%, -50%) scale(1);
        opacity: 1;
      }
      to {
        transform: translate(-50%, -50%) scale(0.5);
        opacity: 0;
      }
    }

    @keyframes fadeIn {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }

    @keyframes fadeOut {
      from {
        opacity: 1;
      }
      to {
        opacity: 0;
      }
    }

    @keyframes slideIn {
      from {
        transform: translateX(400px);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }

    @keyframes slideOut {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(400px);
        opacity: 0;
      }
    }
  `;
  document.head.appendChild(style);
}
