
import os
import requests
from flask import Flask, request, jsonify, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()


@app.route("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.route("/favicon.png")
def icon():
    return send_from_directory(BASE, "favicon.png")


@app.route("/style.css")
def css():
    return send_from_directory(BASE, "style.css")


@app.route("/script.js")
def js():
    return send_from_directory(BASE, "script.js")


@app.route("/api/chat", methods=["POST"])
def chat():
    if not GEMINI_API_KEY or GEMINI_API_KEY.lower() in {
        "put your key here",
        "your_api_key",
        "paste your key here",
    }:
        return jsonify(error="Gemini API key is missing. Configure GEMINI_API_KEY in Render Environment."), 503

    try:
        d = request.get_json(silent=True)

        if not isinstance(d, dict):
            return jsonify(error="Invalid request. Expected JSON data."), 400

        language = d.get("language", "English")
        mode = d.get("mode", "")
        history = d.get("history", [])

        if not isinstance(history, list) or not history:
            return jsonify(error="Please enter a question and try again."), 400

        system = (
            "You are Ethio Tutor AI, a friendly tutor for students in Ethiopia. "
            "Give clear, simple, step-by-step educational answers. "
            f"Reply in {language}. {mode}"
        )

        contents = []

        for i, message in enumerate(history):
            if not isinstance(message, dict):
                continue

            message_text = message.get("text", "")
            if not isinstance(message_text, str) or not message_text.strip():
                continue

            role = message.get("role", "user")

            # Gemini uses "model" rather than "assistant".
            if role == "assistant":
                role = "model"

            if role not in ("user", "model"):
                continue

            parts = [{"text": message_text}]

            # Attach a supported image or document to the latest message.
            if i == len(history) - 1 and d.get("file"):
                uploaded_file = d["file"]

                if isinstance(uploaded_file, dict):
                    mime = uploaded_file.get("mime")
                    data = uploaded_file.get("data")

                    if mime and data:
                        parts.append({
                            "inline_data": {
                                "mime_type": mime,
                                "data": data
                            }
                        })

            contents.append({
                "role": role,
                "parts": parts
            })

        if not contents or contents[-1]["role"] != "user":
            return jsonify(error="Your latest message must be a user question. Please try again."), 400

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{MODEL}:generateContent"
        )

        response = requests.post(
            url,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "system_instruction": {
                    "parts": [{"text": system}]
                },
                "contents": contents
            },
            timeout=120
        )

        try:
            result = response.json()
        except ValueError:
            app.logger.error(
                "Gemini returned a non-JSON response. HTTP %s",
                response.status_code
            )
            return jsonify(error="Gemini returned an unexpected response. Please try again."), 502

        if response.status_code != 200:
            message = result.get("error", {}).get(
                "message", "Gemini request failed."
            )
            app.logger.error(
                "Gemini API error: HTTP %s: %s",
                response.status_code,
                message
            )
            return jsonify(error=message), 502

        candidates = result.get("candidates", [])

        if not candidates:
            return jsonify(
                error="Gemini returned no answer. Try rephrasing your question."
            ), 502

        parts = candidates[0].get("content", {}).get("parts", [])
        answer = "".join(
            part.get("text", "") for part in parts
            if isinstance(part, dict)
        ).strip()

        if not answer:
            return jsonify(
                error="No text answer was returned. Please try another question."
            ), 502

        return jsonify(reply=answer)

    except requests.Timeout:
        app.logger.exception("Gemini request timed out")
        return jsonify(error="The AI took too long to respond. Please try again."), 504

    except requests.RequestException:
        app.logger.exception("Could not connect to Gemini")
        return jsonify(error="Could not connect to the AI service. Please try again."), 502

    except Exception:
        app.logger.exception("Unexpected error in /api/chat")
        return jsonify(error="An unexpected server error occurred. Please try again."), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
