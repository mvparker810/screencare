"""
Flask REST API for Posture Detection
Connects Chrome Extension frontend with Python backend
"""

import cv2
import numpy as np
import base64
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from posture_detector import PostureDetector
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome extension

# Initialize detector once at startup
detector = None

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


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'detector_ready': detector is not None
    }), 200


@app.route('/detect', methods=['POST'])
def detect():
    """
    Detect posture from a video frame

    Expected JSON:
    {
        "frame": "base64_encoded_image_data"
    }

    Returns:
    {
        "status": "good|warning|bad",
        "faceSize": 0.15,
        "isFaceDetected": true,
        "shouldAlert": false
    }
    """
    try:
        if not detector:
            return jsonify({'error': 'Detector not initialized'}), 500

        # Get JSON data
        data = request.get_json()

        if not data or 'frame' not in data:
            return jsonify({'error': 'Missing frame data'}), 400

        # Decode base64 frame
        frame_data = data['frame']

        # Remove data URI prefix if present
        if ',' in frame_data:
            frame_data = frame_data.split(',')[1]

        # Decode base64 to bytes
        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)

        # Decode image
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({'error': 'Failed to decode frame'}), 400

        # Run detection
        posture_status, face_size, bbox, is_face_detected, alerts = detector.detect_posture(frame)

        # Prepare response
        response = {
            'status': posture_status,
            'faceSize': float(face_size) if face_size is not None else None,
            'isFaceDetected': is_face_detected,
            'shouldAlert': detector.bad_posture_counter >= detector.bad_posture_threshold,
            'badPostureTime': detector.bad_posture_time,
            'noFaceAlert': alerts['no_face_alert'],
            'warningAlert': alerts['warning_alert'],
            'badAlert': alerts['bad_alert'],
            'noFaceDuration': round(detector.no_face_duration, 2),
            'warningDuration': round(detector.warning_duration, 2),
            'badDuration': round(detector.bad_duration, 2)
        }

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Detection error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/detect-batch', methods=['POST'])
def detect_batch():
    """
    Process multiple frames in batch

    Expected JSON:
    {
        "frames": ["base64_1", "base64_2", ...]
    }

    Returns:
    {
        "results": [
            {"status": "good", "faceSize": 0.15, ...},
            ...
        ]
    }
    """
    try:
        if not detector:
            return jsonify({'error': 'Detector not initialized'}), 500

        data = request.get_json()

        if not data or 'frames' not in data:
            return jsonify({'error': 'Missing frames data'}), 400

        frames = data['frames']
        results = []

        for frame_data in frames:
            try:
                # Remove data URI prefix if present
                if ',' in frame_data:
                    frame_data = frame_data.split(',')[1]

                # Decode
                frame_bytes = base64.b64decode(frame_data)
                nparr = np.frombuffer(frame_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    results.append({'error': 'Failed to decode'})
                    continue

                # Detect
                posture_status, face_size, bbox, is_face_detected, alerts = detector.detect_posture(frame)

                results.append({
                    'status': posture_status,
                    'faceSize': float(face_size) if face_size is not None else None,
                    'isFaceDetected': is_face_detected,
                    'shouldAlert': detector.bad_posture_counter >= detector.bad_posture_threshold,
                    'noFaceAlert': alerts['no_face_alert'],
                    'warningAlert': alerts['warning_alert'],
                    'badAlert': alerts['bad_alert']
                })
            except Exception as e:
                results.append({'error': str(e)})

        return jsonify({'results': results}), 200

    except Exception as e:
        logger.error(f"Batch detection error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/reset', methods=['POST'])
def reset():
    """Reset detector state"""
    try:
        global detector
        detector = PostureDetector(distance_threshold=0.5)
        return jsonify({'status': 'reset'}), 200
    except Exception as e:
        logger.error(f"Reset error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Initialize detector
    if init_detector():
        # Run Flask server
        logger.info("Starting Flask server on http://localhost:5000")
        app.run(host='localhost', port=5000, debug=False)
    else:
        logger.error("Failed to start server - detector initialization failed")
