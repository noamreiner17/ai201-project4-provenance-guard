import uuid
import json
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from signals import groq_signal, stylometric_signal

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# -------------------------
# Audit Log Helper
# -------------------------

LOG_PATH = "audit_log.jsonl"

def log_event(entry):
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

def read_log(limit=20):
    try:
        with open(LOG_PATH) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines[-limit:]]

# -------------------------
# Classification Helpers
# -------------------------

def classify(confidence):
    """Map a confidence score (0.0 human .. 1.0 AI) to an attribution and label.

    Mirrors the Uncertainty Representation table in planning.md.
    """
    if confidence <= 0.25:
        return "human", "Likely Human-Written"
    if confidence <= 0.45:
        return "likely_human", "Likely Human-Written"
    if confidence <= 0.54:
        return "uncertain", "Uncertain Result"
    if confidence <= 0.75:
        return "likely_ai", "Likely AI-Generated"
    return "ai", "Likely AI-Generated"

# -------------------------
# Routes
# -------------------------

@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    # Validate the request.
    if not text or not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Field 'text' is required and must be a non-empty string."}), 400
    if not creator_id or not isinstance(creator_id, str):
        return jsonify({"error": "Field 'creator_id' is required and must be a string."}), 400

    content_id = str(uuid.uuid4())

    # Signal 1 — Groq LLM.
    signal_1 = groq_signal(text)
    llm_score = signal_1["score"]

    # Signal 2 — Stylometric Analysis.
    signal_2 = stylometric_signal(text)
    stylometric_score = signal_2["score"]

    # Confidence scoring: both signals contribute equally (see planning.md).
    confidence = round((llm_score + stylometric_score) / 2, 4)
    attribution, label = classify(confidence)

    # Write a structured entry to the audit log, capturing both signal scores.
    log_event({
        "content_id": content_id,
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
        "status": "classified",
    })

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "llm_score": llm_score,
        "stylometric_score": stylometric_score,
    })


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json()
    content_id = data.get("content_id")
    reasoning = data.get("creator_reasoning")

    # Write appeal to audit log
    log_event({
        "content_id": content_id,
        "creator_id": None,
        "attribution": None,
        "confidence": None,
        "status": "under_review"
    })

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Your appeal was received and is under review.",
    })


@app.route("/log", methods=["GET"])
def view_log():
    return jsonify({
        "entries": read_log()
    })


if __name__ == "__main__":
    app.run(port=5000, debug=True)