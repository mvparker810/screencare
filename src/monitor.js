// Immediate logging to verify script loaded
console.log("[SCREENCARE] Content script loaded on: " + window.location.href);

let isDetecting = false;
let videoStream = null;
let videoEl = null;
let detectionInterval = null;

console.log("[SCREENCARE] Setting up message listener...");

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  console.log("[SCREENCARE] Got message:", msg);

  if (msg.type === "START") {
    console.log("[SCREENCARE] Starting detection...");
    startDetection();
    sendResponse({ success: true, message: "Detection started" });
  } else if (msg.type === "STOP") {
    console.log("[SCREENCARE] Stopping detection...");
    stopDetection();
    sendResponse({ success: true, message: "Detection stopped" });
  } else {
    sendResponse({ success: true, message: "Content script alive" });
  }
  return true;
});

console.log("[SCREENCARE] Message listener registered");

async function startDetection() {
  if (isDetecting) return;

  try {
    console.log("[SCREENCARE] Requesting camera access...");
    // Request camera access
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });

    console.log("[SCREENCARE] Camera access granted");
    videoStream = stream;
    isDetecting = true;

    // Create hidden video element
    if (!videoEl) {
      videoEl = document.createElement("video");
      videoEl.autoplay = true;
      videoEl.playsInline = true;
      videoEl.muted = true;
      videoEl.style.position = "fixed";
      videoEl.style.width = "1px";
      videoEl.style.height = "1px";
      videoEl.style.opacity = "0";
      videoEl.style.pointerEvents = "none";
      document.body.appendChild(videoEl);
      console.log("[SCREENCARE] Video element created and added to DOM");
    }

    videoEl.srcObject = stream;
    console.log("[SCREENCARE] Stream assigned to video element");

    // Try to play the video
    const playPromise = videoEl.play();
    if (playPromise !== undefined) {
      playPromise
        .then(() => {
          console.log("[SCREENCARE] Video playing");
        })
        .catch((error) => {
          console.warn("[SCREENCARE] Video play failed: " + error);
        });
    }

    // Wait for video to actually load before starting to capture frames
    videoEl.onloadedmetadata = () => {
      console.log("[SCREENCARE] Video metadata loaded, dimensions: " + videoEl.videoWidth + "x" + videoEl.videoHeight);
      if (!detectionInterval) {
        startSendingFrames();
        console.log("[SCREENCARE] Detection started successfully");
      }
    };

    // Fallback: if metadata doesn't load in 1 second, start anyway with whatever dimensions we have
    setTimeout(() => {
      if (!detectionInterval) {
        console.log("[SCREENCARE] Timeout - starting anyway. Video dimensions: " + videoEl.videoWidth + "x" + videoEl.videoHeight);
        startSendingFrames();
      }
    }, 1000);
  } catch (error) {
    console.error("[SCREENCARE] Error accessing camera:", error);
    isDetecting = false;
  }
}

function stopDetection() {
  console.log("[SCREENCARE] Stopping detection...");
  isDetecting = false;

  if (videoStream) {
    videoStream.getTracks().forEach((track) => track.stop());
    videoStream = null;
    console.log("[SCREENCARE] Video stream stopped");
  }

  if (detectionInterval) {
    clearInterval(detectionInterval);
    detectionInterval = null;
    console.log("[SCREENCARE] Frame transmission loop stopped");
  }

  console.log("[SCREENCARE] Detection stopped");
}

function startSendingFrames() {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  let frameCount = 0;
  let loggedDimensions = false;

  console.log("[SCREENCARE] Starting frame transmission loop (~10 FPS)...");

  detectionInterval = setInterval(async () => {
    if (!isDetecting || !videoEl || videoEl.readyState < 2) {
      if (frameCount === 0) {
        console.log("[SCREENCARE] Waiting for video element to be ready... (readyState: " + (videoEl ? videoEl.readyState : "no video") + ")");
      }
      return;
    }

    frameCount++;

    // Draw video to canvas
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;

    // Log dimensions on first successful capture
    if (!loggedDimensions && canvas.width > 0) {
      console.log("[SCREENCARE] Canvas dimensions: " + canvas.width + "x" + canvas.height);
      loggedDimensions = true;
    }

    ctx.drawImage(videoEl, 0, 0);

    // Convert to base64
    const frameData = canvas.toDataURL("image/jpeg", 0.8);
    if (frameCount <= 3) {
      console.log("[SCREENCARE] Frame " + frameCount + ": " + frameData.length + " bytes (canvas: " + canvas.width + "x" + canvas.height + ")");
    }

    // Send to Flask backend
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
        console.log("[SCREENCARE] Posture: " + result.status + " | Face Size: " + result.faceSize + " | Detected: " + result.isFaceDetected);
      }

      // Show alerts
      if (result.badAlert) {
        console.warn("[SCREENCARE] BAD POSTURE ALERT!");
        alert("Bad posture! Move back from screen");
      } else if (result.warningAlert) {
        console.warn("[SCREENCARE] WARNING ALERT!");
        alert("Warning: Adjust your posture");
      } else if (result.noFaceAlert) {
        console.warn("[SCREENCARE] NO FACE ALERT!");
        alert("Face not detected");
      }
    } catch (err) {
      console.warn("[SCREENCARE] Backend error: " + err.message);
    }
  }, 1000 / 10); // ~10 fps
}
