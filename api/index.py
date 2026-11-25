import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory


# ============================================================
# NOVA AI - FLASK BACKEND + OLLAMA
# ============================================================

# api/index.py -> BASE_DIR = thư mục api, PROJECT_DIR = thư mục gốc
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# Đọc .env ở thư mục gốc trước; hỗ trợ thêm api/.env nếu dự án đang đặt tại đó.
# override=False để biến môi trường của Vercel luôn được ưu tiên.
load_dotenv(PROJECT_DIR / ".env", override=False, encoding="utf-8")
load_dotenv(BASE_DIR / ".env", override=False, encoding="utf-8")

OLLAMA_URL = os.getenv("OLLAMA_URL", "https://ollama.com").strip().rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip()

try:
    REQUEST_TIMEOUT = max(10, int(os.getenv("OLLAMA_TIMEOUT", "180")))
except ValueError:
    REQUEST_TIMEOUT = 180

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

SYSTEM_PROMPT = """
Bạn là Nova AI, trợ lý tư vấn chọn tổ hợp môn lớp 10.

Quy tắc:
- Trả lời bằng tiếng Việt.
- Thân thiện, rõ ràng, dễ hiểu với học sinh.
- Khi tư vấn tổ hợp, chỉ sử dụng các tổ hợp được cung cấp.
- Giải thích lý do cho từng đề xuất.
- Không tự bịa dữ liệu hoặc thông tin tuyển sinh.
- Nhắc học sinh xác nhận phương án chính thức với nhà trường.
""".strip()


def is_ollama_cloud():
    """Nhận diện máy chủ Ollama Cloud chính thức."""
    host = (urlparse(OLLAMA_URL).hostname or "").lower()
    return host == "ollama.com" or host.endswith(".ollama.com")


def ollama_headers():
    """
    Tạo header cho Ollama.
    Ollama Cloud yêu cầu API key. Với Ollama tự host, có thể không cần key.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if OLLAMA_API_KEY:
        # Không yêu cầu người dùng ghi sẵn chữ Bearer trong biến môi trường.
        token = OLLAMA_API_KEY
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        headers["Authorization"] = f"Bearer {token}"

    elif is_ollama_cloud():
        raise RuntimeError(
            "Thiếu OLLAMA_API_KEY. Hãy thêm biến này trong Vercel "
            "Project Settings > Environment Variables."
        )

    return headers


def ollama_error_message(response):
    """Đọc lỗi từ Ollama mà không làm lộ API key."""
    try:
        data = response.json()
        if isinstance(data, dict):
            return str(data.get("error") or data.get("message") or response.text)
    except (ValueError, requests.exceptions.JSONDecodeError):
        pass
    return response.text or "Ollama không cung cấp chi tiết lỗi."


def request_ollama_chat(messages):
    if not OLLAMA_URL:
        raise RuntimeError("Chưa cấu hình OLLAMA_URL.")
    if not OLLAMA_MODEL:
        raise RuntimeError("Chưa cấu hình OLLAMA_MODEL.")

    url = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    try:
        response = requests.post(
            url,
            headers=ollama_headers(),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

    except requests.exceptions.HTTPError as exc:
        failed_response = exc.response
        status = failed_response.status_code if failed_response is not None else "?"
        detail = (
            ollama_error_message(failed_response)
            if failed_response is not None
            else str(exc)
        )

        if status == 401:
            raise RuntimeError(
                "Ollama trả về HTTP 401 Unauthorized. Backend đã nhận request "
                "nhưng Ollama không chấp nhận API key. Hãy kiểm tra key được tạo "
                "từ Ollama API Keys, biến OLLAMA_API_KEY trên đúng Environment "
                "của Vercel và deployment mới nhất."
            ) from exc

        if status == 403:
            raise RuntimeError(
                "Ollama trả về HTTP 403 Forbidden. API key không có quyền "
                f"truy cập tài nguyên/model này. Chi tiết: {detail}"
            ) from exc

        if status == 404:
            raise RuntimeError(
                "Ollama trả về HTTP 404. Hãy kiểm tra endpoint và tên model "
                f"Cloud. Chi tiết: {detail}"
            ) from exc

        raise RuntimeError(f"Ollama trả về HTTP {status}: {detail}") from exc

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            f"Ollama không phản hồi trong {REQUEST_TIMEOUT} giây."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Không thể kết nối tới {OLLAMA_URL}. Hãy kiểm tra URL và kết nối mạng."
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Lỗi gửi request tới Ollama: {exc}") from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError("Ollama trả về dữ liệu JSON không hợp lệ.") from exc

    if not isinstance(result, dict):
        raise RuntimeError("Ollama trả về dữ liệu không đúng định dạng.")

    answer = str(result.get("message", {}).get("content", "")).strip()
    if not answer:
        raise RuntimeError(
            "Ollama đã phản hồi nhưng không có nội dung văn bản. "
            "Hãy kiểm tra model và quyền truy cập model."
        )

    return answer


def ask_ollama(question):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    return request_ollama_chat(messages)


# ============================================================
# TRANG CHỦ
# ============================================================

@app.get("/")
def home():
    index_file = PROJECT_DIR / "index.html"
    if not index_file.is_file():
        return (
            "Không tìm thấy index.html ở thư mục gốc dự án.",
            404,
        )
    return send_from_directory(PROJECT_DIR, "index.html")


# ============================================================
# KIỂM TRA BACKEND / OLLAMA
# ============================================================

@app.get("/api/health")
def health():
    if not OLLAMA_URL:
        return jsonify({
            "server": "ok",
            "ollama": "unavailable",
            "model": OLLAMA_MODEL,
            "error": "Thiếu OLLAMA_URL.",
        }), 200

    try:
        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            headers=ollama_headers(),
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()
        models = data.get("models", []) if isinstance(data, dict) else []
        available_models = [
            item.get("name", "")
            for item in models
            if isinstance(item, dict) and item.get("name")
        ]

        return jsonify({
            "server": "ok",
            "ollama": "ok",
            "model": OLLAMA_MODEL,
            "model_installed": OLLAMA_MODEL in available_models,
            "available_models": available_models,
            "note": (
                "Danh sách /api/tags có thể không liệt kê đầy đủ model Cloud. "
                "Phép thử chat thực tế mới xác nhận model có thể được gọi."
            ),
        }), 200

    except requests.exceptions.HTTPError as exc:
        failed_response = exc.response
        status = failed_response.status_code if failed_response is not None else "?"
        detail = (
            ollama_error_message(failed_response)
            if failed_response is not None
            else str(exc)
        )
        return jsonify({
            "server": "ok",
            "ollama": "unavailable",
            "model": OLLAMA_MODEL,
            "error": f"Ollama trả về HTTP {status}: {detail}",
        }), 200

    except Exception as exc:
        app.logger.exception("Ollama health check failed")
        return jsonify({
            "server": "ok",
            "ollama": "unavailable",
            "model": OLLAMA_MODEL,
            "error": str(exc),
        }), 200


# ============================================================
# CHAT
# ============================================================

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
        return jsonify({"answer": answer}), 200

    except Exception as exc:
        app.logger.exception("Ollama chat error")
        detail = str(exc)
        return jsonify({
            "answer": "Nova chưa kết nối hoặc chưa nhận được phản hồi từ Ollama.",
            "detail": detail,
            "error": detail,
            "error_type": type(exc).__name__,
        }), 502


# ============================================================
# TƯ VẤN TỔ HỢP MÔN
# ============================================================

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
""".strip()

    try:
        answer = ask_ollama(question)
        return jsonify({"answer": answer}), 200

    except Exception as exc:
        app.logger.exception("Ollama recommendation error")
        detail = str(exc)
        return jsonify({
            "answer": "Nova chưa tạo được gợi ý từ Ollama.",
            "detail": detail,
            "error": detail,
            "error_type": type(exc).__name__,
        }), 502


# ============================================================
# CHẠY LOCAL
# ============================================================

if __name__ == "__main__":
    from waitress import serve
    import webbrowser

    host = "127.0.0.1"
    port = int(os.getenv("PORT", "5000"))
    local_url = f"http://{host}:{port}"

    print("\n================================")
    print("          NOVA AI")
    print("================================")
    print(f"Website:   {local_url}")
    print(f"Ollama:    {OLLAMA_URL}")
    print(f"Model:     {OLLAMA_MODEL or '(chưa cấu hình)'}")
    print(f"API key:   {'Đã cấu hình' if OLLAMA_API_KEY else 'Chưa cấu hình'}")
    print("================================\n")

    webbrowser.open(local_url)
    serve(app, host=host, port=port)
