import base64
import binascii
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
# Model riêng có khả năng nhận dạng âm thanh; cấu hình trong Vercel.
OLLAMA_STT_MODEL = os.getenv("OLLAMA_STT_MODEL", "").strip()

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
    Tạo header xác thực cho Ollama local qua Cloudflare Tunnel.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    token = os.environ.get("NOVA_TUNNEL_TOKEN", "").strip()

    if token:
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        headers["Authorization"] = f"Bearer {token}"

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
                "NOVA_TUNNEL_AUTH_FAILED: kiểm tra token giữa Vercel và proxy local."
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
    return send_from_directory(BASE_DIR, "index.html")



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
# SPEECH-TO-TEXT (STT) - NHẬN ÂM THANH TỪ ESP32
# ============================================================

@app.post("/api/stt")
def speech_to_text():
    """
    ESP32 gửi JSON: {"audio_base64": "...", "format": "wav"}.
    Backend giải mã WAV rồi chuyển tiếp tới Ollama OpenAI-compatible API.
    OLLAMA_STT_MODEL phải là model có hỗ trợ nhận đầu vào âm thanh.
    """
    if not OLLAMA_STT_MODEL:
        return jsonify({
            "error": "Chưa cấu hình OLLAMA_STT_MODEL trên Vercel.",
            "detail": "Hãy đặt tên model có khả năng nhận dạng âm thanh rồi deploy lại."
        }), 503

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Body phải là JSON hợp lệ."}), 400

    audio_base64 = data.get("audio_base64", "")
    audio_format = str(data.get("format", "wav")).lower().strip()

    if not isinstance(audio_base64, str) or not audio_base64:
        return jsonify({"error": "Thiếu trường audio_base64."}), 400
    if audio_format != "wav":
        return jsonify({"error": "Hiện chỉ hỗ trợ âm thanh WAV."}), 415

    # Giới hạn dữ liệu đầu vào để tránh request quá lớn trên serverless.
    if len(audio_base64) > 3_000_000:
        return jsonify({"error": "Âm thanh quá lớn. Hãy giảm thời lượng ghi âm."}), 413

    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError):
        return jsonify({"error": "Dữ liệu audio_base64 không hợp lệ."}), 400

    if len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        return jsonify({"error": "Dữ liệu gửi lên không phải file WAV hợp lệ."}), 400

    if not OLLAMA_URL:
        return jsonify({"error": "Chưa cấu hình OLLAMA_URL."}), 503

    # requests tự tạo multipart boundary; không gửi Content-Type: application/json.
    headers = ollama_headers()
    headers.pop("Content-Type", None)
    headers["Accept"] = "application/json"

    try:
        response = requests.post(
            f"{OLLAMA_URL}/v1/audio/transcriptions",
            headers=headers,
            data={
                "model": OLLAMA_STT_MODEL,
                "language": "vi",
                "response_format": "json",
            },
            files={"file": ("nova_recording.wav", audio_bytes, "audio/wav")},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        result = response.json()
        if isinstance(result, dict):
            recognized_text = str(result.get("text", "")).strip()
        else:
            recognized_text = str(result).strip()

        if not recognized_text:
            return jsonify({"error": "Model STT không trả về văn bản.", "detail": result}), 502

        return jsonify({"text": recognized_text}), 200

    except requests.exceptions.HTTPError as exc:
        failed_response = exc.response
        status = failed_response.status_code if failed_response is not None else 502
        detail = (
            ollama_error_message(failed_response)
            if failed_response is not None
            else str(exc)
        )
        app.logger.exception("Ollama STT HTTP error")
        return jsonify({
            "error": f"Ollama STT trả về HTTP {status}.",
            "detail": detail,
            "model": OLLAMA_STT_MODEL,
        }), 502

    except requests.exceptions.Timeout:
        app.logger.exception("Ollama STT timeout")
        return jsonify({"error": "Ollama STT hết thời gian chờ."}), 504

    except requests.exceptions.RequestException as exc:
        app.logger.exception("Ollama STT request failed")
        return jsonify({"error": "Không thể kết nối dịch vụ Ollama STT.", "detail": str(exc)}), 502

    except (ValueError, TypeError) as exc:
        app.logger.exception("Ollama STT response parse failed")
        return jsonify({"error": "Phản hồi STT không hợp lệ.", "detail": str(exc)}), 502


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
