"""Read-only local API for aggregate stats shown on the static landing page."""

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import streamlit as st

from services.config.workout_config import EXERCISE_OPTIONS, AUTO_DETECT_OPTION


DB_PATH = Path(__file__).resolve().parents[2] / "data.db"
DEFAULT_PORT = 8765


class _StatsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/landing-stats":
            self.send_error(404)
            return

        try:
            with sqlite3.connect(DB_PATH, timeout=2) as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS activity_logs,
                           COALESCE(SUM(reps), 0) AS reps_tracked
                    FROM exercises
                    """
                ).fetchone()
            payload = {
                "supported_exercises": sum(
                    1 for name in EXERCISE_OPTIONS if name != AUTO_DETECT_OPTION
                ),
                "activity_logs": row[0],
                "reps_tracked": row[1],
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            # LandingPage is a static file and may be opened via file:// or another local port.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (sqlite3.Error, OSError):
            self.send_error(503, "Workout database is not ready")

    def log_message(self, _format, *_args):
        # Keep routine browser polling out of the Streamlit terminal.
        return


@st.cache_resource
def start_landing_stats_api():
    """Start the read-only aggregate endpoint once per Streamlit process."""
    try:
        port = int(os.environ.get("LANDING_STATS_PORT", DEFAULT_PORT))
        server = ThreadingHTTPServer(("127.0.0.1", port), _StatsHandler)
    except (OSError, ValueError) as error:
        st.warning(f"Landing page live stats are unavailable: {error}")
        return None
    thread = Thread(target=server.serve_forever, name="landing-stats-api", daemon=True)
    thread.start()
    return server
