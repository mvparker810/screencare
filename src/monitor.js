let screenCareIsOn = false;
let screenCareStream = null;
let videoEl = null;
let processingInterval = null;
let isEyeClosed = false;
let lastEyeClosedTime = 0;
let blinkCount = 0;
let faceMesh = null;
const BLINK_HISTORY = []; // { timestamp, count }
const HISTORY_WINDOW_MS = 30 * 60 * 1000; // 30 minutes
let currentMinuteBlinkCount = 0;
let minuteTimer = null;
// FaceMesh will run our CV
const faceMesh = new FaceMesh({
  locateFile: (file) => chrome.runtime.getURL("libs/face_mesh/" + file),
});

// Configure FaceMesh (like in your Python project)
faceMesh.setOptions({
  maxNumFaces: 1,
  refineLandmarks: true,
  minDetectionConfidence: 0.5,
  minTrackingConfidence: 0.5,
});

const RIGHT_EYE = [33, 159, 158, 133, 153, 145];
const LEFT_EYE  = [362, 380, 374, 263, 386, 385];

// --- EAR helpers (JavaScript port of your Python eye_aspect_ratio) ---

function distance(p1, p2) {
  const dx = p1.x - p2.x;
  const dy = p1.y - p2.y;
  return Math.sqrt(dx * dx + dy * dy);
}

function eyeAspectRatio(eyeIndices, landmarks) {
  const p1 = landmarks[eyeIndices[0]];
  const p2 = landmarks[eyeIndices[1]];
  const p3 = landmarks[eyeIndices[2]];
  const p4 = landmarks[eyeIndices[3]];
  const p5 = landmarks[eyeIndices[4]];
  const p6 = landmarks[eyeIndices[5]];

  const A = distance(p2, p6);
  const B = distance(p3, p5);
  const C = distance(p1, p4);

  return (A + B) / (2.0 * C);
}

function computeEyeOpenness(landmarks) {
  const rightEAR = eyeAspectRatio(RIGHT_EYE, landmarks);
  const leftEAR  = eyeAspectRatio(LEFT_EYE, landmarks);
  const avgEAR = (rightEAR + leftEAR) / 2.0;
  return avgEAR; // higher = more open, lower = more closed
}
// When FaceMesh finishes processing a frame, this runs:
faceMesh.onResults((results) => {
  if (!results.multiFaceLandmarks || !results.multiFaceLandmarks.length) return;

  const landmarks = results.multiFaceLandmarks[0];
  const eyeOpenness = computeEyeOpenness(landmarks);
  onFaceResults(eyeOpenness); //how open is the eye? 
});

async function startScreenCareInPage() {
  if (screenCareIsOn) {
    return { ok: true }; // already on
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: false,
    });

    screenCareStream = stream;
    screenCareIsOn = true;

    setupHiddenVideo(stream);
    startBlinkProcessing();
    console.log("ScreenCare: monitoring started in this tab");

    return { ok: true };
  } catch (err) {
    console.error("ScreenCare: error accessing camera in page", err);
    screenCareIsOn = false;
    screenCareStream = null;
    return { ok: false, error: err.message || err.name || "Unknown error" };
  }
}

function stopScreenCareInPage() { //stop video and everything
  if (screenCareStream) {
    screenCareStream.getTracks().forEach((track) => track.stop());
    screenCareStream = null;
  }
  if (processingInterval) {
    clearInterval(processingInterval);
    processingInterval = null;
  }
  if (minuteTimer) {
    clearInterval(minuteTimer);
    minuteTimer = null;
  }
  screenCareIsOn = false;
  console.log("ScreenCare: monitoring stopped in this tab");
}


function setupHiddenVideo(stream) {
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
  }
  videoEl.srcObject = stream;
}

async function startBlinkProcessing() { 
  // If you don’t want analytics yet, keep this commented:
  // setupBlinkAnalytics();

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");

  processingInterval = setInterval(async () => {
    if (!videoEl || videoEl.readyState < 2) return;

    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

    await faceMesh.send({ image: canvas }); //this does everything, processes video, sends to faceMesh
  }, 1000 / 15); // ~15 fps
}


function onFaceResults(eyeOpenness) {
  const now = performance.now(); //get time
  const CLOSED_THRESHOLD = 0.25; //
  const MIN_BLINK_DURATION = 80; // ms
  const MAX_BLINK_DURATION = 800; // ms

  if (eyeOpenness < CLOSED_THRESHOLD) {
    if (!isEyeClosed) {
      //if eye is open
      isEyeClosed = true; //eye just closed
      lastEyeClosedTime = now;
    }
  } else {
    if (isEyeClosed) {
      //if eye is closed
      const duration = now - lastEyeClosedTime; //blink just ended, get duration
      if (duration >= MIN_BLINK_DURATION && duration <= MAX_BLINK_DURATION) {
        //if blink is within scientific limits
        blinkCount++;
        currentMinuteBlinkCount++;
        console.log("Blink!", blinkCount);
      }
      isEyeClosed = false; //reset
    }
  }
}

// every minute, roll analytics
function setupBlinkAnalytics() {
  if (minuteTimer) return;

  minuteTimer = setInterval(() => {
    //run timer every minute
    const now = Date.now();
    BLINK_HISTORY.push({
      //each minute push the amount of blinks
      timestamp: now,
      count: currentMinuteBlinkCount,
    });
    currentMinuteBlinkCount = 0;

    // purge old data beyond 30 min
    while (
      BLINK_HISTORY.length &&
      now - BLINK_HISTORY[0].timestamp > HISTORY_WINDOW_MS
    ) {
      //if more than 60 minutes passed, reset
      BLINK_HISTORY.shift();
    }

    evaluateBlinkHealth(); // decide whether to show break
  }, 60 * 1000);
}

function getBlinkStatsLast30min() {
  const now = Date.now();
  const entries = BLINK_HISTORY.filter(
    (e) => now - e.timestamp <= HISTORY_WINDOW_MS //keep the ones that happened last 30 minutes
  );
  if (entries.length === 0) return { avgPerMin: 0, minutes: 0 }; //unavailable data

  const totalBlinks = entries.reduce((sum, e) => sum + e.count, 0); //sum all blinks
  const minutes = entries.length; //get minutes

  return {
    avgPerMin: totalBlinks / minutes, //average blinks per minute is total blinks over mins
    minutes,
  };
}

let consecutiveLowMinutes = 0;
let consecutiveVeryLowMinutes = 0;

function evaluateBlinkHealth() {
  const last = BLINK_HISTORY[BLINK_HISTORY.length - 1];
  if (!last) return;

  const blinksPerMin = last.count; //get most recent blinks per minute

  if (blinksPerMin <= 6) {
    consecutiveVeryLowMinutes++; //serious fatigue
    consecutiveLowMinutes++; //fatigue
  } else if (blinksPerMin <= 11) {
    consecutiveLowMinutes++;
    consecutiveVeryLowMinutes = 0;
  } else {
    consecutiveLowMinutes = 0;
    consecutiveVeryLowMinutes = 0;
  }
  //If blinking rate is low for 2 minutes 
  if (consecutiveLowMinutes === 2) {
    console.log("Blinking rlly low for 2 mins");
    // showBreakOverlay({
    //   type: "micro",
    //   message:
    //     "Your blink rate has been a bit low. Look 20 seconds at something 20 feet away. Blink slowly",
    //   durationSec: 20,
    // });
  }

  //Bigger break if very low for 5 minutes
  if (consecutiveVeryLowMinutes === 5) {
    console.log("Blinking rlly low for 5 mins");
    // showBreakOverlay({
    //   type: "macro",
    //   message:
    //     "Your eyes need a quick reset. Step away for 5 minutes. A short pause now prevents fatigue later.",
    //   durationSec: 300,
    // });
  }
}



//still need to implement block & the analytics. in the first prompt

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "SCREENCARE_START") {
    startScreenCareInPage().then((result) => {
      sendResponse(result);
    });
    return true; // keep the message channel open for async
  }

  if (msg.type === "SCREENCARE_STOP") {
    stopScreenCareInPage();
    sendResponse({ ok: true });
    return; // no async needed
  }

  if (msg.type === "SCREENCARE_STATUS") {
    sendResponse({ isOn: screenCareIsOn });
    return;
  }
});
