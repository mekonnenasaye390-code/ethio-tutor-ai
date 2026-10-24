import os
import logging
import base64
import binascii

from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY", "").strip()
    or os.getenv("GOOGLE_API_KEY", "").strip()
)
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = None

if GEMINI_API_KEY:
    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=60000),  # milliseconds
    )


# --------------------------------------------------
# Frontend routes
# --------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.route("/favicon.png")
def icon():
    if not os.path.exists(os.path.join(BASE, "favicon.png")):
        return "", 204
    return send_from_directory(BASE, "favicon.png")


@app.route("/style.css")
def css():
    return send_from_directory(BASE, "style.css")


@app.route("/script.js")
def js():
    return send_from_directory(BASE, "script.js")


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "provider": "gemini",
        "configured": bool(GEMINI_API_KEY),
        "model": MODEL,
    })


# --------------------------------------------------
# Error response helper
# --------------------------------------------------

def error_response(message, status):
    return jsonify({"error": message}), status


# --------------------------------------------------
# File conversion
# --------------------------------------------------

def make_file_part(mime, raw_bytes):
    """Convert supported uploads to a Gemini content part."""

    if mime in (
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    ):
        return types.Part.from_bytes(data=raw_bytes, mime_type=mime)

    raise ValueError(
        "Supported files are PDF, JPEG, PNG, and WebP."
    )


# --------------------------------------------------
# Validate and normalize conversation history
# --------------------------------------------------

def normalize_history(history):
    """
    Returns a list of {"role": "user" | "model", "text": str}.
    Gemini uses the role names "user" and "model".
    """
    messages = []

    for item in history[-40:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        text = item.get("text", "")

        if role not in ("user", "model", "assistant"):
            continue

        if not isinstance(text, str) or not text.strip():
            continue

        api_role = "user" if role == "user" else "model"
        content = text[:20000]

        if messages and messages[-1]["role"] == api_role:
            messages[-1]["text"] += "\n\n" + content
        else:
            messages.append({
                "role": api_role,
                "text": content,
            })

    # A conversation must begin with a user message.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)

    if not messages:
        return []

    # A conversation must end with the current user message.
    if messages[-1]["role"] != "user":
        return []

    return messages


# --------------------------------------------------
# Main AI chat endpoint
# --------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def chat():

    if client is None:
        return error_response(
            "Gemini API key is not configured. "
            "Check GEMINI_API_KEY in your .env file.",
            503,
        )

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return error_response("Invalid JSON request.", 400)

    language = data.get("language", "English")
    mode = data.get("mode", "")
    history = data.get("history", [])
    uploaded_file = data.get("file")

    if not isinstance(language, str):
        language = "English"

    if not isinstance(mode, str):
        mode = ""

    if not isinstance(history, list) or not history:
        return error_response("Please send a message.", 400)

    messages = normalize_history(history)

    if not messages:
        return error_response(
            "Please send a new message and try again.",
            400,
        )

    # --------------------------------------------------
    # Tutor instructions
    # --------------------------------------------------

    system_instruction = (
        "You are Ethio Tutor AI, a friendly educational assistant "
        "for students in Ethiopia. "
        "Explain concepts clearly, step by step, using examples "
        "appropriate to the student's level. "
        "Help with mathematics, science, programming, languages, "
        "exam preparation, and general academic learning. "
        "When a document or image is provided, use its actual "
        "contents when answering. Never claim to have read a "
        "file that was not provided. Be honest when uncertain. "
        f"Reply in {language}. "
        f"Study mode and additional instructions: {mode[:2000]}"
    )

    # --------------------------------------------------
    # Prepare uploaded PDF or image (optional)
    # --------------------------------------------------

    file_part = None

    if uploaded_file is not None:
        if not isinstance(uploaded_file, dict):
            return error_response("Invalid uploaded file.", 400)

        mime = uploaded_file.get("mime")
        file_data = uploaded_file.get("data")

        allowed_types = {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if mime not in allowed_types:
            return error_response(
                "Supported files are PDF, JPEG, PNG, and WebP.",
                400,
            )

        if not isinstance(file_data, str) or not file_data:
            return error_response(
                "Uploaded file data is missing.",
                400,
            )

        # Limit encoded file size.
        if len(file_data) > 12 * 1024 * 1024:
            return error_response(
                "File is too large. Upload a smaller file.",
                400,
            )

        # Support data URLs sent by some frontends.
        if file_data.startswith("data:"):
            try:
                header, file_data = file_data.split(",", 1)
            except ValueError:
                return error_response(
                    "Invalid uploaded file data URL.",
                    400,
                )

            if ";base64" not in header:
                return error_response(
                    "The uploaded file must use base64 encoding.",
                    400,
                )

        try:
            raw_bytes = base64.b64decode(
                file_data,
                validate=True,
            )
        except (ValueError, binascii.Error):
            return error_response(
                "Invalid uploaded file data.",
                400,
            )

        if not raw_bytes:
            return error_response(
                "Uploaded file is empty.",
                400,
            )

        # Verify file signatures to reject obvious MIME mismatches.
        if mime == "application/pdf" and not raw_bytes.startswith(b"%PDF-"):
            return error_response(
                "The uploaded file does not appear to be a valid PDF.",
                400,
            )

        if mime == "image/jpeg" and not raw_bytes.startswith(b"\xff\xd8\xff"):
            return error_response(
                "The uploaded file does not appear to be a valid JPEG.",
                400,
            )

        if mime == "image/png" and not raw_bytes.startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            return error_response(
                "The uploaded file does not appear to be a valid PNG.",
                400,
            )

        if mime == "image/webp" and not (
            raw_bytes.startswith(b"RIFF")
            and raw_bytes[8:12] == b"WEBP"
        ):
            return error_response(
                "The uploaded file does not appear to be a valid WebP image.",
                400,
            )

        try:
            file_part = make_file_part(mime, raw_bytes)
        except ValueError as exc:
            return error_response(str(exc), 400)

    # --------------------------------------------------
    # Build Gemini contents
    # --------------------------------------------------

    contents = []
    last_index = len(messages) - 1

    for i, item in enumerate(messages):
        parts = [types.Part.from_text(text=item["text"])]

        # Attach the file to the latest user message.
        if i == last_index and file_part is not None:
            parts.append(file_part)

        contents.append(types.Content(role=item["role"], parts=parts))

    # --------------------------------------------------
    # Call Gemini
    # --------------------------------------------------

    try:
        result = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                # Gemini 2.5 counts thinking tokens toward this limit,
                # so keep it high enough for a full answer.
                max_output_tokens=8192,
            ),
        )

        # Prompt blocked by safety filters.
        feedback = getattr(result, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            logger.warning("Gemini blocked the prompt: %s", feedback.block_reason)
            return error_response(
                "Gemini could not answer this request because it was "
                "blocked by safety filters. Try rephrasing your question.",
                400,
            )

        answer = ""

        try:
            answer = (result.text or "").strip()
        except Exception:
            answer = ""

        if not answer:
            logger.warning("Gemini returned no text output.")
            return error_response(
                "The AI returned an empty answer. Please try again.",
                502,
            )

        return jsonify({
            "reply": answer,
            "model": getattr(result, "model_version", None) or MODEL,
        })

    except genai_errors.APIError as exc:
        status = getattr(exc, "code", None)

        # Log the actual API response, without logging secrets.
        logger.error(
            "Gemini API error: status=%s, message=%s",
            status,
            str(exc),
        )

        if status == 400:
            return error_response(
                "Gemini rejected the request. Check the terminal "
                "for the exact API error (the API key may also be invalid).",
                400,
            )

        if status == 401:
            return error_response(
                "Gemini authentication failed. Check your API key.",
                401,
            )

        if status == 403:
            return error_response(
                "Gemini denied the request. Check that your API key is "
                "valid and that the Gemini API is enabled for it.",
                403,
            )

        if status == 404:
            return error_response(
                "The requested Gemini model was not found or is "
                "unavailable. Check GEMINI_MODEL in your .env file.",
                404,
            )

        if status == 429:
            return error_response(
                "Gemini rate limit or quota reached. Wait a moment, "
                "check your API usage, then try again.",
                429,
            )

        return error_response(
            f"Gemini API error (HTTP {status}). "
            "Check the terminal for details.",
            502,
        )

    except Exception as exc:
        text = str(exc).lower()

        if "timed out" in text or "timeout" in text:
            logger.exception("Gemini request timed out.")
            return error_response(
                "The request to Gemini timed out. Please try again.",
                504,
            )

        if "connect" in text or "network" in text or "resolve" in text:
            logger.exception("Could not connect to Gemini.")
            return error_response(
                "Could not connect to Gemini. Check your internet connection.",
                502,
            )

        logger.exception("Unexpected Gemini request failure.")
        return error_response(
            "The AI request failed unexpectedly. Check the terminal "
            "for the detailed error.",
            500,
        )


# --------------------------------------------------
# Request too large
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(_error):
    return error_response(
        "Request is too large. Please upload a smaller file.",
        413,
    )


# --------------------------------------------------
# Start server
# --------------------------------------------------

if __name__ == "__main__":
    for name in ("index.html", "style.css", "script.js"):
        if not os.path.exists(os.path.join(BASE, name)):
            logger.warning("Missing file next to app.py: %s", name)
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY is not set in .env")
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
