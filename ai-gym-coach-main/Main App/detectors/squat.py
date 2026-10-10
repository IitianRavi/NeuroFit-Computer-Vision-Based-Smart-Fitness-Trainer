from core.base_exercise import BaseExercise


class SquatDetector(BaseExercise):
    DOWN_THRESHOLD = 120
    DEPTH_THRESHOLD = 100
    UP_THRESHOLD = 150
    MIN_VISIBILITY = 0.5

    LEFT_HIP = 23
    LEFT_KNEE = 25
    LEFT_ANKLE = 27
    RIGHT_HIP = 24
    RIGHT_KNEE = 26
    RIGHT_ANKLE = 28
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12

    def __init__(self):
        super().__init__()
        self._depth_reached = False
        self._rep_started = False

    def reset(self):
        self.reps = 0
        self.stage = "up"
        self._depth_reached = False
        self._rep_started = False

    def process(self, landmarks):
        left_knee_angle = self.calculate_angle(
            self.get_point(landmarks, self.LEFT_HIP),
            self.get_point(landmarks, self.LEFT_KNEE),
            self.get_point(landmarks, self.LEFT_ANKLE)
        )

        right_knee_angle = self.calculate_angle(
            self.get_point(landmarks, self.RIGHT_HIP),
            self.get_point(landmarks, self.RIGHT_KNEE),
            self.get_point(landmarks, self.RIGHT_ANKLE)
        )

        left_vis = sum(landmarks[index].visibility for index in (
            self.LEFT_HIP, self.LEFT_KNEE, self.LEFT_ANKLE, self.LEFT_SHOULDER
        ))
        right_vis = sum(landmarks[index].visibility for index in (
            self.RIGHT_HIP, self.RIGHT_KNEE, self.RIGHT_ANKLE, self.RIGHT_SHOULDER
        ))

        if left_vis >= right_vis:
            knee_angle = left_knee_angle
            hip_idx, knee_idx, ankle_idx, shoulder_idx = self.LEFT_HIP, self.LEFT_KNEE, self.LEFT_ANKLE, self.LEFT_SHOULDER
        else:
            knee_angle = right_knee_angle
            hip_idx, knee_idx, ankle_idx, shoulder_idx = self.RIGHT_HIP, self.RIGHT_KNEE, self.RIGHT_ANKLE, self.RIGHT_SHOULDER

        back_angle = self.calculate_angle(
            self.get_point(landmarks, shoulder_idx),
            self.get_point(landmarks, hip_idx),
            self.get_point(landmarks, knee_idx)
        )

        key_landmark_visible = all(
            landmarks[index].visibility >= self.MIN_VISIBILITY
            for index in (hip_idx, knee_idx, ankle_idx, shoulder_idx)
        )

        if key_landmark_visible:
            if knee_angle <= self.DOWN_THRESHOLD:
                self.stage = "down"
                self._rep_started = True

            if knee_angle <= self.DEPTH_THRESHOLD:
                self._depth_reached = True

            if knee_angle >= self.UP_THRESHOLD and self.stage == "down":
                if self._rep_started:
                    self.reps += 1
                self.stage = "up"
                self._rep_started = False
                self._depth_reached = False

        if self.stage == "down":
            depth_status = "GOOD DEPTH" if self._depth_reached else "TOO HIGH"
        elif self.stage == "up":
            depth_status = "STANDING"
        else:
            depth_status = "STANDING"

        return {
            "reps": self.reps,
            "knee_angle": int(knee_angle),
            "back_angle": int(back_angle),
            "depth_status": depth_status
        }
    
