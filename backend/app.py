"""
Flask REST API for Posture Detection
Backend directly accesses camera and detects posture
"""

import cv2
import numpy as np
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from posture_detector import PostureDetector
import logging
import threading
import time
import tkinter as tk
import random

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize detector once at startup
detector = None
is_detecting = False
detection_thread = None

# Store latest detection state
current_status = {
    'posture_status': 'good',
    'face_size': None,
    'is_face_detected': False,
    'alerts': {'bad_alert': False, 'warning_alert': False, 'no_face_alert': False, 'low_blink_rate_alert': False}
}

def show_popup(message, bg_color):
    def popup():
        root = tk.Tk()
        root.overrideredirect(True)              # Remove window border
        root.attributes("-topmost", True)        # Always on top
        root.configure(bg=bg_color)

        # Size and position (bottom-right corner)
        width, height = 380, 110
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = screen_w - width - 40
        y = screen_h - height - 80
        root.geometry(f"{width}x{height}+{x}+{y}")

        label = tk.Label(root, text=message, font=("Segoe UI", 12),
                         fg="white", bg=bg_color, wraplength=360, justify="left")
        label.pack(expand=True, fill="both", padx=16, pady=12)

        # Auto-close after 3 seconds
        root.after(3000, root.destroy)
        root.mainloop()

    threading.Thread(target=popup, daemon=True).start()



def init_detector():
    """Initialize the posture detector"""
    global detector
    try:
        detector = PostureDetector(distance_threshold=0.18)
        logger.info("PostureDetector initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize detector: {e}")
        return False

def run_detection_loop():
    """Continuously capture from camera and detect posture"""
    global is_detecting, current_status

    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            logger.error("Cannot access camera")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        logger.info("Camera opened successfully")
        frame_count = 0

        while is_detecting:
            ret, frame = cap.read()
            if not ret:
                logger.error("Failed to read frame")
                break

            frame_count += 1

            # Flip for selfie view
            frame = cv2.flip(frame, 1)

            # Detect posture
            posture_status, face_size, bbox, is_face_detected, alerts = detector.detect_posture(frame)

            # Update current status for frontend to poll
            current_status = {
                'posture_status': posture_status,
                'face_size': float(face_size) if face_size is not None else None,
                'is_face_detected': is_face_detected,
                'alerts': alerts
            }

            # Log every 10th frame
            if frame_count % 10 == 0:
                distance_str = f"{face_size:.3f}" if face_size is not None else "None"
                print(f"[DETECT] Face: {is_face_detected} | Distance: {distance_str} | Status: {posture_status} | Bad: {alerts['bad_alert']} | Warning: {alerts['warning_alert']} | NoFace: {alerts['no_face_alert']}")

                # Trigger alerts
                if alerts['bad_alert']:
                    msg = "🚨 BAD POSTURE \nMove back from the screen!"
                    show_popup(msg, "#C62828")  # Red
                    logger.warning(msg)
                elif alerts['warning_alert']:
                    msg = "⚠️  WARNING - Adjust your posture!"
                    show_popup(msg, "#F57C00")
                    logger.warning("⚠️  WARNING - Adjust your posture!")
                # elif alerts['no_face_alert']:
                #     logger.warning("👤 NO FACE DETECTED - Face not in frame!")

            # Small delay to avoid CPU spinning
            time.sleep(0.01)  # ~100 FPS capture, process at ~10 FPS

        cap.release()
        logger.info("Camera released")
    except Exception as e:
        logger.error(f"Detection loop error: {e}")
    finally:
        is_detecting = False


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'detecting': is_detecting,
        'detector_ready': detector is not None
    }), 200


@app.route('/start', methods=['POST'])
def start():
    """Start posture detection"""
    global is_detecting, detection_thread

    if is_detecting:
        return jsonify({'status': 'already detecting'}), 200

    try:
        is_detecting = True
        detection_thread = threading.Thread(target=run_detection_loop, daemon=True)
        detection_thread.start()
        logger.info("Detection started")
        return jsonify({'status': 'started'}), 200
    except Exception as e:
        logger.error(f"Failed to start detection: {e}")
        is_detecting = False
        return jsonify({'error': str(e)}), 500


@app.route('/stop', methods=['POST'])
def stop():
    """Stop posture detection"""
    global is_detecting

    is_detecting = False
    logger.info("Detection stopped")
    return jsonify({'status': 'stopped'}), 200


@app.route('/status', methods=['GET'])
def status():
    """Get current detection status"""
    return jsonify(current_status), 200


if __name__ == '__main__':
    # Initialize detector
    if init_detector():
        # Run Flask server
        logger.info("Starting Flask server on http://localhost:5000")
        app.run(host='localhost', port=5000, debug=False)
    else:
        logger.error("Failed to start server - detector initialization failed")
        
def _show_fullscreen_block(message, duration_ms):
    """
    Create a fullscreen, top-most Tk window that blocks the screen
    for the given duration in milliseconds.
    """
    def block():
        root = tk.Tk()
        root.overrideredirect(True)          # Remove window chrome
        root.attributes("-topmost", True)    # Always on top
        root.attributes("-fullscreen", True) # Fullscreen

        # Background + base layout
        root.configure(bg="#212121")

        # Container frame
        frame = tk.Frame(root, bg="#212121")
        frame.pack(expand=True, fill="both", padx=40, pady=40)

        title = tk.Label(
            frame,
            text="Take a Break",
            font=("Segoe UI", 32, "bold"),
            fg="white",
            bg="#212121",
        )
        title.pack(pady=(0, 20))

        label = tk.Label(
            frame,
            text=message,
            font=("Segoe UI", 18),
            fg="#E0E0E0",
            bg="#212121",
            wraplength=root.winfo_screenwidth() - 160,
            justify="center",
        )
        label.pack(pady=(0, 20))

        info = tk.Label(
            frame,
            text="This screen will close automatically.",
            font=("Segoe UI", 12),
            fg="#B0B0B0",
            bg="#212121",
        )
        info.pack(pady=(10, 0))

        # Disable basic key presses from closing the window easily
        def swallow_event(event):
            return "break"

        for key in ["<Escape>", "<Alt_L>", "<Alt_R>", "<Control_L>", "<Control_R>"]:
            root.bind(key, swallow_event)

        # Auto-close after duration_ms
        root.after(duration_ms, root.destroy)
        root.mainloop()

    threading.Thread(target=block, daemon=True).start()


def block_screen_with_5min_activity():
    """
    Block the screen and suggest a random 5-minute activity.
    Intended to be called when blink rate drops below a threshold.
    (Do NOT call it here; just define it.)
    """
    activities = [
        "Call or text a loved one and check in.",
        "Fill a glass of water and drink it slowly.",
        "Stand up, stretch your neck, shoulders, and back.",
        "Walk around your room or office for a few minutes.",
        "Write down three things you're grateful for.",
        "Do a short breathing exercise: inhale 4s, hold 4s, exhale 4s.",
        "Look out the window and notice five things you can see.",
    ]

    suggestion = random.choice(activities)
    message = (
        "🚨 LOW BLINK RATE DETECTED\n\n"
        "Your eyes and posture need a rest.\n\n"
        "Take a **5-minute break** and do this:\n\n"
        f"- {suggestion}"
    )

    # 5 minutes = 5 * 60 * 1000 ms
    _show_fullscreen_block(message, duration_ms=5 * 60 * 1000)


def block_screen_20_20_rule():
    """
    Block the screen and show a simple low eye strain / 20-20 rule message.
    Intended to be called when low eye strain / blinking is detected.
    (Do NOT call it here; just define it.)
    """
    message = (
        "👀 LOW EYE STRAIN / BLINK RATE DETECTED\n\n"
        "Pause and follow the 20-20 rule:\n\n"
        "- Look at something ~20 feet away\n"
        "- For at least **20 seconds**\n"
        "- Blink slowly and gently while you do it\n"
    )

    # 20 seconds = 20 * 1000 ms
    _show_fullscreen_block(message, duration_ms=20 * 1000)

