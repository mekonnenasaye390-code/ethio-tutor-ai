import os, requests
from flask import Flask, request, jsonify, send_from_directory

GEMINI_API_KEY = "put your key here"   # <-- put your key here
MODEL = "gemini-2.5-flash"                           # change if Google renames the model

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)

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
    d = request.get_json(force=True)
    if GEMINI_API_KEY.startswith("PASTE"):
        return jsonify(error="Open app.py and paste your Gemini API key."), 400
    system = ("You are Ethio Tutor AI, a friendly tutor for students in Ethiopia. "
              "Give clear, simple, step-by-step answers. Reply in " + d.get("language", "English") + ". "
              + d.get("mode", ""))
    contents = []
    hist = d.get("history", [])
    for i, m in enumerate(hist):
        parts = [{"text": m["text"]}]
        if i == len(hist) - 1 and d.get("file"):
            parts.append({"inline_data": {"mime_type": d["file"]["mime"], "data": d["file"]["data"]}})
        contents.append({"role": m["role"], "parts": parts})
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={"system_instruction": {"parts": [{"text": system}]}, "contents": contents},
            timeout=120)
        j = r.json()
        if r.status_code != 200:
            return jsonify(error=j.get("error", {}).get("message", "Gemini error")), 500
        cand = j.get("candidates")
        if not cand:
            return jsonify(error="Gemini returned no answer. Try rephrasing your question."), 500
        parts = cand[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts) or "No answer received. Please try again."
        return jsonify(reply=text)
    except Exception as e:
        return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)