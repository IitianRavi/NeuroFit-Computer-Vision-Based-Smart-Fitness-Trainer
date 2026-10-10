import streamlit as st
import time
from services.config.workout_config import METRICS_FIELDS
from services.config.workout_config import AUTO_DETECT_OPTION
from services.persistence.exercise_repository import add_exercise


def sync_metrics_update(context):
    if not context or not hasattr(context, "state") or not context.state.playing:
        return
    
    processor = getattr(context, "video_processor", None)

    if not processor:
        return 
    
    selected_exercise = st.session_state.get("exercise_type")

    if not selected_exercise:
        return
    
    processor.set_exercise(selected_exercise)
    latest_metrics = processor.get_latest_metrics()

    if not latest_metrics:
        return
    
    pose_detected = latest_metrics.get("pose_detected", True)
    is_auto_detect = selected_exercise == AUTO_DETECT_OPTION
    exercise = latest_metrics.get("exercise_type", selected_exercise)

    if is_auto_detect:
        if pose_detected:
            st.session_state.detected_exercise = exercise
            st.session_state.detected_activity_category = latest_metrics.get(
                "activity_category", "Waiting for a clear pose"
            )
            st.session_state.activity_hold_seconds = latest_metrics.get("hold_seconds", 0.0)
            st.session_state.activity_current_hold_seconds = latest_metrics.get("current_hold_seconds", 0.0)
            st.session_state.sun_salutation_cycles = latest_metrics.get("sun_salutation_cycles", 0)
            st.session_state.sun_salutation_step = latest_metrics.get("sun_salutation_step", 0)
            st.session_state.sun_salutation_pose = latest_metrics.get("sun_salutation_pose", "")
            st.session_state.reps = latest_metrics.get("reps", 0)

            summary = st.session_state.setdefault("auto_activity_summary", {})
            category = latest_metrics.get("activity_category")
            if category in {"Exercise", "Yoga pose"}:
                stats = summary.setdefault(exercise, {"reps": 0, "time": 0})
                if category == "Exercise":
                    stats["reps"] = max(stats["reps"], int(latest_metrics.get("reps", 0)))
                else:
                    stats["time"] = max(stats["time"], int(latest_metrics.get("hold_seconds", 0)))

            cycles = int(latest_metrics.get("sun_salutation_cycles", 0))
            if cycles:
                stats = summary.setdefault("Surya Namaskar", {"reps": 0, "time": 0})
                stats["reps"] = max(stats["reps"], cycles)
        else:
            st.session_state.detected_exercise = "Move into camera view"
            st.session_state.detected_activity_category = "Waiting for a clear pose"
            st.session_state.activity_current_hold_seconds = 0.0
    else:
        st.session_state.reps = latest_metrics.get("reps", st.session_state.get("reps", 0)) or 0

    fields = METRICS_FIELDS.get(exercise)
    if fields:
        for key, default in fields.items():
            if key in latest_metrics:
                st.session_state[key] = latest_metrics[key]
            elif not pose_detected and (key.endswith("_status") or key == "depth_status"):
                st.session_state[key] = "NO POSE"
            elif key not in st.session_state:
                st.session_state[key] = default

    reps_per_set = st.session_state.get("reps_per_set", 0)
    target_sets = st.session_state.get("target_sets", 0)

    if not is_auto_detect and reps_per_set > 0 and target_sets > 0:
        reps = st.session_state.reps
        sets_completed = reps // reps_per_set
        current_set_reps = reps % reps_per_set
        workout_completed = sets_completed >= target_sets 
    else:
        sets_completed = 0
        current_set_reps = 0
        workout_completed = False

    st.session_state.sets_completed = sets_completed
    st.session_state.current_set_reps = current_set_reps
    st.session_state.workout_completed = workout_completed

    last_saved_sets = st.session_state.get("last_saved_sets_completed", 0)

    if not is_auto_detect and target_sets > 0 and reps_per_set > 0 and sets_completed > last_saved_sets:
        newly_completed = sets_completed - last_saved_sets
        now_ts = time.time()
        started_at = st.session_state.get("set_cycle_started_at", now_ts)
        time_taken = now_ts - started_at
        user_id = st.session_state.get("user_id", 0)

        add_exercise(user_id, exercise, newly_completed * reps_per_set, newly_completed, time_taken)

        if st.session_state.get("voice_pipeline"):
            result = st.session_state.voice_pipeline.process_event(
                event="set_completed",
                exercise=exercise,
                metrics=latest_metrics,
            )

            if result:
                st.session_state.audio_to_play, st.session_state.coach_feedback = result

        st.session_state.set_cycle_started_at = now_ts
        st.session_state.last_saved_sets_completed = sets_completed

    if workout_completed and not st.session_state.get("last_notified_workout_complete", False):
        st.session_state.last_notified_workout_complete = True

        if st.session_state.get("voice_pipeline"):
            result = st.session_state.voice_pipeline.process_event(
                event="workout_completed",
                exercise=exercise,
                metrics=latest_metrics,
            )

            if result:
                st.session_state.audio_to_play, st.session_state.coach_feedback = result
                
    if not pose_detected and st.session_state.get("voice_pipeline"):
        result = st.session_state.voice_pipeline.process_event(
            event="no_pose_detected",
            exercise=exercise,
            metrics={"issue": "No pose detected! Please step into the camera frame."},
        )
    
        if result:
            st.session_state.audio_to_play, st.session_state.coach_feedback = result

    if st.session_state.get("voice_pipeline"):
        result = st.session_state.voice_pipeline.process_event(
            event="ongoing_form_check",
            exercise=exercise,
            metrics=latest_metrics,
        )
        
        if result:
            st.session_state.audio_to_play, st.session_state.coach_feedback = result
