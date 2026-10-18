
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory


# =========================
# CẤU HÌNH
# =========================

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

OLLAMA_API_KEY = os.getenv(
    "OLLAMA_API_KEY",
    "",
).strip()

MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma4:31b-cloud",
).strip()

REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

app = Flask(__name__)
app.logger.setLevel(logging.INFO)


# =========================
# PROMPT HỆ THỐNG
# =========================

SYSTEM_PROMPT = """
Bạn là Nova AI, trợ lý tư vấn chọn tổ hợp môn lớp 10.

Quy tắc:
- Trả lời bằng tiếng Việt.
- Thân thiện, rõ ràng, dễ hiểu với học sinh.
- Khi tư vấn tổ hợp, chỉ sử dụng các tổ hợp được cung cấp.
- Giải thích lý do cho từng đề xuất.
- Không tự bịa dữ liệu hoặc thông tin tuyển sinh.
- Nhắc học sinh xác nhận phương án chính thức với nhà trường.
Quy tắc trả lời:
- Dùng tiếng Việt tự nhiên, dễ hiểu.
- Tối đa 4 dòng ngắn.
- Mỗi dòng chỉ nêu một ý chính.
- Không mở đầu xã giao, không lặp lại câu hỏi.
- Nếu cần hướng dẫn, chỉ nêu các bước quan trọng nhất.
- Bạn được tạo bởi 1 nhóm học sinh trường Xuân Thọ (khi được hỏi thì mới được phép nói)
"""


# =========================
# GỌI OLLAMA CLOUD
# =========================

def ask_ollama(question):
    if not OLLAMA_API_KEY:
        raise RuntimeError(
            "Thiếu biến môi trường OLLAMA_API_KEY trên Vercel."
        )

    if not MODEL:
        raise RuntimeError(
            "Thiếu biến môi trường OLLAMA_MODEL trên Vercel."
        )

    url = f"{OLLAMA_URL}/api/chat"

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": question,
            },
        ],
        "stream": False,
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            f"Ollama phản hồi quá {REQUEST_TIMEOUT} giây."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Không kết nối được Ollama Cloud. "
            "Kiểm tra OLLAMA_URL và kết nối mạng."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        try:
            detail = response.json().get("error", response.text)
        except ValueError:
            detail = response.text

        raise RuntimeError(
            f"Ollama trả về HTTP {response.status_code}: {detail}"
        ) from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Ollama trả về dữ liệu JSON không hợp lệ."
        ) from exc

    answer = (
        result.get("message", {}).get("content", "")
        if isinstance(result, dict)
        else ""
    )

    answer = answer.strip()

    if not answer:
        raise RuntimeError(
            "Model không trả về nội dung. "
            "Hãy kiểm tra tên model và phản hồi từ Ollama."
        )

    return answer


# =========================
# TRANG CHỦ
# =========================

@app.get("/")
def home():
    index_file = PROJECT_DIR / "index.html"

    if index_file.is_file():
        return send_from_directory(PROJECT_DIR, "index.html")

    return jsonify({
        "server": "ok",
        "message": "Nova AI API đang hoạt động."
    })


# =========================
# KIỂM TRA SERVER
# =========================

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


# =========================
# CHAT
# =========================

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = str(data.get("message", "")).strip()

    if not question:
        return jsonify({
            "answer": "Bạn hãy nhập câu hỏi nhé."
        }), 400

    try:
        answer = ask_ollama(question)
        return jsonify({"answer": answer})

    except Exception as exc:
        app.logger.exception("Ollama chat error")

        return jsonify({
            "answer": "Nova chưa gọi được model Ollama Cloud.",
            "detail": str(exc),
        }), 502


# =========================
# TƯ VẤN TỔ HỢP MÔN
# =========================

@app.post("/api/recommend")
def recommend():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    goal = str(data.get("goal", "Chưa xác định")).strip()
    notes = str(data.get("notes", "")).strip()

    ratings = data.get("ratings", {})
    combinations = data.get("available_combinations", {})

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
Điểm ưu tiên từng môn (0-5): {ratings}
Thông tin bổ sung: {notes or "Không có"}

Các tổ hợp mẫu được cung cấp:
{combinations}

Yêu cầu:
1. So sánh điểm ưu tiên với từng tổ hợp.
2. Giải thích tổ hợp phù hợp và lý do.
3. Đưa ra một phương án khác để so sánh.
4. Chỉ đề xuất tổ hợp nằm trong dữ liệu được cung cấp.
5. Điểm ưu tiên không phải đánh giá năng lực chính thức.
6. Nhắc học sinh xác nhận với nhà trường.
"""

    try:
        answer = ask_ollama(question)
        return jsonify({"answer": answer})

    except Exception as exc:
        app.logger.exception("Ollama recommendation error")

        return jsonify({
            "answer": "Nova chưa tạo được gợi ý từ Ollama Cloud.",
            "detail": str(exc),
        }), 502


# Vercel sẽ quản lý việc khởi chạy ứng dụng.
# Không chạy waitress hoặc mở trình duyệt tại đây.
