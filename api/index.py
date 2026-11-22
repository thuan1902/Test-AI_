
import logging
import os
import logging
import base64
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory


# =========================
# CẤU HÌNH
# =========================
# =====================================
# CONFIG
# =====================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# Không ghi đè biến môi trường Vercel bằng file .env
load_dotenv(
    dotenv_path=PROJECT_DIR / ".env",
    override=False,
    encoding="utf-8",
)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "https://ollama.com",
).strip().rstrip("/")
    "OLLAMA_URL", "https://ollama.com"
).rstrip("/")

OLLAMA_API_KEY = os.getenv(
    "OLLAMA_API_KEY",
    "",
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL", "gemma4:31b-cloud"
).strip()

MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma4:31b-cloud",
).strip()
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")

REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

app = Flask(__name__)
app.logger.setLevel(logging.INFO)


# =========================
# PROMPT HỆ THỐNG
# =========================
# =====================================
# SYSTEM PROMPT
# =====================================

SYSTEM_PROMPT = """
Bạn là Nova AI, trợ lý tư vấn chọn tổ hợp môn lớp 10.

Quy tắc:
- Trả lời bằng tiếng Việt.
- Luôn trả lời bằng tiếng Việt.
- Thân thiện, rõ ràng, dễ hiểu với học sinh.
- Khi tư vấn tổ hợp, chỉ sử dụng các tổ hợp được cung cấp.
- Giải thích lý do cho từng đề xuất.
- Không tự bịa dữ liệu hoặc thông tin tuyển sinh.
- Nhắc học sinh xác nhận phương án chính thức với nhà trường.
Quy tắc trả lời:
- Dùng tiếng Việt tự nhiên, dễ hiểu.
- Tối đa 3 dòng liền mạch.
- Mỗi dòng chỉ nêu một ý chính.
- Không mở đầu xã giao, không lặp lại câu hỏi.
- Nếu cần hướng dẫn, chỉ nêu các bước quan trọng nhất.
"""

# =====================================
# OLLAMA CHAT
# =====================================

# =========================
# GỌI OLLAMA CLOUD
# =========================
def ask_ollama(question):

    if not OLLAMA_MODEL:
        raise RuntimeError("Chưa cấu hình OLLAMA_MODEL.")

def ask_ollama(question, history=None):
    if not OLLAMA_API_KEY:
        raise RuntimeError(
            "Thiếu biến môi trường OLLAMA_API_KEY trên Vercel."
        )
    headers = {
        "Content-Type": "application/json"
    }

    if not MODEL:
        raise RuntimeError(
            "Thiếu biến môi trường OLLAMA_MODEL trên Vercel."
    if OLLAMA_API_KEY:
        headers["Authorization"] = (
            f"Bearer {OLLAMA_API_KEY}"
)

    # Tạo danh sách tin nhắn, bắt đầu bằng hướng dẫn hệ thống.
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    # Thêm lịch sử trò chuyện trước đó.
    if isinstance(history, list):
        for item in history[-500:]:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role not in ("user", "assistant"):
                continue

            if not isinstance(content, str) or not content.strip():
                continue

            messages.append({
                "role": role,
                "content": content[:6000],
            })

    # Thêm câu hỏi hiện tại sau lịch sử.
    messages.append({
        "role": "user",
        "content": question,
    })

    url = f"{OLLAMA_URL}/api/chat"

payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
                "Content-Type": "application/json",
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            f"Ollama phản hồi quá {REQUEST_TIMEOUT} giây."
        ) from exc
            {
                "role": "user",
                "content": question
            }
        ],
        "stream": False
    }

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Không kết nối được Ollama Cloud. "
            "Kiểm tra OLLAMA_URL và kết nối mạng."
        ) from exc
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT
    )

    except requests.exceptions.HTTPError as exc:
        try:
            detail = response.json().get("error", response.text)
        except ValueError:
            detail = response.text
    response.raise_for_status()

        raise RuntimeError(
            f"Ollama trả về HTTP {response.status_code}: {detail}"
        ) from exc
    data = response.json()

    result = response.json()
    answer = result.get("message", {}).get("content", "").strip()
    answer = (
        data.get("message", {})
        .get("content", "")
        .strip()
    )

if not answer:
        raise RuntimeError("Model không trả về nội dung.")
        raise RuntimeError("Ollama không trả về nội dung.")

return answer


# =========================
# TRANG CHỦ
# =========================
# =====================================
# HOME
# =====================================

@app.get("/")
def home():
    index_file = PROJECT_DIR / "index.html"
    return send_from_directory(BASE_DIR, "index.html")

    if index_file.is_file():
        return send_from_directory(PROJECT_DIR, "index.html")

    return jsonify({
        "server": "ok",
        "message": "Nova AI API đang hoạt động."
    })


# =========================
# KIỂM TRA SERVER
# =========================
# =====================================
# HEALTH
# =====================================

@app.get("/api/health")
def health():
    configured = bool(OLLAMA_API_KEY and MODEL)

return jsonify({
"server": "ok",
        "ollama_configured": configured,
        "model": MODEL or None,
        "message": (
            "Đã cấu hình Ollama Cloud."
            if configured
            else "Thiếu OLLAMA_API_KEY hoặc OLLAMA_MODEL."
        ),
    }), 200 if configured else 503
        "chat_model": OLLAMA_MODEL,
        "stt": bool(OPENAI_API_KEY),
        "tts": bool(GOOGLE_TTS_API_KEY)
    })


# =========================
# =====================================
# CHAT
# =========================

# =====================================

@app.post("/api/chat")
def chat():

data = request.get_json(silent=True) or {}

    question = str(data.get("message", "")).strip()
    history = data.get("history", [])
    question = str(
        data.get("message", "")
    ).strip()

if not question:
return jsonify({
"answer": "Bạn hãy nhập câu hỏi nhé."
}), 400

    if not isinstance(history, list):
        history = []

try:
        answer = ask_ollama(
            question,
            history=history,
        )
        answer = ask_ollama(question)

        return jsonify({"answer": answer})
        return jsonify({
            "answer": answer
        })

except Exception as exc:
        app.logger.exception("Ollama chat error")

        app.logger.exception("Chat error")

return jsonify({
            "answer": "Nova chưa gọi được model Ollama Cloud.",
            "detail": str(exc),
            "answer": "Nova chưa thể trả lời lúc này.",
            "detail": str(exc)
}), 502


# =========================
# TƯ VẤN TỔ HỢP MÔN
# =========================
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
    combinations = data.get("available_combinations", {})
    combinations = data.get(
        "available_combinations", {}
    )

if not isinstance(ratings, dict):
ratings = {}
@@ -268,33 +194,204 @@ def recommend():

Tên học sinh: {name or "Chưa cung cấp"}
Nhóm ngành quan tâm: {goal}
Điểm ưu tiên từng môn (0-5): {ratings}
Điểm ưu tiên từng môn: {ratings}
Thông tin bổ sung: {notes or "Không có"}

Các tổ hợp mẫu được cung cấp:
Các tổ hợp mẫu:
{combinations}

Yêu cầu:
1. So sánh điểm ưu tiên với từng tổ hợp.
2. Giải thích tổ hợp phù hợp và lý do.
3. Đưa ra một phương án khác để so sánh.
4. Chỉ đề xuất tổ hợp nằm trong dữ liệu được cung cấp.
5. Điểm ưu tiên không phải đánh giá năng lực chính thức.
6. Nhắc học sinh xác nhận với nhà trường.
2. Giải thích lý do.
3. Đưa ra phương án khác để so sánh.
4. Chỉ đề xuất tổ hợp có trong dữ liệu.
5. Nhắc học sinh xác nhận với nhà trường.
"""

try:
        answer = ask_ollama(question)
        return jsonify({"answer": answer})
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
        app.logger.exception("Ollama recommendation error")

        app.logger.exception("STT error")

return jsonify({
            "answer": "Nova chưa tạo được gợi ý từ Ollama Cloud.",
            "detail": str(exc),
            "error": "Không thể nhận dạng giọng nói.",
            "detail": str(exc)
}), 502


# Vercel sẽ quản lý việc khởi chạy ứng dụng.
# Không chạy waitress hoặc mở trình duyệt tại đây.
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
