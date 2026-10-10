import os
import cv2
import av
import numpy as np
import mediapipe as mp
import threading
import time
from streamlit_webrtc import VideoProcessorBase
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from detectors.squat import SquatDetector
from detectors.pushup import PushUpDetector
from detectors.biceps_curl import BicepsCurlDetector
from detectors.shoulder_press import ShoulderPressDetector
from detectors.lunges import LungesDetector
from services.vision.activity_classifier import ActivityClassifier
from services.config.workout_config import POSE_CONNECTIONS
from services.config.workout_config import AUTO_DETECT_OPTION


class VideoProcessorClass(VideoProcessorBase):
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_metrics = None
        self._exercise_type = AUTO_DETECT_OPTION
        self._activity_classifier = ActivityClassifier()

        models_dir = os.path.join(os.getcwd(), "ml_models")
        lite_model_path = os.path.join(models_dir, "pose_landmarker_lite.task")
        full_model_path = os.path.join(models_dir, "pose_landmarker_full.task")
        model_path = lite_model_path if os.path.isfile(lite_model_path) else full_model_path
        base_option = python.BaseOptions(model_asset_path=model_path)

        options = vision.PoseLandmarkerOptions(
            base_options=base_option,
            running_mode=vision.RunningMode.VIDEO,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_segmentation_masks=False
        )

        self._landmarker = vision.PoseLandmarker.create_from_options(options)

        self._detectors = {
            "Squats": SquatDetector(),
            "Push-ups": PushUpDetector(),
            "Biceps Curls (Dumbbell)": BicepsCurlDetector(),
            "Shoulder Press": ShoulderPressDetector(),
            "Lunges": LungesDetector(),
        }

        self._frame_timestamps_ms = 0
    
    def set_latest_metrics(self, metrics):
        with self._lock:
            self._latest_metrics = metrics.copy()

    def get_latest_metrics(self):
        with self._lock:
            return None if self._latest_metrics is None else self._latest_metrics.copy()
        
    def set_exercise(self, exercise_type):
        with self._lock:
            self._exercise_type = exercise_type

    def get_exercise(self):
        with self._lock:
            return self._exercise_type
        
    def _draw_skeleton(self, img, landmarks):
        h, w = img.shape[:2]

        for start_idx, end_idx in POSE_CONNECTIONS:
            p1 = landmarks[start_idx]
            p2 = landmarks[end_idx]

            if p1.visibility > 0.5 and p2.visibility > 0.5:
                cv2.line(
                    img,
                    (int(p1.x * w), int(p1.y * h)),
                    (int(p2.x * w), int(p2.y * h)),
                    (0, 255, 0),
                    4
                )
        
        for lm in landmarks:
            if lm.visibility > 0.5:
                cv2.circle(
                    img, 
                    (int(lm.x * w), int(lm.y * h)),
                    4,
                    (255, 0, 0),
                    -1
                )
            
    def _draw_no_pose_warnings(self, img):
        cv2.putText(
            img,
            "NO POSE DETECTED",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        cv2.putText(
            img,
            "STEP BACK - KEEP YOUR FULL BODY IN FRAME",
            (30, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    def _draw_overlays(self, img, metrics, ex_type):
        if ex_type == "Squats":
            self._draw_squats_overlays(img, metrics)
        elif ex_type == "Push-ups":
            self._draw_pushup_overlays(img, metrics)
        elif ex_type == "Biceps Curls (Dumbbell)":
            self._draw_curl_overlays(img, metrics)
        elif ex_type == "Shoulder Press":
            self._draw_press_overlays(img, metrics)
        elif ex_type == "Lunges":
            self._draw_lunge_overlays(img, metrics)

    def _draw_activity_overlay(self, img, metrics):
        activity = metrics.get("exercise_type", "Adjust position")
        category = metrics.get("activity_category", "")
        cv2.putText(
            img,
            f"DETECTED: {activity.upper()}",
            (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (80, 240, 210),
            2,
            cv2.LINE_AA,
        )

        if category == "Exercise" and metrics.get("reps") is not None:
            detail = f"REPS: {metrics['reps']}"
        elif category == "Yoga pose":
            detail = f"HOLD: {int(metrics.get('current_hold_seconds', 0))}s"
        else:
            detail = category.upper()

        cv2.putText(
            img,
            detail,
            (20, 86),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (80, 240, 210),
            2,
            cv2.LINE_AA,
        )

        step = metrics.get("sun_salutation_step", 0)
        cycles = metrics.get("sun_salutation_cycles", 0)
        if step:
            cv2.putText(
                img,
                f"SURYA NAMASKAR FLOW: {step}/12",
                (20, 122),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (80, 240, 210),
                2,
                cv2.LINE_AA,
            )
        if cycles:
            cv2.putText(
                img,
                f"COMPLETED CYCLES: {cycles}",
                (20, 158),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (80, 240, 210),
                2,
                cv2.LINE_AA,
            )


    def _draw_squats_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"DEPTH: {metrics['depth_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )
    
    def _draw_pushup_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"BODY: {metrics['body_alignment']} | HIP: {metrics['hip_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_curl_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"SWING: {metrics['swing_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_press_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"EXT: {metrics['extension_status']} | BACK: {metrics['back_arch_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def _draw_lunge_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        cv2.putText(
            img,
            f"BALANCE: {metrics['balance_status']}",
            (20, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

    def recv(self, frame):
        image = np.asarray(
            cv2.flip(frame.to_ndarray(format="bgr24"), 1),
            dtype=np.uint8
        )
        try:
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            )

            # VIDEO mode requires strictly increasing timestamps. Use capture
            # processing time instead of assuming a fixed frame rate.
            self._frame_timestamps_ms = max(
                self._frame_timestamps_ms + 1,
                int(time.monotonic() * 1000),
            )
            result = self._landmarker.detect_for_video(mp_image, self._frame_timestamps_ms)

            if result.pose_landmarks:
                landmarks = result.pose_landmarks[0]
                self._draw_skeleton(image, landmarks)

                selected_exercise = self.get_exercise()
                if selected_exercise == AUTO_DETECT_OPTION:
                    activity_metrics = self._activity_classifier.process(landmarks)
                    ex_type = activity_metrics["exercise_type"]
                else:
                    ex_type = selected_exercise
                    activity_metrics = {
                        "activity_key": ex_type,
                        "exercise_type": ex_type,
                        "activity_category": "Exercise",
                        "confidence": 1.0,
                        "hold_seconds": 0.0,
                        "current_hold_seconds": 0.0,
                        "sun_salutation_step": 0,
                        "sun_salutation_cycles": 0,
                    }

                detector = self._detectors.get(ex_type)
                metrics = detector.process(landmarks) if detector else {"reps": 0}
                metrics.update(activity_metrics)
                metrics["exercise_type"] = ex_type
                metrics["pose_detected"] = True

                if detector:
                    self._draw_overlays(image, metrics, ex_type)
                self._draw_activity_overlay(image, metrics)
                self.set_latest_metrics(metrics)
            else:
                self._draw_no_pose_warnings(image)
                with self._lock:
                    if self._latest_metrics is not None:
                        self._latest_metrics["pose_detected"] = False
                    else:
                        self._latest_metrics = {"pose_detected": False}
        except Exception as error:
            # Always return the raw camera frame so a detector problem cannot
            # leave the received video element blank.
            cv2.putText(
                image,
                f"LIVE CAMERA - ANALYSIS ERROR: {type(error).__name__}",
                (20, 42),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 80, 255),
                2,
                cv2.LINE_AA,
            )
            self.set_latest_metrics({
                "pose_detected": False,
                "processor_error": type(error).__name__,
            })

        return av.VideoFrame.from_ndarray(image, format="bgr24")
    
