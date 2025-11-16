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
import ctypes

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

def _show_fullscreen_block(message, duration_ms):
    """
    Show a fullscreen OpenCV window with a message and block for duration_ms.
    Modern, calm mental-health / healthcare styling.
    """
    # Get screen size (Windows)
    user32 = ctypes.windll.user32
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)

    # Create a soft pastel background
    img = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
    img[:] = (245, 240, 255)  # light pastel lavender (BGR)

    # "Card" area in the center
    card_margin_x = int(screen_w * 0.08)
    card_margin_y_top = int(screen_h * 0.12)
    card_margin_y_bottom = int(screen_h * 0.14)

    card_x1 = card_margin_x
    card_y1 = card_margin_y_top
    card_x2 = screen_w - card_margin_x
    card_y2 = screen_h - card_margin_y_bottom

    # Subtle drop shadow behind card
    shadow_offset = 10
    cv2.rectangle(
        img,
        (card_x1 + shadow_offset, card_y1 + shadow_offset),
        (card_x2 + shadow_offset, card_y2 + shadow_offset),
        (225, 220, 240),  # soft shadow color
        thickness=-1,
        lineType=cv2.LINE_AA
    )

    # Card itself (white)
    cv2.rectangle(
        img,
        (card_x1, card_y1),
        (card_x2, card_y2),
        (255, 255, 255),
        thickness=-1,
        lineType=cv2.LINE_AA
    )

    # Accent bar at top of card
    accent_height = 8
    cv2.rectangle(
        img,
        (card_x1, card_y1),
        (card_x2, card_y1 + accent_height),
        (210, 180, 255),  # soft purple accent
        thickness=-1,
        lineType=cv2.LINE_AA
    )

    # Helper to draw multi-line text
    def put_multiline_text(img, text, org, line_height=40, scale=1.2,
                           color=(80, 80, 90), thickness=2):
        x, y = org
        for line in text.split("\n"):
            if not line.strip():
                y += line_height
                continue
            (text_w, text_h), _ = cv2.getTextSize(
                line, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness
            )
            cv2.putText(
                img,
                line,
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,
                color,
                thickness,
                cv2.LINE_AA
            )
            y += line_height

    # Title (centered horizontally)
    title_text = "Reminder to Stay Kind to Your Body"
    title_scale = 1.4
    title_thickness = 2
    (title_w, title_h), _ = cv2.getTextSize(
        title_text, cv2.FONT_HERSHEY_SIMPLEX, title_scale, title_thickness
    )
    title_x = card_x1 + (card_x2 - card_x1 - title_w) // 2
    title_y = card_y1 + 80

    cv2.putText(
        img,
        title_text,
        (title_x, title_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        title_scale,
        (170, 120, 255),  # soft purple
        title_thickness,
        cv2.LINE_AA
    )

    # Main message (left-aligned inside card)
    body_x = card_x1 + 80
    body_y = title_y + 60
    put_multiline_text(
        img,
        message,
        (body_x, body_y),
        line_height=40,
        scale=1.0,
        color=(90, 100, 120),  # gentle slate gray
        thickness=2
    )

    # Info text at bottom of card
    info_text = "This screen will close automatically."
    info_scale = 0.9
    info_thickness = 2
    (info_w, info_h), _ = cv2.getTextSize(
        info_text, cv2.FONT_HERSHEY_SIMPLEX, info_scale, info_thickness
    )
    info_x = card_x1 + (card_x2 - card_x1 - info_w) // 2
    info_y = card_y2 - 40

    cv2.putText(
        img,
        info_text,
        (info_x, info_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        info_scale,
        (150, 150, 170),  # soft muted gray
        info_thickness,
        cv2.LINE_AA
    )

    window_name = "Eye Break"
    cv2.namedWindow(window_name, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow(window_name, img)

    # Block here for duration_ms milliseconds
    cv2.waitKey(duration_ms)

    cv2.destroyWindow(window_name)

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
    message = (   # 1️⃣ Added message = and parentheses
    "\n\nEye Strain Detected\n\n"
    "Take a 5-minute break, spend it wisely to fuel your soul, here is an idea:\n\n"
    f" {suggestion}\n\n"   # 2️⃣ Added \n\n after the suggestion
    "A tiny pause now saves you from burning out later!"
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
        "\n\nSlight Eye Strain Detected\n\n"
        "Pause and follow the 20-20 rule:\n\n"
        "- Look at something ~20 feet away\n"
        "- For at least 20 seconds\n"
        "- Blink slowly and gently while you do it\n"
    )

    # 20 seconds = 20 * 1000 ms
    _show_fullscreen_block(message, duration_ms=20 * 1000)

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
        


