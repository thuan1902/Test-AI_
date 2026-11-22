
import os
import logging
import base64
from pathlib import Path

import requests
from flask import Flask, request, jsonify, send_from_directory

# =====================================
# CONFIG
# =====================================

BASE_DIR = Path(__file__).resolve().parent

OLLAMA_URL = os.getenv(
    "OLLAMA_URL", "https://ollama.com"
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL", "gemma4:31b-cloud"
).strip()

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")

REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# =====================================
# SYSTEM PROMPT
# =====================================

SYSTEM_PROMPT = """
Bạn là Nova AI, trợ lý tư vấn chọn tổ hợp môn lớp 10.

Quy tắc:
- Luôn trả lời bằng tiếng Việt.
- Thân thiện, rõ ràng, dễ hiểu với học sinh.
- Khi tư vấn tổ hợp, chỉ sử dụng các tổ hợp được cung cấp.
- Giải thích lý do cho từng đề xuất.
- Không tự bịa dữ liệu hoặc thông tin tuyển sinh.
- Nhắc học sinh xác nhận phương án chính thức với nhà trường.
"""

# =====================================
# OLLAMA CHAT
# =====================================

def ask_ollama(question):

    if not OLLAMA_MODEL:
        raise RuntimeError("Chưa cấu hình OLLAMA_MODEL.")

    headers = {
        "Content-Type": "application/json"
    }

    if OLLAMA_API_KEY:
        headers["Authorization"] = (
            f"Bearer {OLLAMA_API_KEY}"
        )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "stream": False
    }

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    answer = (
        data.get("message", {})
        .get("content", "")
        .strip()
    )

    if not answer:
        raise RuntimeError("Ollama không trả về nội dung.")

    return answer


# =====================================
# HOME
# =====================================

@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


# =====================================
# HEALTH
# =====================================

@app.get("/api/health")
def health():

    return jsonify({
        "server": "ok",
        "chat_model": OLLAMA_MODEL,
        "stt": bool(OPENAI_API_KEY),
        "tts": bool(GOOGLE_TTS_API_KEY)
    })


# =====================================
# CHAT
# =====================================

@app.post("/api/chat")
def chat():

    data = request.get_json(silent=True) or {}

    question = str(
        data.get("message", "")
    ).strip()

    if not question:
        return jsonify({
            "answer": "Bạn hãy nhập câu hỏi nhé."
        }), 400

    try:
        answer = ask_ollama(question)

        return jsonify({
            "answer": answer
        })

    except Exception as exc:

        app.logger.exception("Chat error")

        return jsonify({
            "answer": "Nova chưa thể trả lời lúc này.",
            "detail": str(exc)
        }), 502


# =====================================
# RECOMMEND
# =====================================

@app.post("/api/recommend")
def recommend():

    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    goal = str(data.get("goal", "Chưa xác định")).strip()
    notes = str(data.get("notes", "")).strip()

    ratings = data.get("ratings", {})
    combinations = data.get(
        "available_combinations", {}
    )

    if not isinstance(ratings, dict):
        ratings = {}

    if not isinstance(combinations, dict) or not combinations:
        return jsonify({
            "answer": "Chưa có dữ liệu tổ hợp để tư vấn."
        }), 400

    question = f"""
Hãy tư vấn chọn tổ hợp môn cho học sinh lớp 10.

Tên học sinh: {name or "Chưa cung cấp"}
Nhóm ngành quan tâm: {goal}
Điểm ưu tiên từng môn: {ratings}
Thông tin bổ sung: {notes or "Không có"}

Các tổ hợp mẫu:
{combinations}

Yêu cầu:
1. So sánh điểm ưu tiên với từng tổ hợp.
2. Giải thích lý do.
3. Đưa ra phương án khác để so sánh.
4. Chỉ đề xuất tổ hợp có trong dữ liệu.
5. Nhắc học sinh xác nhận với nhà trường.
"""

    try:
        return jsonify({
            "answer": ask_ollama(question)
        })

    except Exception as exc:

        app.logger.exception("Recommend error")

        return jsonify({
            "answer": "Nova chưa tạo được gợi ý.",
            "detail": str(exc)
        }), 502


# =====================================
# SPEECH TO TEXT
# POST /api/transcribe
# multipart/form-data: file
# =====================================

@app.post("/api/transcribe")
def transcribe():

    if not OPENAI_API_KEY:
        return jsonify({
            "error": "Chưa cấu hình OPENAI_API_KEY."
        }), 500

    audio = request.files.get("file")

    if audio is None:
        return jsonify({
            "error": "Không tìm thấy file âm thanh."
        }), 400

    audio_data = audio.read()

    if not audio_data:
        return jsonify({
            "error": "File ghi âm rỗng."
        }), 400

    if len(audio_data) > 3 * 1024 * 1024:
        return jsonify({
            "error": "File ghi âm quá lớn."
        }), 413

    try:

        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={
                "Authorization": (
                    f"Bearer {OPENAI_API_KEY}"
                )
            },
            files={
                "file": (
                    audio.filename or "recording.wav",
                    audio_data,
                    "audio/wav"
                )
            },
            data={
                "model": "gpt-transcribe",
                "language": "vi",
                "response_format": "json"
            },
            timeout=90
        )

        response.raise_for_status()

        result = response.json()

        text = str(
            result.get("text", "")
        ).strip()

        return jsonify({
            "text": text
        })

    except Exception as exc:

        app.logger.exception("STT error")

        return jsonify({
            "error": "Không thể nhận dạng giọng nói.",
            "detail": str(exc)
        }), 502


# =====================================
# TEXT TO SPEECH
# POST /api/speech
# JSON: {"text": "..."}
# =====================================

@app.post("/api/speech")
def speech():

    if not GOOGLE_TTS_API_KEY:
        return jsonify({
            "error": "Chưa cấu hình GOOGLE_TTS_API_KEY."
        }), 500

    data = request.get_json(silent=True) or {}

    text = str(
        data.get("text", "")
    ).strip()

    if not text:
        return jsonify({
            "error": "Văn bản trống."
        }), 400

    # Giới hạn độ dài để tránh tạo audio quá lớn.
    text = text[:2500]

    try:

        response = requests.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            params={
                "key": GOOGLE_TTS_API_KEY
            },
            json={
                "input": {
                    "text": text
                },
                "voice": {
                    "languageCode": "vi-VN",
                    "name": "vi-VN-Neural2-D"
                },
                "audioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": 16000,
                    "speakingRate": 1.0,
                    "volumeGainDb": 0.0
                }
            },
            timeout=60
        )

        response.raise_for_status()

        result = response.json()

        audio_base64 = result.get(
            "audioContent", ""
        )

        if not audio_base64:
            raise RuntimeError(
                "Google TTS không trả về âm thanh."
            )

        return jsonify({
            "audio": audio_base64,
            "format": "wav",
            "sample_rate": 16000
        })

    except Exception as exc:

        app.logger.exception("TTS error")

        return jsonify({
            "error": "Không thể tạo giọng nói.",
            "detail": str(exc)
        }), 502


# =====================================
# LOCAL SERVER
# =====================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
