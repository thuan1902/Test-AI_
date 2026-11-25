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
