from flask import Flask, Response, request, jsonify, send_from_directory
import serial
import time
import threading
import os

# ================== GEMINI - PHIÊN BẢN MỚI (2026) ==================
import google.generativeai as genai
from google.generativeai.types import GenerateContentConfig

app = Flask(__name__)

# ================== CẤU HÌNH ==================
SERIAL_PORT = "COM8"
BAUD_RATE = 9600

# ================== GEMINI ==================
GEMINI_API_KEY_MAIN = os.environ.get("GEMINI_API_KEY_MAIN")
GEMINI_API_KEY_LEARNING = os.environ.get("GEMINI_API_KEY_LEARNING") or GEMINI_API_KEY_MAIN

print(f"🔑 Gemini Key: {str(GEMINI_API_KEY_MAIN)[:15]}...")

try:
    genai.configure(api_key=GEMINI_API_KEY_MAIN)
    print("✅ Khởi tạo Gemini thành công!")
except Exception as e:
    print(f"❌ Lỗi khởi tạo Gemini: {e}")

MAIN_MODEL_NAME = "gemini-2.5-flash"
LEARNING_MODEL_NAME = "gemini-2.5-flash-lite"

MAIN_SYSTEM = """
Bạn là Chatbot Thiên Văn thông minh, hỗ trợ học sinh sử dụng kính thiên văn trong học tập STEM.
Nhiệm vụ: Giải thích thiên văn, hướng dẫn sử dụng kính, gợi ý quan sát.
Phong cách: Thân thiện, dễ hiểu, phù hợp học sinh THPT.
"""

LEARNING_FORMAT_RULES = """
Trả lời tiếng Việt, thân thiện như giáo viên. Viết văn xuôi, ngắn gọn, không markdown.
"""

_main_chat_lock = threading.Lock()
_main_chat_history = []

# ================== ARDUINO ==================
ser = None
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2.5)
    print(f"✅ Kết nối Arduino thành công qua {SERIAL_PORT}")
except Exception as e:
    print(f"⚠️ Không kết nối được Arduino: {e}")
    ser = None

def _build_history_contents(history_list):
    contents = []
    for turn in history_list:
        contents.append({
            "role": turn["role"],
            "parts": [genai.types.Part.from_text(text=p) for p in turn["parts"]]
        })
    return contents

# ================== ROUTES ==================
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/command', methods=['POST'])
def command():
    data = request.get_json() or {}
    cmd = data.get('cmd', '')
    if cmd and ser:
        try:
            ser.write((cmd + '\n').encode())
        except Exception as e:
            print(f"❌ Lỗi Arduino: {e}")
    return "OK"

# ----- Tab Chat chính -----
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({"response": "Bạn muốn hỏi gì về thiên văn?"})

    try:
        model = genai.GenerativeModel(MAIN_MODEL_NAME)
        contents = _build_history_contents(_main_chat_history)
        contents.append({
            "role": "user", 
            "parts": [genai.types.Part.from_text(text=user_message)]
        })

        resp = model.generate_content(
            contents,
            generation_config=GenerateContentConfig(
                system_instruction=MAIN_SYSTEM,
                temperature=0.7,
                max_output_tokens=1000
            )
        )
        reply = (resp.text or "").strip() or "Xin lỗi, mình chưa nghĩ ra câu trả lời."

        _main_chat_history.append({"role": "user", "parts": [user_message]})
        _main_chat_history.append({"role": "model", "parts": [reply]})
        if len(_main_chat_history) > 40:
            del _main_chat_history[:2]

        return jsonify({"response": reply})
    except Exception as e:
        print(f"❌ Chat error: {e}")
        return jsonify({"response": "Lỗi kết nối AI. Thử lại sau nhé!"})

# ----- Learning Hub chat -----
@app.route('/learning_chat', methods=['POST'])
def learning_chat():
    data = request.get_json() or {}
    system_prompt = data.get('system_prompt', '')
    messages = data.get('messages', [])

    try:
        full_system = system_prompt + "\n\n" + LEARNING_FORMAT_RULES
        model = genai.GenerativeModel(LEARNING_MODEL_NAME)

        contents = _build_history_contents(messages[:-1])
        last_msg = messages[-1].get('content', '')
        contents.append({"role": "user", "parts": [genai.types.Part.from_text(text=last_msg)]})

        resp = model.generate_content(
            contents,
            generation_config=GenerateContentConfig(
                system_instruction=full_system,
                temperature=0.8,
                max_output_tokens=800
            )
        )
        reply = (resp.text or "").strip() or "Xin lỗi, mình chưa nghĩ ra câu trả lời."
    except Exception as e:
        print(f"❌ Learning chat error: {e}")
        reply = "Xin lỗi, AI đang gặp sự cố. Thử lại nhé! 🙏"

    return jsonify({"reply": reply})

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    print("🌌 Kính Thiên Văn STEM đang chạy trên Render...")
    app.run(host='0.0.0.0', port=5000, threaded=True)
