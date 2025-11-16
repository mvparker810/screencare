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

def init_detector():
    """Initialize the posture detector"""
    global detector
    try:
        detector = PostureDetector(distance_threshold=0.5)
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
                    logger.warning("🚨 BAD POSTURE DETECTED - Move back from screen!")
                elif alerts['warning_alert']:
                    logger.warning("⚠️  WARNING - Adjust your posture!")
                elif alerts['no_face_alert']:
                    logger.warning("👤 NO FACE DETECTED - Face not in frame!")

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
