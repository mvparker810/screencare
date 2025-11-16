import cv2
import mediapipe as mp
import numpy as np
import time
import winsound  # For Windows beeping alerts
from collections import deque

# Initialize MediaPipe Face Detection and Face Mesh
mp_face_detection = mp.solutions.face_detection
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils

class PostureDetector:
    def __init__(self, distance_threshold=0.18, smoothing_frames=10):
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

        # Initialize MediaPipe Face Mesh for eye blinking detection
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            min_detection_confidence=0.5
        )

        # Eye blink tracking (following the BlinkCounter pattern)
        self.blink_count = 0  # Total blinks detected
        self.frame_counter = 0  # Consecutive frames with eyes closed
        self.ear_threshold = 0.3  # Eye aspect ratio threshold
        self.consec_frames = 4  # Minimum consecutive frames to confirm blink

        # Eye landmarks for visualization and EAR calculation
        self.RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
        self.LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
        self.RIGHT_EYE_EAR = [33, 159, 158, 133, 153, 145]
        self.LEFT_EYE_EAR = [362, 380, 374, 263, 386, 385]

        # Colors for visualization
        self.GREEN_COLOR = (86, 241, 13)  # Eyes open
        self.RED_COLOR = (30, 46, 209)    # Eyes closed

        # Blink rate tracking (for low blink rate warning)
        self.blink_timestamps = deque()  # Track when blinks occur
        self.blink_rate_check_interval = 60  # Check blink rate every 60 seconds
        self.last_blink_rate_check = time.time()
        self.absolute_min_blinks_per_minute = 7  # Warn if below this threshold
        self.min_blinks_per_minute = 11
        self.low_blink_rate_alert_triggered = False  # Prevent repeated alerts

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

    def eye_aspect_ratio(self, eye_indices, landmarks):
        """
        Calculate Eye Aspect Ratio (EAR) for blink detection.
        Uses the formula: EAR = (A + B) / (2.0 * C)
        where A, B are vertical distances and C is horizontal distance.

        Args:
            eye_indices: List of 6 landmark indices [0=inner, 1=top, 2=top2, 3=outer, 4=bottom2, 5=bottom]
            landmarks: List of all facial landmarks with x,y coordinates
        """
        # A = distance between top landmarks
        A = np.linalg.norm(np.array(landmarks[eye_indices[1]]) - np.array(landmarks[eye_indices[5]]))
        # B = distance between top2 and bottom2 landmarks
        B = np.linalg.norm(np.array(landmarks[eye_indices[2]]) - np.array(landmarks[eye_indices[4]]))
        # C = distance between inner and outer corners
        C = np.linalg.norm(np.array(landmarks[eye_indices[0]]) - np.array(landmarks[eye_indices[3]]))

        # Calculate EAR
        ear = (A + B) / (2.0 * C)
        return ear

    def update_blink_count(self, ear):
        """
        Update blink counter based on current eye aspect ratio.
        Follows the reference BlinkCounter pattern exactly.

        Args:
            ear (float): Current eye aspect ratio

        Returns:
            bool: True if a new blink was detected, False otherwise
        """
        blink_detected = False
        if ear < self.ear_threshold:
            self.frame_counter += 1
        else: 
            if self.frame_counter >= self.consec_frames:
                self.blink_count += 1
                blink_detected = True
                # Record timestamp for blink rate tracking
                self.blink_timestamps.append(time.time())
                print(f"👁️ BLINK DETECTED! (Total: {self.blink_count})")
            self.frame_counter = 0

        return blink_detected

    def set_colors(self, ear):
        """
        Determine visualization color based on eye aspect ratio.

        Args:
            ear (float): Current eye aspect ratio

        Returns:
            tuple: BGR color values
        """
        return self.RED_COLOR if ear < self.ear_threshold else self.GREEN_COLOR

    def detect_blinks(self, frame_rgb, frame_bgr):
        """
        Detect eye blinks using Face Mesh landmarks.
        Follows the BlinkCounter pattern from the reference script.

        Args:
            frame_rgb: Frame in RGB format for Face Mesh processing
            frame_bgr: Frame in BGR format for visualization
        """
        results = self.face_mesh.process(frame_rgb)

        if not results.multi_face_landmarks:
            # Debug: Face Mesh not detecting landmarks
            if not hasattr(self, '_debug_logged'):
                print("[BLINK] Face Mesh not detecting landmarks - checking if face is visible and well-lit")
                self._debug_logged = True
            return False

        # Reset debug flag when landmarks are detected
        self._debug_logged = False

        landmarks_list = []
        for landmark in results.multi_face_landmarks[0].landmark:
            landmarks_list.append([landmark.x, landmark.y])

        # Calculate Eye Aspect Ratio for both eyes
        right_ear = self.eye_aspect_ratio(self.RIGHT_EYE_EAR, landmarks_list)
        left_ear = self.eye_aspect_ratio(self.LEFT_EYE_EAR, landmarks_list)
        ear = (right_ear + left_ear) / 2.0

        # Determine color based on EAR
        color = self.set_colors(ear)

        # Draw eye landmarks on the frame
        self._draw_eye_landmarks(frame_bgr, landmarks_list, self.RIGHT_EYE, color)
        self._draw_eye_landmarks(frame_bgr, landmarks_list, self.LEFT_EYE, color)

        # Debug: Print EAR values every 30 frames
        if not hasattr(self, '_frame_counter_debug'):
            self._frame_counter_debug = 0
        self._frame_counter_debug += 1

        if self._frame_counter_debug % 30 == 0:
            print(f"[EAR] R:{right_ear:.3f} L:{left_ear:.3f} Avg:{ear:.3f} Threshold:{self.ear_threshold} Frame_cnt:{self.frame_counter}")

        # Update blink detection using the update_blink_count method
        blink_detected = self.update_blink_count(ear)

        return blink_detected

    def _draw_eye_landmarks(self, frame, landmarks, eye_indices, color):
        """
        Draw landmarks around the eyes on the frame.

        Args:
            frame: Video frame to draw on
            landmarks: List of facial landmarks (normalized coordinates)
            eye_indices: Indices of landmarks for one eye
            color: BGR color values for drawing
        """
        frame_height, frame_width, _ = frame.shape
        for idx in eye_indices:
            if idx < len(landmarks):
                x = int(landmarks[idx][0] * frame_width)
                y = int(landmarks[idx][1] * frame_height)
                cv2.circle(frame, (x, y), 2, color, -1)

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

        # Detect blinks (pass both RGB for processing and BGR for visualization)
        self.detect_blinks(frame_rgb, frame)

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
            'bad_alert': False,
            'low_blink_rate_alert': False,
            'serious_eye_strain': False
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

        # Check blink rate every 60 seconds
        if current_time - self.last_blink_rate_check >= self.blink_rate_check_interval:
            # Remove timestamps older than 60 seconds
            cutoff_time = current_time - self.blink_rate_check_interval
            while self.blink_timestamps and self.blink_timestamps[0] < cutoff_time:
                self.blink_timestamps.popleft()

            # Calculate blinks per minute (normalize to 60 seconds)
            blinks_in_interval = len(self.blink_timestamps)
            blinks_per_minute = blinks_in_interval  # Already in 60-second window

            # Check if below threshold
            if blinks_per_minute < self.absolute_min_blinks_per_minute:
                alerts['serious_eye_strain'] = True
                self.low_blink_rate_alert_triggered = True
                print(f"⚠️  LOW BLINK RATE - {blinks_per_minute} blinks/min (threshold: {self.absolute_min_blinks_per_minute})")
            elif blinks_per_minute < self.min_blinks_per_minute: 
                alerts['low_blink_rate_alert'] = True
                self.low_blink_rate_alert_triggered = True
                print(f"⚠️  LOW BLINK RATE - {blinks_per_minute} blinks/min (threshold: {self.min_blinks_per_minute})")
            else:# Reset trigger flag when blink rate recovers
                self.low_blink_rate_alert_triggered = False

            self.last_blink_rate_check = current_time

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

        # Draw blink count
        blink_count_text = f"👁️ Blinks: {self.blink_count}"
        cv2.putText(frame, blink_count_text, (50, 250), font, 1, (100, 200, 255), 2)

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
