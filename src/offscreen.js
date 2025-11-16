let videoEl = document.getElementById('camera');
let canvas = document.getElementById('canvas');
let ctx = canvas.getContext('2d');
let videoStream = null;
let detectionInterval = null;
let isDetecting = false;

console.log("[SCREENCARE] Offscreen document loaded");

// Listen for messages from Service Worker
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  console.log("[SCREENCARE] Offscreen got message:", msg.type);

  if (msg.type === "START") {
    startDetection();
    sendResponse({ success: true });
  } else if (msg.type === "STOP") {
    stopDetection();
    sendResponse({ success: true });
  }
  return true;
});

async function startDetection() {
  if (isDetecting) {
    console.log("[SCREENCARE] Already detecting");
    return;
  }

  try {
    console.log("[SCREENCARE] Requesting camera...");
    videoStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });

    console.log("[SCREENCARE] Camera granted");
    videoEl.srcObject = videoStream;
    isDetecting = true;

    // Wait for video to load
    videoEl.onloadedmetadata = () => {
      console.log("[SCREENCARE] Video ready: " + videoEl.videoWidth + "x" + videoEl.videoHeight);
      if (!detectionInterval) startSendingFrames();
    };

    // Timeout fallback
    setTimeout(() => {
      if (isDetecting && !detectionInterval) {
        console.log("[SCREENCARE] Starting frame loop (timeout)");
        startSendingFrames();
      }
    }, 1000);
  } catch (error) {
    console.error("[SCREENCARE] Camera error:", error);
    isDetecting = false;
  }
}

function stopDetection() {
  console.log("[SCREENCARE] Stopping detection");
  isDetecting = false;

  if (videoStream) {
    videoStream.getTracks().forEach(t => t.stop());
    videoStream = null;
  }

  if (detectionInterval) {
    clearInterval(detectionInterval);
    detectionInterval = null;
  }
}

function startSendingFrames() {
  if (detectionInterval) return;

  let frameCount = 0;
  console.log("[SCREENCARE] Starting frame capture");

  detectionInterval = setInterval(async () => {
    if (!isDetecting || videoEl.readyState < 2) return;

    frameCount++;
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    ctx.drawImage(videoEl, 0, 0);
    const frameData = canvas.toDataURL("image/jpeg", 0.8);

    if (frameCount === 1) {
      console.log("[SCREENCARE] First frame: " + frameData.length + " bytes (" + canvas.width + "x" + canvas.height + ")");
    }

    try {
      const response = await fetch("http://localhost:5000/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frame: frameData }),
      });

      if (!response.ok) {
        console.warn("[SCREENCARE] Flask error: " + response.status);
        return;
      }

      const result = await response.json();

      if (frameCount <= 3) {
        console.log("[SCREENCARE] Response: " + result.status + " | Face: " + result.isFaceDetected);
      }

      // Notify Service Worker of alerts
      if (result.badAlert || result.warningAlert || result.noFaceAlert) {
        chrome.runtime.sendMessage({
          type: "ALERT",
          alert: result.badAlert ? "bad" : result.warningAlert ? "warning" : "noface"
        }).catch(() => {});
      }
    } catch (err) {
      console.warn("[SCREENCARE] Request error: " + err.message);
    }
  }, 100); // ~10 fps
}
