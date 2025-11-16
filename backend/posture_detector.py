import cv2
import mediapipe as mp
import numpy as np
import time
import winsound  # For Windows beeping alerts
from collections import deque

# Initialize MediaPipe Face Detection
mp_face_detection = mp.solutions.face_detection
mp_drawing = mp.solutions.drawing_utils

class PostureDetector:
    def __init__(self, distance_threshold=0.6, smoothing_frames=10):
        """
        Initialize the posture detector.

        Args:
            distance_threshold: Face size threshold (0-1). Lower values = closer to camera = bad posture
            smoothing_frames: Number of frames to average for smooth detection
        """
        self.distance_threshold = distance_threshold
        self.smoothing_frames = smoothing_frames
        self.face_size_history = deque(maxlen=smoothing_frames)
        self.bad_posture_counter = 0
        self.bad_posture_threshold = 3  # Alert after 3 consecutive bad frames

        # Time tracking for alerts (in seconds)
        self.no_face_duration = 0
        self.last_face_time = time.time()

        # Rolling window for averaging (tracks last 10 seconds of frames)
        self.frame_history = deque(maxlen=300)  # ~10 seconds at 30fps
        self.frame_timestamps = deque(maxlen=300)

        # Alert thresholds
        self.no_face_threshold = 30  # Alert if face not detected for 30 seconds
        self.warning_avg_threshold = 0.6  # Alert if 60% of frames in last 10s are warning+
        self.bad_avg_threshold = 0.5  # Alert if 50% of frames in last 10s are bad

        # Initialize MediaPipe Face Detection once
        self.face_detection = mp_face_detection.FaceDetection(
            model_selection=1,  # 0 for short range, 1 for full range
            min_detection_confidence=0.7
        )

    def calculate_face_size(self, detection, frame_width, frame_height):
        """Calculate the relative size of the detected face."""
        bbox = detection.location_data.relative_bounding_box
        width = bbox.width * frame_width
        height = bbox.height * frame_height
        face_area = width * height
        frame_area = frame_width * frame_height
        face_size_ratio = face_area / frame_area
        return face_size_ratio, bbox

    def get_smoothed_face_size(self):
        """Get smoothed face size from history."""
        if not self.face_size_history:
            return None
        return np.mean(list(self.face_size_history))

    def detect_posture(self, frame):
        """
        Detect posture from a frame using rolling window averaging.

        Returns:
            posture_status: 'good', 'warning', or 'bad'
            face_size: relative size of face in frame
            bbox: bounding box of detected face
            alerts: dict with alert signals (based on last 10 seconds)
        """
        frame_height, frame_width, _ = frame.shape
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Use the pre-initialized face detection
        results = self.face_detection.process(frame_rgb)

        posture_status = 'good'
        face_size = None
        bbox = None
        is_face_detected = False
        current_time = time.time()

        # Initialize alerts
        alerts = {
            'no_face_alert': False,
            'warning_alert': False,
            'bad_alert': False
        }

        if results.detections:
            is_face_detected = True
            self.last_face_time = current_time  # Reset face detection timer
            self.no_face_duration = 0  # Reset no-face duration

            detection = results.detections[0]  # Use first detected face
            face_size, bbox = self.calculate_face_size(detection, frame_width, frame_height)
            self.face_size_history.append(face_size)

            smoothed_size = self.get_smoothed_face_size()

            # Determine current frame status
            if smoothed_size is None:
                posture_status = 'good'
            elif smoothed_size > self.distance_threshold:
                posture_status = 'bad'
            elif smoothed_size > self.distance_threshold * 0.75:
                posture_status = 'warning'
            else:
                posture_status = 'good'
        else:
            # No face detected
            self.no_face_duration = current_time - self.last_face_time
            posture_status = 'good'

        # Add current frame to rolling window
        self.frame_history.append(posture_status)
        self.frame_timestamps.append(current_time)

        # Calculate averages over last 10 seconds
        bad_count = sum(1 for status in self.frame_history if status == 'bad')
        warning_or_bad_count = sum(1 for status in self.frame_history if status in ['bad', 'warning'])
        total_frames = len(self.frame_history)

        if total_frames > 0:
            bad_fraction = bad_count / total_frames
            warning_or_bad_fraction = warning_or_bad_count / total_frames

            # Alert if bad posture is 50%+ of last 10 seconds
            if bad_fraction >= self.bad_avg_threshold:
                alerts['bad_alert'] = True

            # Alert if warning+bad posture is 60%+ of last 10 seconds (and not already bad alert)
            if not alerts['bad_alert'] and warning_or_bad_fraction >= self.warning_avg_threshold:
                alerts['warning_alert'] = True

        # Alert if no face for over 30 seconds
        if self.no_face_duration >= self.no_face_threshold:
            alerts['no_face_alert'] = True

        return posture_status, face_size, bbox, is_face_detected, alerts

    def draw_feedback(self, frame, posture_status, face_size, bbox):
        """Draw visual feedback on frame."""
        frame_height, frame_width, _ = frame.shape

        # Draw status text
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.5
        thickness = 3

        if (face_size):
            if posture_status == 'good':
                color = (0, 255, 0)  # Green
                text = "GOOD POSTURE"
            elif posture_status == 'warning':
                color = (0, 165, 255)  # Orange
                text = "WARNING: Move back"
            else:  # bad
                color = (0, 0, 255)  # Red
                text = "BAD POSTURE: Too close!"
        else:
            color = (0, 0, 255)  # Red
            text = "not detected"



        # Draw status text at top
        cv2.putText(frame, text, (50, 100), font, font_scale, color, thickness)

        # Draw face size info
        if face_size is not None:
            face_size_text = f"Face size: {face_size:.2%}"
            cv2.putText(frame, face_size_text, (50, 200), font, 1, (255, 255, 255), 2)

        # Draw bounding box if face detected
        if bbox is not None:
            x_min = int(bbox.xmin * frame_width)
            y_min = int(bbox.ymin * frame_height)
            x_max = int((bbox.xmin + bbox.width) * frame_width)
            y_max = int((bbox.ymin + bbox.height) * frame_height)

            # Ensure coordinates are within bounds
            x_min = max(0, x_min)
            y_min = max(0, y_min)
            x_max = min(frame_width, x_max)
            y_max = min(frame_height, y_max)

            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color, 3)

        # Draw threshold indicator bar at bottom
        bar_height = 30
        bar_width = frame_width
        bar_y = frame_height - bar_height

        # Background
        cv2.rectangle(frame, (0, bar_y), (bar_width, frame_height), (50, 50, 50), -1)

        # Threshold markers
        threshold_x = int(self.distance_threshold * bar_width)
        warning_x = int(self.distance_threshold * 0.75 * bar_width)

        # Draw zones
        cv2.rectangle(frame, (0, bar_y), (warning_x, frame_height), (0, 255, 0), -1)
        cv2.rectangle(frame, (warning_x, bar_y), (threshold_x, frame_height), (0, 165, 255), -1)
        cv2.rectangle(frame, (threshold_x, bar_y), (bar_width, frame_height), (0, 0, 255), -1)

        # Labels
        cv2.putText(frame, "Good", (10, frame_height - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, "Warning", (warning_x + 10, frame_height - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
        cv2.putText(frame, "Bad", (threshold_x + 10, frame_height - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        return frame

    def alert(self, posture_status):
        """Play alert sound for bad posture."""
        if posture_status == 'bad' and self.bad_posture_counter >= self.bad_posture_threshold:
            try:
                # Windows beep: frequency=1000Hz, duration=200ms
                winsound.Beep(1000, 200)
            except Exception as e:
                print(f"Could not play sound: {e}")


def main():
    print("Posture Detector - Press 'q' to quit")
    print("=" * 50)

    detector = PostureDetector(distance_threshold=0.5)
    # Use DirectShow backend for Windows camera access
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print("Error: Could not open webcam")
        return

    # Get video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Use default FPS if camera doesn't report it
    if fps == 0:
        fps = 30

    print(f"Camera resolution: {frame_width}x{frame_height}")
    print(f"FPS: {fps}")
    print("=" * 50)

    frame_count = 0
    bad_posture_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        # Flip frame for better selfie view
        frame = cv2.flip(frame, 1)

        # Detect posture
        posture_status, face_size, bbox, is_face_detected, alerts = detector.detect_posture(frame)

        # Draw feedback
        frame = detector.draw_feedback(frame, posture_status, face_size, bbox)

        # Play alert if bad posture
        detector.alert(posture_status)

        # Track bad posture duration
        if posture_status == 'bad':
            bad_posture_time += 1
        else:
            bad_posture_time = 0

        # Display frame
        cv2.imshow('Posture Detector', frame)

        frame_count += 1
        if frame_count % 30 == 0:  # Print stats every 30 frames
            if is_face_detected:
                print(f"Frame {frame_count} | Status: {posture_status.upper():8} | Face Size: {face_size:.2%} | Bad Posture Time: {bad_posture_time/fps:.1f}s")
            else:
                print(f"Frame {frame_count} | Status: NO FACE DETECTED")

        # Exit on 'q' key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Posture detector closed")


if __name__ == "__main__":
    main()
