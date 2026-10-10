import time
import streamlit as st
from services.coaching.tts import VOICE_LANGUAGES


class VoicePipeline:
    def __init__(self, llm, tts):
        self.llm = llm
        self.tts = tts
        self.last_spoken_at = 0
        self.last_error = None

    def _find_form_issue(self, exercise, metrics):
        if "issue" in metrics:
            return metrics["issue"]

        if metrics.get("activity_category") == "Yoga pose":
            return metrics.get("form_issue")

        if (
            metrics.get("activity_category") == "Waiting for a clear pose"
            and metrics.get("pose_detected", True)
        ):
            return "I cannot clearly identify your pose. Step back and keep your full body visible."

        if exercise == "Squats":
            depth = metrics.get("depth_status", "")
            back_angle = metrics.get("back_angle", 180)
            
            if depth == "TOO HIGH":
                return "The user's squat is not deep enough — knees are not bending sufficiently."

            if isinstance(back_angle, (int, float)) and back_angle < 130:
                return "The user is leaning too far forward during the squat."

        elif exercise == "Push-ups":
            alignment = metrics.get("body_alignment", "")
            hip_status = metrics.get("hip_status", "")
            
            if alignment == "Poor Form":
                return "The user's body is not straight during the push-up."

            if hip_status == "SAGGING":
                return "The user's hips are sagging down during the push-up."

            if hip_status == "PIKED UP":
                return "The user's hips are too high — lower them to form a straight line."

        elif exercise == "Biceps Curls (Dumbbell)":
            swing = metrics.get("swing_status", "")
            shoulder = metrics.get("shoulder_status", "")
            
            if swing == "SWINGING":
                return "The user is swinging their torso during the curl — keep the body still."

            if shoulder == "ELBOW DRIFTING":
                return "The user's elbow is drifting away from their side during the curl."

        elif exercise == "Shoulder Press":
            back_arch = metrics.get("back_arch_status", "")
            extension = metrics.get("extension_status", "")
            
            if back_arch == "Excessive Arch":
                return "The user is arching their lower back excessively during the press."

            if back_arch == "Slight Arch":
                return "Slight back arch detected — encourage the user to brace their core."

        elif exercise == "Lunges":
            balance = metrics.get("balance_status", "")
            
            if balance == "OFF BALANCE":
                return "The user is losing balance during the lunge — feet should be hip-width apart."

        return None

    def process_event(self, event, exercise, metrics):
        issue = self._find_form_issue(exercise, metrics)

        now = time.time()

        is_major_issue = event in ["workout_started", "set_completed", "workout_completed"]

        if not is_major_issue:
            # Periodic positive feedback when form is good; quicker corrections
            # when a form issue is present.
            cooldown = 5 if issue else 15
            if now - self.last_spoken_at < cooldown:
                return None
            
        try:
            selected_language = st.session_state.get("coach_language", "Hindi / Hinglish")
            language_code, language_name = VOICE_LANGUAGES.get(
                selected_language, VOICE_LANGUAGES["Hindi / Hinglish"]
            )
            context = metrics.get("coach_praise") if not issue else None
            text = self.llm.give_feedback(event, issue, language_name, context=context)
            voice = self.tts.speak(text, lang=language_code)
        except Exception as error:
            self.last_error = type(error).__name__
            return None

        self.last_spoken_at = now
        self.last_error = None

        return voice, text
    

def autoplay_audio(audio_bytes):
    if not audio_bytes:
        return

    # Keep the player visible as a manual fallback when the browser blocks autoplay.
    st.audio(audio_bytes, format="audio/mp3", autoplay=True)
