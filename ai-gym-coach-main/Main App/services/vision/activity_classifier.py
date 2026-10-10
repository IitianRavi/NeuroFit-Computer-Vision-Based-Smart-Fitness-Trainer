"""Best-effort activity labels from MediaPipe pose landmarks.

This uses visible body posture only; it cannot verify breathing or fine hand
gestures that the pose model does not expose.
"""

import math
import time


EXERCISE_LABELS = {
    "squats": "Squats",
    "pushups": "Push-ups",
    "curls": "Biceps Curls (Dumbbell)",
    "press": "Shoulder Press",
    "lunges": "Lunges",
}

YOGA_LABELS = {
    "mountain": "Mountain Pose",
    "upward_salute": "Hasta Uttanasana (Raised Arms)",
    "prayer": "Pranamasana (Prayer Pose)",
    "forward_fold": "Padahastasana (Standing Forward Fold)",
    "lunge": "Ashwa Sanchalanasana (Equestrian Pose)",
    "plank": "Dandasana (Plank Pose)",
    "ashtanga": "Ashtanga Namaskara (Eight-Limbed Pose)",
    "chaturanga": "Chaturanga",
    "cobra": "Bhujangasana (Cobra Pose)",
    "downward_dog": "Parvatasana (Inverted-V Pose)",
    "tree": "Tree Pose",
    "warrior": "Warrior II",
    "triangle": "Triangle Pose",
    "child": "Child's Pose",
    "seated_breathing": "Seated Breathing",
    "anulom_vilom": "Anulom Vilom Setup",
}

SUN_START_KEYS = {"mountain", "prayer"}


def _point(landmarks, index):
    point = landmarks[index]
    return point.x, point.y


def _angle(landmarks, first, middle, last):
    ax, ay = _point(landmarks, first)
    bx, by = _point(landmarks, middle)
    cx, cy = _point(landmarks, last)
    first_vector = (ax - bx, ay - by)
    last_vector = (cx - bx, cy - by)
    first_length = math.hypot(*first_vector)
    last_length = math.hypot(*last_vector)
    if first_length == 0 or last_length == 0:
        return 0.0
    cosine = sum(a * b for a, b in zip(first_vector, last_vector)) / (first_length * last_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _midpoint_y(landmarks, first, second):
    return (landmarks[first].y + landmarks[second].y) / 2


def _midpoint_x(landmarks, first, second):
    return (landmarks[first].x + landmarks[second].x) / 2


def body_dx_for_floor(landmarks):
    return abs(_midpoint_x(landmarks, 11, 12) - _midpoint_x(landmarks, 27, 28))


def _pose_coaching(key, landmarks):
    """Return conservative coaching cues from measurable landmark alignment."""
    cues = {
        "prayer": "Good Pranamasana. Stand tall, relax your shoulders, and keep your palms together.",
        "upward_salute": "Nice raised-arms pose. Lengthen upward and avoid forcing your lower back.",
        "forward_fold": "Good forward fold. Let your torso relax and keep your weight balanced over both feet.",
        "lunge": "Good low lunge. Keep your front knee aligned over your ankle and chest lifted.",
        "plank": "Strong Dandasana. Keep your shoulders, hips, and ankles in one steady line.",
        "ashtanga": "Good eight-limbed pose. Lower with control and keep your neck comfortable.",
        "chaturanga": "Good controlled transition. Keep elbows close and shoulders supported.",
        "cobra": "Nice Bhujangasana. Open your chest gently and keep your shoulders away from your ears.",
        "downward_dog": "Good Parvatasana. Press the floor away and lengthen your spine.",
    }
    if key not in cues:
        return {}

    knee_mean = (
        _angle(landmarks, 23, 25, 27) + _angle(landmarks, 24, 26, 28)
    ) / 2
    elbow_mean = (
        _angle(landmarks, 11, 13, 15) + _angle(landmarks, 12, 14, 16)
    ) / 2
    hip_mean = (
        _angle(landmarks, 11, 23, 25) + _angle(landmarks, 12, 24, 26)
    ) / 2

    issue = None
    if key == "forward_fold" and knee_mean < 140:
        issue = "Soften the knee bend slightly and fold from your hips; do not force your hands to the floor."
    elif key == "upward_salute" and elbow_mean < 135:
        issue = "Lengthen your arms upward without locking your elbows or arching your lower back."
    elif key == "plank":
        shoulder_y = _midpoint_y(landmarks, 11, 12)
        hip_y = _midpoint_y(landmarks, 23, 24)
        ankle_y = _midpoint_y(landmarks, 27, 28)
        if abs(hip_y - (shoulder_y + ankle_y) / 2) > 0.12:
            issue = "Bring your hips in line with your shoulders and ankles; avoid sagging or piking."
    elif key == "ashtanga" and elbow_mean > 132:
        issue = "Bend your elbows more and lower knees, chest, and chin with control."
    elif key == "downward_dog" and hip_mean < 115:
        issue = "Push your hips back and up to lengthen your spine; bend your knees if needed."

    return {"form_issue": issue, "coach_praise": cues[key]}


class ActivityClassifier:
    """Classify common gym movements and yoga postures with temporal smoothing."""

    MIN_VISIBILITY = 0.35
    # Four frames gives a quick (~0.2 s at 20 FPS) stable pose without flicker.
    STABLE_FRAMES = 4
    MOVEMENT_LOCK_SECONDS = 3.0

    def __init__(self):
        self.current_key = "unknown"
        self._candidate_key = None
        self._candidate_frames = 0
        self._last_frame_at = None
        self._last_change_at = time.monotonic()
        self._current_hold = 0.0
        self._hold_totals = {}
        self._last_flow_key = None
        self._flow_step = 0
        self._sun_salutations = 0

    def _raw_key(self, landmarks):
        required = (11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28)
        if any(landmarks[index].visibility < self.MIN_VISIBILITY for index in required):
            return "unknown"

        left_knee = _angle(landmarks, 23, 25, 27)
        right_knee = _angle(landmarks, 24, 26, 28)
        left_elbow = _angle(landmarks, 11, 13, 15)
        right_elbow = _angle(landmarks, 12, 14, 16)
        left_hip = _angle(landmarks, 11, 23, 25)
        right_hip = _angle(landmarks, 12, 24, 26)

        shoulder_y = _midpoint_y(landmarks, 11, 12)
        hip_y = _midpoint_y(landmarks, 23, 24)
        knee_y = _midpoint_y(landmarks, 25, 26)
        ankle_y = _midpoint_y(landmarks, 27, 28)
        shoulder_x = _midpoint_x(landmarks, 11, 12)
        hip_x = _midpoint_x(landmarks, 23, 24)
        shoulder_span = max(0.08, abs(landmarks[11].x - landmarks[12].x))
        elbow_span = abs(landmarks[13].x - landmarks[14].x)
        knee_mean = (left_knee + right_knee) / 2
        elbow_mean = (left_elbow + right_elbow) / 2
        standing = shoulder_y < hip_y < ankle_y and ankle_y - shoulder_y > 0.25
        arms_overhead = (
            landmarks[15].y < landmarks[11].y - 0.04
            and landmarks[16].y < landmarks[12].y - 0.04
        )
        arms_wide = (
            abs(landmarks[15].y - shoulder_y) < 0.14
            and abs(landmarks[16].y - shoulder_y) < 0.14
            and abs(landmarks[15].x - landmarks[16].x)
            > abs(landmarks[11].x - landmarks[12].x) * 1.3
        )
        asymmetric_legs = min(left_knee, right_knee) < 125 and max(left_knee, right_knee) > 145

        nose_x, nose_y = _point(landmarks, 0)
        hand_near_face = min(
            math.hypot(landmarks[15].x - nose_x, landmarks[15].y - nose_y),
            math.hypot(landmarks[16].x - nose_x, landmarks[16].y - nose_y),
        ) < 0.16
        seated = (
            knee_mean < 135
            and abs(hip_y - knee_y) < 0.12
            and ankle_y - hip_y < 0.30
            and shoulder_y < hip_y
        )

        # Seated postures are checked before standing yoga positions.
        if seated and hand_near_face:
            return "anulom_vilom"
        if seated:
            return "seated_breathing"

        # Inverted V: hips are the highest point, with straight arms and legs.
        if (
            hip_y < shoulder_y - 0.04
            and hip_y < knee_y - 0.02
            and (left_hip + right_hip) / 2 > 95
            and knee_mean > 135
        ):
            return "downward_dog"

        # Cobra lifts the chest while the hips and extended legs stay near the floor.
        if (
            shoulder_y < hip_y - 0.04
            and abs(hip_y - ankle_y) < 0.18
            and body_dx_for_floor(landmarks) > 0.22
            and knee_mean > 145
        ):
            return "cobra"

        # In Ashtanga Namaskara the knees are grounded and the elbows bend as
        # chest/chin lower; this separates it from the straight-body Dandasana.
        if (
            body_dx_for_floor(landmarks) > 0.22
            and elbow_mean < 140
            and knee_mean < 160
            and shoulder_y > hip_y - 0.10
        ):
            return "ashtanga"

        # Floor poses have the shoulder, hip and ankle nearly on one horizontal line.
        body_dx = abs(_midpoint_x(landmarks, 11, 12) - _midpoint_x(landmarks, 27, 28))
        body_dy = abs(shoulder_y - ankle_y)
        horizontal_body = body_dx > 0.28 and body_dy < 0.18
        if horizontal_body:
            if elbow_mean < 95:
                return "chaturanga"
            if elbow_mean < 135:
                return "pushups"
            if shoulder_y < hip_y - 0.05 and knee_mean > 145:
                return "cobra"
            if knee_mean > 145:
                return "plank"

        # Folded floor posture: hips stay high while the head and hands move low.
        if (
            hip_y < knee_y - 0.03
            and shoulder_y > hip_y + 0.03
            and knee_mean < 145
            and abs(hip_x - shoulder_x) < 0.24
        ):
            return "child"

        hands_to_floor = min(landmarks[15].y, landmarks[16].y) > hip_y + 0.18
        if min(left_knee, right_knee) < 125 and (arms_overhead or hands_to_floor):
            return "lunge"

        if standing:
            wrist_span = abs(landmarks[15].x - landmarks[16].x)
            wrists_at_chest = (
                wrist_span < shoulder_span * 0.65
                and shoulder_y < _midpoint_y(landmarks, 15, 16) < hip_y
            )
            if wrists_at_chest and knee_mean > 145:
                return "prayer"

            if asymmetric_legs and arms_wide:
                return "warrior"

            if asymmetric_legs:
                bent_side = 0 if left_knee < right_knee else 1
                lifted_ankle = landmarks[27 if bent_side == 0 else 28].y
                support_ankle = landmarks[28 if bent_side == 0 else 27].y
                if lifted_ankle < support_ankle - 0.07:
                    return "tree"
                if arms_overhead or hands_to_floor:
                    return "lunge"
                return "lunges"

            feet_wide = abs(landmarks[27].x - landmarks[28].x) > 0.30
            torso_tilt = abs(shoulder_y - hip_y)
            hand_low = min(landmarks[15].y, landmarks[16].y) > hip_y - 0.04
            if feet_wide and knee_mean > 145 and torso_tilt > 0.12 and hand_low:
                return "triangle"

            if 100 < knee_mean < 148 and (
                arms_overhead or min(landmarks[15].y, landmarks[16].y) < shoulder_y
            ):
                return "chair"

            if arms_overhead:
                wrist_span = abs(landmarks[15].x - landmarks[16].x)
                if knee_mean > 145 and wrist_span < shoulder_span * 0.9:
                    return "upward_salute"
                return "press"

            if (
                elbow_mean < 125
                and elbow_span > shoulder_span * 1.15
                and min(landmarks[15].y, landmarks[16].y) < hip_y
            ):
                return "press"

            if 100 < knee_mean < 148:
                return "squats"
            if knee_mean <= 100:
                return "squats"

            # Curls need a clear elbow bend while the torso and legs are upright.
            if elbow_mean < 135:
                return "curls"
            if elbow_mean < 150 and min(landmarks[15].y, landmarks[16].y) < hip_y:
                return "curls"
            return "mountain"

        # A forward fold often does not satisfy the standing check because the torso bends.
        if (
            shoulder_y > hip_y + 0.04
            and ankle_y > hip_y
            and (left_hip + right_hip) / 2 < 125
        ):
            return "forward_fold"

        return "unknown"

    def _smooth(self, raw_key, now):
        # Keep rep detectors active through the return-to-start phase after a movement
        # was recognized; otherwise a curl can be relabeled as standing mid-rep.
        rep_keys = {"squats", "pushups", "curls", "press", "lunges"}
        if (
            self.current_key in rep_keys
            and raw_key in {"unknown", "mountain"}
            and now - self._last_change_at < self.MOVEMENT_LOCK_SECONDS
        ):
            raw_key = self.current_key

        if raw_key == self.current_key:
            self._candidate_key = None
            self._candidate_frames = 0
            return self.current_key

        if raw_key != self._candidate_key:
            self._candidate_key = raw_key
            self._candidate_frames = 1
        else:
            self._candidate_frames += 1

        if self._candidate_frames >= self.STABLE_FRAMES:
            self.current_key = raw_key
            self._last_change_at = now
            self._current_hold = 0.0
            self._candidate_key = None
            self._candidate_frames = 0
        return self.current_key

    def _update_sun_sequence(self, key):
        if key == self._last_flow_key:
            return
        step = self._flow_step

        # Standard 12 posture sequence shown in the supplied charts:
        # Pranamasana, Hasta Uttanasana, Padahastasana, Ashwa Sanchalanasana,
        # Dandasana, Ashtanga Namaskara, Bhujangasana, Parvatasana, then repeat
        # the lunge, fold, raised arms and prayer postures.
        if step == 0:
            if key in SUN_START_KEYS:
                self._flow_step = 1  # Prayer / starting position
            elif key == "upward_salute":
                self._flow_step = 2  # Started after the opening prayer
        elif step == 1 and key == "upward_salute":
            self._flow_step = 2
        elif step == 2 and key == "forward_fold":
            self._flow_step = 3
        elif step == 3 and key == "lunge":
            self._flow_step = 4
        elif step == 4 and key in {"plank", "pushups"}:
            self._flow_step = 5
        elif step == 4 and key == "ashtanga":
            self._flow_step = 6
        elif step == 5 and key == "ashtanga":
            self._flow_step = 6
        elif step == 5 and key == "chaturanga":
            self._flow_step = 6
        elif step in {5, 6} and key == "cobra":
            self._flow_step = 7
        elif step == 7 and key == "downward_dog":
            self._flow_step = 8
        elif step == 8 and key == "lunge":
            self._flow_step = 9
        elif step == 9 and key == "forward_fold":
            self._flow_step = 10
        elif step == 10 and key == "upward_salute":
            self._flow_step = 11
        elif step == 10 and key == "prayer":
            # Raised-arms posture can be missed by a camera at the frame edge.
            self._flow_step = 12
            self._sun_salutations += 1
        elif step == 11 and key == "prayer":
            self._flow_step = 12
            self._sun_salutations += 1
        elif step == 12 and key == "upward_salute":
            self._flow_step = 2
        elif step == 12 and key == "forward_fold":
            # Recover if both the opening prayer and raised arms were missed.
            self._flow_step = 3
        self._last_flow_key = key

    def process(self, landmarks):
        now = time.monotonic()
        delta = 0.0 if self._last_frame_at is None else min(0.2, max(0.0, now - self._last_frame_at))
        self._last_frame_at = now

        raw_key = self._raw_key(landmarks)
        key = self._smooth(raw_key, now)
        if key in YOGA_LABELS:
            self._current_hold += delta
            self._hold_totals[key] = self._hold_totals.get(key, 0.0) + delta
        else:
            self._current_hold = 0.0

        self._update_sun_sequence(key)
        coaching = _pose_coaching(key, landmarks) if key in YOGA_LABELS else {}

        if key in EXERCISE_LABELS:
            label = EXERCISE_LABELS[key]
            category = "Exercise"
        elif key in YOGA_LABELS:
            label = YOGA_LABELS[key]
            category = "Yoga pose"
        else:
            label = "Adjust position"
            category = "Waiting for a clear pose"

        return {
            "activity_key": key,
            "exercise_type": label,
            "activity_category": category,
            "confidence": 1.0 if key != "unknown" else 0.0,
            "hold_seconds": self._hold_totals.get(key, 0.0),
            "current_hold_seconds": self._current_hold,
            "sun_salutation_step": self._flow_step,
            "sun_salutation_cycles": self._sun_salutations,
            "sun_salutation_pose": (
                YOGA_LABELS.get(key, "") if self._flow_step else ""
            ),
            **coaching,
        }
