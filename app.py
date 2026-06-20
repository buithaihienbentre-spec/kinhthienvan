from flask import Flask, request, jsonify, send_from_directory
import os

import google.generativeai as genai

app = Flask(__name__)

# ================== GEMINI ==================
GEMINI_API_KEY_MAIN = os.environ.get("GEMINI_API_KEY_MAIN")
GEMINI_API_KEY_LEARNING = os.environ.get("GEMINI_API_KEY_LEARNING") or GEMINI_API_KEY_MAIN

print(f"🔑 MAIN Key: {str(GEMINI_API_KEY_MAIN)[:15]}...")
print(f"🔑 LEARNING Key: {str(GEMINI_API_KEY_LEARNING)[:15]}...")

try:
    genai.configure(api_key=GEMINI_API_KEY_MAIN)
    print("✅ Gemini cấu hình thành công!")
except Exception as e:
    print(f"❌ Lỗi Gemini: {e}")

# ================== SYSTEM PROMPT ==================
MAIN_SYSTEM = """
Bạn là Chatbot Thiên Văn thông minh, hỗ trợ học sinh sử dụng kính thiên văn trong học tập STEM.

Nhiệm vụ:
- Giải thích các hiện tượng thiên văn: Mặt Trăng, hành tinh, chòm sao, tinh vân
- Hướng dẫn sử dụng kính thiên văn: xoay, zoom, căn chỉnh
- Gợi ý nên quan sát gì theo thời gian (ban đêm, vị trí bầu trời)
- Trả lời ngắn gọn, dễ hiểu, phù hợp học sinh THPT

Phong cách:
- Thân thiện, dễ hiểu
- Có thể đưa ví dụ thực tế
- Không dùng ký tự đặc biệt phức tạp
"""

LEARNING_FORMAT_RULES = """
Quy tắc định dạng:
- Trả lời tiếng Việt, thân thiện như giáo viên
- KHÔNG dùng markdown, không **, không #, không bullet
- Viết văn xuôi, ngắn gọn, dễ hiểu
- Khuyến khích học sinh, tích cực
- Nếu không chắc: "Bạn nên tham khảo thêm tài liệu hoặc hỏi giáo viên nhé!"
"""

# ================== ROUTES ==================
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/command', methods=['POST'])
def command():
    return "OK"

# ================== CHAT CHÍNH ==================
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({"response": "Bạn muốn hỏi gì về thiên văn?"})

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=MAIN_SYSTEM
        )
        chat = model.start_chat(history=[])
        response = chat.send_message(user_message)
        return jsonify({"response": response.text.strip()})
    except Exception as e:
        print(f"❌ Chat error: {e}")
        return jsonify({"response": "Xin lỗi, AI đang gặp sự cố. Thử lại sau nhé!"})


# ================== LEARNING CHAT (Đang dùng) ==================
@app.route('/learning_chat', methods=['POST'])
def learning_chat():
    data = request.get_json() or {}
    system_prompt = data.get('system_prompt', '')
    messages = data.get('messages', [])

    try:
        full_system = LEARNING_SYSTEM + "\n\n" + system_prompt
        
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=full_system
        )
        
        chat = model.start_chat(history=[])
        last_msg = messages[-1].get('content', '') if messages else "Xin chào"
        
        response = chat.send_message(last_msg)
        return jsonify({"reply": response.text.strip()})
    except Exception as e:
        print(f"❌ Learning chat error: {e}")
        return jsonify({"reply": "Xin lỗi, AI đang gặp sự cố. Thử lại nhé! 🙏"})


if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    print("🌌 Kính Thiên Văn STEM đang chạy...")
    app.run(host='0.0.0.0', port=5000, threaded=True)
