import streamlit as st
import os
import time
import pandas as pd
from services.auth.login_wall import render_login_wall
from services.state.session_defaults import initial_session_defaults
from services.config.workout_config import AUTO_DETECT_OPTION, EXERCISE_OPTIONS
from services.ui.style_loader import load_css, inject_local_font, inject_webrtc_styles
from services.persistence.exercise_repository import init_db
from services.persistence.landing_stats_api import start_landing_stats_api
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from services.vision.exercise_video_processor import VideoProcessorClass
from services.tracking.metrics import sync_metrics_update
from services.persistence.exercise_repository import add_exercise, get_users_exercises
from groq import Groq
from dotenv import load_dotenv
from services.coaching.llm import LLMCoach
from services.coaching.tts import TextToSpeech
from services.coaching.tts import VOICE_LANGUAGES
from services.coaching.voice_pipeline import VoicePipeline, autoplay_audio


load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def main():
    st.set_page_config(
        page_icon="🏋️‍♀️",
        page_title="AI Real-time GYM Coach",
        initial_sidebar_state="expanded",
        layout="centered"
    )

    load_css(os.path.join(os.getcwd(), "static", "style.css"))
    inject_local_font(os.path.join(os.getcwd(), "static", "AdobeClean.otf"), "AdobeClean")

    init_db()
    start_landing_stats_api()

    if not render_login_wall():
        return 

    initial_session_defaults()

    if "voice_pipeline" not in st.session_state:
        try:
            api_key = os.environ.get("GROQ_API_KEY", "")

            if not api_key:
                try:
                    api_key = st.secrets["GROQ_API_KEY"]
                except Exception:
                    api_key = ""

            if not api_key:
                raise ValueError("GROQ_API_KEY is not configured")
            
            groq_client = Groq(api_key=api_key)
            llm_coach = LLMCoach(groq_client)
            tts = TextToSpeech()
            st.session_state.voice_pipeline = VoicePipeline(llm_coach, tts)
            st.session_state.voice_error = None
        except Exception as error:
            st.session_state.voice_pipeline = None
            st.session_state.voice_error = str(error)

    workout_started = st.session_state.get("workout_started", False)

    with st.sidebar:
        st.header("Workout controls")
        st.selectbox(
            "Activity mode", EXERCISE_OPTIONS,
            key="plan_exercise_mode",
            help="Auto-detect identifies supported gym exercises and yoga poses from your camera.",
            disabled=workout_started,
        )
        plan_exercise = st.session_state.plan_exercise_mode
        if plan_exercise == AUTO_DETECT_OPTION:
            st.caption("Auto-detect is selected. You can begin yoga or supported gym movements without choosing a pose.")
        else:
            st.number_input("Target sets", min_value=1, max_value=20, key="plan_sets", disabled=workout_started)
            st.number_input("Reps per set", min_value=1, max_value=100, key="plan_reps", disabled=workout_started)
        st.selectbox(
            "Coach voice language", options=list(VOICE_LANGUAGES),
            key="coach_language", help="Choose the language used for spoken coaching.",
        )

        if not workout_started:
            if st.button("Start Workout", type="primary", width="stretch"):
                st.session_state.exercise_type = plan_exercise
                st.session_state.target_sets = 0 if plan_exercise == AUTO_DETECT_OPTION else st.session_state.plan_sets
                st.session_state.reps_per_set = 0 if plan_exercise == AUTO_DETECT_OPTION else st.session_state.plan_reps
                st.session_state.reps = 0
                st.session_state.activity_mode = "auto" if plan_exercise == AUTO_DETECT_OPTION else "manual"
                st.session_state.auto_activity_summary = {}
                st.session_state.detected_exercise = "Waiting for pose..."
                st.session_state.detected_activity_category = "Waiting for a clear pose"
                st.session_state.activity_hold_seconds = 0.0
                st.session_state.activity_current_hold_seconds = 0.0
                st.session_state.sun_salutation_cycles = 0
                st.session_state.sun_salutation_step = 0
                st.session_state.sun_salutation_pose = ""
                st.session_state.workout_started = True
                st.session_state.set_cycle_started_at = time.time()
                st.session_state.last_saved_sets_completed = 0
                st.session_state.last_notified_sets_completed = 0
                st.session_state.last_notified_workout_complete = False
                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_started", exercise=plan_exercise, metrics={},
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result
                st.rerun()
        else:
            st.success(f"Active: {st.session_state.exercise_type}")
            if st.session_state.exercise_type == AUTO_DETECT_OPTION:
                st.metric("Detected activity", st.session_state.get("detected_exercise", "Waiting for pose..."))
                if st.session_state.get("detected_activity_category") == "Exercise":
                    st.metric("Reps", st.session_state.get("reps", 0))
                else:
                    st.metric("Current pose hold", f"{st.session_state.get('activity_current_hold_seconds', 0):.0f} sec")
                st.metric("Surya Namaskar cycles", st.session_state.get("sun_salutation_cycles", 0))
                flow_step = st.session_state.get("sun_salutation_step", 0)
                st.caption(f"Surya Namaskar progress: {flow_step} / 12 poses")
                if flow_step:
                    st.caption(f"Current flow pose: {st.session_state.get('sun_salutation_pose', '')}")
                st.caption("Anulom Vilom: camera can detect seated posture and hand position, not breathing or nostril switching.")
            else:
                st.metric("Reps", st.session_state.get("reps", 0))
                st.metric("Sets completed", st.session_state.get("sets_completed", 0))
            if st.button("End Workout", width="stretch"):
                for activity_name, activity_stats in st.session_state.get("auto_activity_summary", {}).items():
                    if activity_stats.get("reps", 0) or activity_stats.get("time", 0):
                        add_exercise(st.session_state.get("user_id", 0), activity_name,
                                     activity_stats.get("reps", 0), 0, activity_stats.get("time", 0))
                st.session_state.workout_started = False
                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_completed", exercise=st.session_state.exercise_type, metrics={},
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result
                st.rerun()

    st.title("AI Real-time GYM Coach")
    st.markdown("#### Real-time pose detection with proactive AI voice coaching")

    if not workout_started:
        st.info("Open Workout controls in the sidebar, keep Auto-detect selected, then press Start Workout.")
    else:
        st.info("Workout active. Live detection, rep/pose hold and Surya Namaskar progress are in the sidebar.")

    if not st.session_state.get("voice_pipeline"):
        st.warning(
            "Voice coach is off. Add `GROQ_API_KEY=your_key` to `Main App/.env`, "
            "then restart the app. Setup issue: "
            f"{st.session_state.get('voice_error', 'unknown error')}"
        )
    elif st.session_state.voice_pipeline.last_error:
        st.warning(
            "Voice coach request failed. Check that your Groq API key is valid "
            "and that this computer has internet access."
        )
 
    if st.session_state.get("audio_to_play"):
        autoplay_audio(st.session_state.audio_to_play)

    if st.session_state.get("coach_feedback"):
        st.markdown("")
        st.success(f"🤖 **Coach:** {st.session_state.coach_feedback}")

    if not workout_started:
        st.markdown(
            """
            <div style="
                border: 2px solid #344760;
                border-radius: 16px;
                padding: 24px 20px;
                text-align: center;
                color: #888;
                margin-top: 16px;
                margin-bottom: 20px;
            ">
                <h2 style="color:#ccc; margin-bottom:6px;">Ready to train?</h2>
                <p style="font-size:1.05rem;">
                    Start the workout from the sidebar, then enter the camera frame.<br>
                    Auto-detect identifies supported gym movements and yoga poses for you.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.caption(
            "Rep tracking tip: keep your full body visible. For squats and lunges, "
            "stand side-on to the camera. For Surya Namaskar, keep your full-body flow in frame."
        )
        context = webrtc_streamer(
            key="exercise-analysis",
            mode=WebRtcMode.SENDRECV,
            video_processor_factory=VideoProcessorClass,
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
            media_stream_constraints={
                "video": {
                    # Keep camera frames light enough for real-time pose processing.
                    "width": {"ideal": 640},
                    "height": {"ideal": 480},
                    "frameRate": {"ideal": 20, "max": 24},
                },
                "audio": False
            },
            async_processing=True,
            # Drop stale frames instead of building a queue when inference is slower.
            video_receiver_size=1,
        )

        sync_metrics_update(context)

        if context.state.playing:
            time.sleep(0.4)
            st.rerun()

        inject_webrtc_styles()

    st.divider()

    st.markdown("#### Workout History")

    user_id = st.session_state.get("user_id", 0)

    if isinstance(user_id, int):
        history_rows = get_users_exercises(user_id)

        arr = [
            {
                "Exercise": row['exercise_name'],
                "Reps": row['reps'],
                "Sets": row['sets'],
                "Time (sec)": row['time'],
                "Date": row['created_at']
            }
            for row in history_rows
        ]

        df = pd.DataFrame(arr)

        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            agg_df = df.groupby(["Exercise", "Date"]).agg({
                "Reps": 'sum',
                "Sets": "sum",
                "Time (sec)": "sum"
            }).reset_index()
            agg_df.index += 1
            st.table(agg_df, border="horizontal")
        else:
            st.info("No workout history found.")


if __name__ == "__main__":
    main()
    
