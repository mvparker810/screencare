document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById("toggleBtn");
  const btnLabel = document.getElementById("btnLabel");
  const btnIcon = document.getElementById("btnIcon");
  const statusPill = document.getElementById("statusPill");
  const statusText = document.getElementById("statusText");
  const stateHeadline = document.getElementById("stateHeadline");
  const stateDescription = document.getElementById("stateDescription");
  const iconCircle = document.getElementById("iconCircle");
  const iconEmoji = document.getElementById("iconEmoji");
  const errorMsg = document.getElementById("errorMsg");

  let isOn = false;

  function setOnUI() {
    toggleBtn.classList.remove("btn-off");
    toggleBtn.classList.add("btn-on");
    btnLabel.textContent = "Turn Off Screen Care";
    btnIcon.textContent = "⏸";

    statusPill.classList.remove("pill-off");
    statusPill.classList.add("pill-on");
    statusText.textContent = "On";

    stateHeadline.textContent = "Screen Care is active";
    stateDescription.textContent =
      "We’re helping you stay kind to your body. We’ll remind you when it’s time to take a break or fix your posture.";
    iconCircle.style.background = "linear-gradient(135deg, #e3f8f3, #d7f0ff)";
    iconEmoji.textContent = "✨";
  }

  function setOffUI() {
    toggleBtn.classList.remove("btn-on");
    toggleBtn.classList.add("btn-off");
    btnLabel.textContent = "Turn On Screen Care";
    btnIcon.textContent = "▶️";

    statusPill.classList.remove("pill-on");
    statusPill.classList.add("pill-off");
    statusText.textContent = "Off";

    stateHeadline.textContent = "Screen Care is paused";
    stateDescription.textContent =
      "Turn on Screen Care to watch over eye strain and posture while you work.";
    iconCircle.style.background = "linear-gradient(135deg, #e3f8f3, #f5f9ff)";
    iconEmoji.textContent = "🌿";
  }

  function getActiveTab(callback) {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs && tabs.length > 0) {
        callback(tabs[0]);
      } else {
        callback(null);
      }
    });
  }

  function requestStatusFromTab() {
    getActiveTab((tab) => {
      if (!tab) {
        setOffUI();
        return;
      }

      chrome.tabs.sendMessage(
        tab.id,
        { type: "SCREENCARE_STATUS" },
        (response) => {
          if (chrome.runtime.lastError) {
            // no content script or cannot reach it
            setOffUI();
            return;
          }

          if (response && response.isOn) {
            isOn = true;
            setOnUI();
          } else {
            isOn = false;
            setOffUI();
          }
        }
      );
    });
  }

  function sendStartToTab() {
    getActiveTab((tab) => {
      if (!tab) return;

      chrome.tabs.sendMessage(
        tab.id,
        { type: "SCREENCARE_START" },
        (response) => {
          errorMsg.style.display = "none";
          errorMsg.textContent = "";

          if (chrome.runtime.lastError) {
            errorMsg.style.display = "block";
            errorMsg.textContent = "Could not reach ScreenCare on this page.";
            setOffUI();
            isOn = false;
            return;
          }

          if (response && response.ok) {
            isOn = true;
            setOnUI();
          } else {
            isOn = false;
            setOffUI();
            errorMsg.style.display = "block";
            errorMsg.textContent =
              "Could not start ScreenCare: " +
              ((response && response.error) || "Unknown error");
          }
        }
      );
    });
  }

  function sendStopToTab() {
    getActiveTab((tab) => {
      if (!tab) return;

      chrome.tabs.sendMessage(tab.id, { type: "SCREENCARE_STOP" }, () => {
        // we don't care too much about the response here
        isOn = false;
        setOffUI();
      });
    });
  }

  toggleBtn.addEventListener("click", () => {
    if (isOn) {
      sendStopToTab();
    } else {
      sendStartToTab();
    }
  });

  // When popup opens, check if ScreenCare is already running for this tab
  requestStatusFromTab();
});
