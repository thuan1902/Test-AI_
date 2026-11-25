
import logging
import os
from pathlib import Path

import requests
from flask import Flask, request, jsonify, send_from_directory


# =====================================================
# CẤU HÌNH
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# Đọc trực tiếp Environment Variables trên Vercel.
# Không sử dụng file .env.

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "https://ollama.com"
).strip().rstrip("/")

OLLAMA_API_KEY = os.getenv(
    "OLLAMA_API_KEY",
    ""
).strip()

MODEL = os.getenv(
    "OLLAMA_MODEL",
    "glm-5.3-flash"
).strip()

try:
    REQUEST_TIMEOUT = int(
        os.getenv("OLLAMA_TIMEOUT", "180")
    )
except (TypeError, ValueError):
    REQUEST_TIMEOUT = 180

app = Flask(__name__)
app.logger.setLevel(logging.INFO)


# =====================================================
# PROMPT HỆ THỐNG
# =====================================================

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


# =====================================================
# XÁC THỰC OLLAMA
# =====================================================

def get_ollama_headers():

    if not OLLAMA_URL:
        raise RuntimeError(
            "Chưa cấu hình OLLAMA_URL trên Vercel."
        )

    if not OLLAMA_API_KEY:
        raise RuntimeError(
            "Thiếu OLLAMA_API_KEY trong Vercel Environment Variables."
        )

    token = OLLAMA_API_KEY

    # Tránh trường hợp người dùng đã nhập sẵn Bearer.
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# =====================================================
# GỬI REQUEST ĐẾN OLLAMA
# =====================================================

def ollama_request(endpoint, payload=None, timeout=None):

    url = f"{OLLAMA_URL}{endpoint}"
    headers = get_ollama_headers()

    try:

        if payload is None:

            response = requests.get(
                url,
                headers=headers,
                timeout=timeout or REQUEST_TIMEOUT,
            )

        else:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout or REQUEST_TIMEOUT,
            )

        if not response.ok:

            try:
                error_data = response.json()
                detail = error_data.get(
                    "error",
                    response.text
                )
            except ValueError:
                detail = response.text

            if response.status_code == 401:
                raise RuntimeError(
                    "HTTP 401 Unauthorized: Ollama không chấp nhận API key."
                )

            elif response.status_code == 403:
                raise RuntimeError(
                    f"HTTP 403 Forbidden: Không có quyền truy cập. {detail}"
                )

            elif response.status_code == 404:
                raise RuntimeError(
                    f"HTTP 404 Not Found: Kiểm tra endpoint hoặc model. {detail}"
                )

            elif response.status_code == 429:
                raise RuntimeError(
                    f"HTTP 429: Vượt giới hạn yêu cầu. {detail}"
                )

            else:
                raise RuntimeError(
                    f"Ollama HTTP {response.status_code}: {detail}"
                )

        return response

    except requests.exceptions.Timeout as exc:

        raise RuntimeError(
            f"Ollama phản hồi quá {timeout or REQUEST_TIMEOUT} giây."
        ) from exc

    except requests.exceptions.ConnectionError as exc:

        raise RuntimeError(
            f"Không thể kết nối đến Ollama: {OLLAMA_URL}"
        ) from exc

    except requests.exceptions.RequestException as exc:

        raise RuntimeError(
            f"Lỗi gửi request đến Ollama: {exc}"
        ) from exc


# =====================================================
# GỌI MODEL OLLAMA
# =====================================================

def ask_ollama(question):

    if not MODEL:
        raise RuntimeError(
            "Chưa cấu hình OLLAMA_MODEL trên Vercel."
        )

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

    response = ollama_request(
        "/api/chat",
        payload=payload,
    )

    try:
        result = response.json()

    except ValueError as exc:
        raise RuntimeError(
            "Ollama trả về JSON không hợp lệ."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            "Dữ liệu trả về từ Ollama không hợp lệ."
        )

    message = result.get("message", {})

    answer = (
        message.get("content", "")
        if isinstance(message, dict)
        else ""
    )

    answer = str(answer).strip()

    if not answer:
        answer = str(
            result.get("response", "")
        ).strip()

    if not answer:
        raise RuntimeError(
            "Model không trả về nội dung văn bản."
        )

    return answer


# =====================================================
# TRANG CHỦ
# =====================================================

@app.get("/")
def home():

    index_file = PROJECT_DIR / "index.html"

    if not index_file.is_file():
        return jsonify({
            "error": "Không tìm thấy index.html ở thư mục gốc."
        }), 404

    return send_from_directory(
        PROJECT_DIR,
        "index.html"
    )


# =====================================================
# KIỂM TRA KẾT NỐI
# =====================================================

@app.get("/api/health")
def health():

    config = {
        "OLLAMA_URL": bool(OLLAMA_URL),
        "OLLAMA_API_KEY": bool(OLLAMA_API_KEY),
        "OLLAMA_MODEL": bool(MODEL),
    }

    missing = [
        key for key, value in config.items()
        if not value
    ]

    if missing:
        return jsonify({
            "server": "ok",
            "ollama": "unavailable",
            "model": MODEL,
            "configuration": config,
            "error": "Thiếu cấu hình: " + ", ".join(missing),
        })

    try:

        response = ollama_request(
            "/api/tags",
            timeout=15,
        )

        data = response.json()

        available_models = [
            item.get("name", "")
            for item in data.get("models", [])
            if isinstance(item, dict)
        ]

        return jsonify({
            "server": "ok",
            "ollama": "ok",
            "model": MODEL,
            "model_installed": MODEL in available_models,
            "available_models": available_models,
            "configuration": config,
            "note": "Danh sách tags không nhất thiết thể hiện đầy đủ model Cloud."
        })

    except Exception as exc:

        app.logger.warning(
            "Ollama health error: %s",
            str(exc)
        )

        return jsonify({
            "server": "ok",
            "ollama": "unavailable",
            "model": MODEL,
            "configuration": config,
            "error": str(exc),
        })


# =====================================================
# CHAT
# =====================================================

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
            "answer": "Nova chưa kết nối hoặc nhận được phản hồi từ Ollama.",
            "detail": str(exc),
            "error_type": type(exc).__name__,
        }), 502


# =====================================================
# TƯ VẤN TỔ HỢP MÔN
# =====================================================

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

        return jsonify({
            "answer": answer
        })

    except Exception as exc:

        app.logger.exception(
            "Ollama recommendation error"
        )

        return jsonify({
            "answer": "Nova chưa tạo được gợi ý từ Ollama.",
            "detail": str(exc),
            "error_type": type(exc).__name__,
        }), 502


# =====================================================
# CHẠY LOCAL
# =====================================================

if __name__ == "__main__":

    from waitress import serve
    import webbrowser

    host = "127.0.0.1"
    port = 5000

    url = f"http://{host}:{port}"

    print("\n================================")
    print("       NOVA AI ĐANG CHẠY")
    print("================================")
    print(f"Website: {url}")
    print(f"Ollama URL: {OLLAMA_URL}")
    print(f"Model: {MODEL}")
    print(
        "API Key:",
        "Đã cấu hình" if OLLAMA_API_KEY else "Chưa cấu hình"
    )
    print("================================\n")

    webbrowser.open(url)

    serve(
        app,
        host=host,
        port=port
    )
