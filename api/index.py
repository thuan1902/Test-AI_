    answer = (
        result.get("message", {}).get("content", "")
        if isinstance(result, dict) else ""
    ).strip()

    if not answer:
        raise RuntimeError(
            "Model không trả về nội dung. Hãy kiểm tra tên model và phản hồi từ Ollama."
        )
    return answer


# =========================
# TRANG CHỦ
# =========================

@app.get("/")
def home():
    if (PROJECT_DIR / "index.html").is_file():
        return send_from_directory(PROJECT_DIR, "index.html")
    return jsonify({"server": "ok", "message": "Nova AI API đang hoạt động."})


# =========================
# KIỂM TRA SERVER
# =========================

@app.get("/api/health")
def health():
    configured = bool(OLLAMA_API_KEY and MODEL and OLLAMA_URL)
    return jsonify({
        "server": "ok",
        "ollama_configured": "https://ollama.com",
        "model": "gemma4:31b-cloud",
        "message": (
            "Đã cấu hình Ollama Cloud."
            if configured
            else "Thiếu OLLAMA_API_KEY, OLLAMA_MODEL hoặc OLLAMA_URL."
        ),
    }), 200 if configured else 503


# =========================
# CHAT: NHẬN LỊCH SỬ TỪ FRONTEND
# =========================

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = str(data.get("message", "")).strip()
    history = data.get("history", [])

    if not question:
        return jsonify({"answer": "Bạn hãy nhập câu hỏi nhé."}), 400
    if not isinstance(history, list):
        history = []

    try:
        answer = ask_ollama(question, history=history)
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
        return jsonify({"answer": "Chưa có dữ liệu tổ hợp để tư vấn."}), 400

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
        return jsonify({"answer": ask_ollama(question)})
    except Exception as exc:
        app.logger.exception("Ollama recommendation error")
        return jsonify({
            "answer": "Nova chưa tạo được gợi ý từ Ollama Cloud.",
            "detail": str(exc),
        }), 502


# Vercel sẽ quản lý việc khởi chạy ứng dụng.
