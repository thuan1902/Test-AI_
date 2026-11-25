
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory


# ==========================================
# ĐƯỜNG DẪN VÀ CẤU HÌNH
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
ENV_PATH = PROJECT_DIR / ".env"

# Không ghi đè Environment Variables của Vercel
load_dotenv(
    dotenv_path=ENV_PATH,
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
    "qwen2.5:3b",
).strip()

REQUEST_TIMEOUT = int(
    os.getenv("OLLAMA_TIMEOUT", "180")
)

app = Flask(__name__)
app.logger.setLevel(logging.INFO)


# ==========================================
# PROMPT HỆ THỐNG
# ==========================================

SYSTEM_PROMPT = """
Bạn là Nova AI, trợ lý tư vấn chọn tổ hợp môn lớp 10.

Quy tắc:
- Trả lời bằng tiếng Việt.
- Thân thiện, rõ ràng, dễ hiểu với học sinh.
- Khi tư vấn tổ hợp, chỉ sử dụng các tổ hợp được cung cấp.
- Giải thích lý do cho từng đề xuất.
- Không tự bịa dữ liệu hoặc thông tin tuyển sinh.
- Nhắc học sinh xác nhận phương án chính thức với nhà trường.
"""


# ==========================================
# XÁC THỰC OLLAMA
# ==========================================

def get_ollama_headers():

    headers = {
        "Content-Type": "application/json"
    }

    # Ollama Cloud cần API key
    if "ollama.com" in OLLAMA_URL.lower():

        if not OLLAMA_API_KEY:
            raise RuntimeError(
                "Thiếu OLLAMA_API_KEY trong "
                "Vercel Environment Variables."
            )

        headers["Authorization"] = (
            f"Bearer {OLLAMA_API_KEY}"
        )

    elif OLLAMA_API_KEY:
        headers["Authorization"] = (
            f"Bearer {OLLAMA_API_KEY}"
        )

    return headers


# ==========================================
# GỌI MODEL QUA OLLAMA
# ==========================================

def ask_ollama(question):

    if not MODEL:
        raise RuntimeError(
            "Chưa cấu hình OLLAMA_MODEL."
        )

    headers = get_ollama_headers()

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
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except requests.exceptions.ConnectionError as exc:

        raise RuntimeError(
            "Không kết nối được Ollama. "
            "Hãy kiểm tra OLLAMA_URL."
        ) from exc

    except requests.exceptions.Timeout as exc:

        raise RuntimeError(
            f"Ollama phản hồi quá "
            f"{REQUEST_TIMEOUT} giây."
        ) from exc

    except requests.exceptions.HTTPError as exc:

        try:
            detail = response.json().get(
                "error",
                response.text
            )
        except ValueError:
            detail = response.text

        raise RuntimeError(
            f"Ollama trả về HTTP "
            f"{response.status_code}: {detail}"
        ) from exc

    try:

        result = response.json()

    except ValueError as exc:

        raise RuntimeError(
            "Ollama trả về JSON không hợp lệ."
        ) from exc

    answer = (
        result.get("message", {}).get("content", "")
        if isinstance(result, dict)
        else ""
    )

    answer = answer.strip()

    if not answer:
        raise RuntimeError(
            "Model Ollama không trả về nội dung văn bản."
        )

    return answer


# ==========================================
# TRANG CHỦ
# ==========================================

@app.get("/")
def home():

    index_file = PROJECT_DIR / "index.html"

    if index_file.is_file():
        return send_from_directory(
            PROJECT_DIR,
            "index.html"
        )

    return jsonify({
        "server": "ok",
        "message": "Nova AI API đang hoạt động."
    })


# ==========================================
# KIỂM TRA SERVER VÀ OLLAMA
# ==========================================

@app.get("/api/health")
def health():

    ollama_ok = False
    available_models = []
    error = None

    try:

        headers = get_ollama_headers()

        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        available_models = [
            item.get("name", "")
            for item in data.get("models", [])
        ]

        ollama_ok = True

    except Exception as exc:

        error = str(exc)

    model_installed = (
        MODEL in available_models
        or any(
            name.split(":")[0] == MODEL.split(":")[0]
            for name in available_models
        )
    )

    return jsonify({
        "server": "ok",
        "ollama": (
            "ok" if ollama_ok else "unavailable"
        ),
        "model": MODEL,
        "model_installed": model_installed,
        "available_models": available_models,
        "error": error,
    })


# ==========================================
# CHAT
# ==========================================

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

        app.logger.exception(
            "Ollama chat error"
        )

        return jsonify({
            "answer": (
                "Nova chưa gọi được model Ollama. "
                "Hãy kiểm tra cấu hình máy chủ AI."
            ),
            "error_type": type(exc).__name__,
            "detail": str(exc),
        }), 502


# ==========================================
# TƯ VẤN TỔ HỢP MÔN
# ==========================================

@app.post("/api/recommend")
def recommend():

    data = request.get_json(silent=True) or {}

    name = str(
        data.get("name", "")
    ).strip()

    goal = str(
        data.get("goal", "Chưa xác định")
    ).strip()

    notes = str(
        data.get("notes", "")
    ).strip()

    ratings = data.get("ratings", {})

    combinations = data.get(
        "available_combinations",
        {}
    )

    if not isinstance(ratings, dict):
        ratings = {}

    if (
        not isinstance(combinations, dict)
        or not combinations
    ):

        return jsonify({
            "answer": (
                "Chưa có dữ liệu tổ hợp để tư vấn."
            )
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

        return jsonify({
            "answer": answer
        })

    except Exception as exc:

        app.logger.exception(
            "Ollama recommendation error"
        )

        return jsonify({
            "answer": (
                "Nova chưa tạo được gợi ý. "
                "Hãy kiểm tra cấu hình máy chủ AI."
            ),
            "error_type": type(exc).__name__,
            "detail": str(exc),
        }), 502


# ==========================================
# KHỞI ĐỘNG LOCAL SERVER
# ==========================================

if __name__ == "__main__":

    from waitress import serve
    import webbrowser

    host = "127.0.0.1"
    port = 5000

    url = f"http://{host}:{port}"

    print("\n================================")
    print("       NOVA AI ĐANG CHẠY")
    print(f"Website: {url}")
    print(f"Model: {MODEL}")
    print(f"Ollama URL: {OLLAMA_URL}")
    print("Backend: Ollama")
    print("================================\n")

    webbrowser.open(url)

    serve(
        app,
        host=host,
        port=port
    )
