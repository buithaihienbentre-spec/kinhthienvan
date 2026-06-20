from flask import Flask, Response, request, jsonify, send_from_directory
# import cv2
import serial
import time
import threading
import os
import google.generativeai as genai
from google.generativeai import types

app = Flask(__name__)

# ================== CẤU HÌNH ==================
SERIAL_PORT = "COM8"
BAUD_RATE = 9600

# ================== GEMINI ==================
GEMINI_API_KEY_MAIN = os.environ.get("GEMINI_API_KEY_MAIN") 
GEMINI_API_KEY_LEARNING = os.environ.get("GEMINI_API_KEY_LEARNING") or GEMINI_API_KEY_MAIN

print(f"🔑 Gemini Key: {GEMINI_API_KEY_MAIN[:15]}...")

_client_main = None
_client_learning = None

try:
    _client_main = genai.Client(api_key=GEMINI_API_KEY_MAIN)
    _client_learning = genai.Client(api_key=GEMINI_API_KEY_LEARNING)
    print("✅ Khởi tạo Gemini Client thành công!")
except Exception as e:
    print(f"❌ Lỗi khởi tạo Gemini: {e}")

# === MODEL NAMES ĐÃ CẬP NHẬT (ổn định nhất hiện tại) ===
MAIN_MODEL_NAME = "gemini-2.5-flash"          # Model nhanh và mạnh
LEARNING_MODEL_NAME = "gemini-2.5-flash-lite" # Tiết kiệm + nhanh cho Learning Hub

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

_main_chat_lock = threading.Lock()
_main_chat_history = []

# ================== CAMERA ==================
class VideoCamera:
    def __init__(self):
        self.cap = None
        self.current_index = 0
        self.lock = threading.Lock()
        self.frame = None
        self.open_camera(self.current_index)

    def open_camera(self, index):
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.current_index = index
        return self.cap.isOpened()

    def update(self):
        while True:
            if self.cap is not None:
                ret, frame = self.cap.read()
                if ret:
                    with self.lock:
                        self.frame = frame.copy()
            time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return jpeg.tobytes()

    def switch_camera(self):
        for _ in range(3):
            self.current_index = (self.current_index + 1) % 3
            if self.open_camera(self.current_index):
                return True
        return False


# camera = VideoCamera()
# threading.Thread(target=camera.update, daemon=True).start()


# ================== ARDUINO ==================
ser = None
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2.5)
    print(f"✅ Kết nối Arduino thành công qua {SERIAL_PORT}")
except Exception as e:
    print(f"⚠️  Không kết nối được Arduino: {e}")
    ser = None


def _build_history_contents(history_list):
    contents = []
    for turn in history_list:
        contents.append(
            types.Content(
                role=turn["role"],
                parts=[types.Part.from_text(text=p) for p in turn["parts"]],
            )
        )
    return contents


# ================== ROUTES ==================
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/camera_index')
def camera_index():
    return jsonify({"index": camera.current_index})

def gen():
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.12)

@app.route('/video_feed')
def video_feed():
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/switch_camera', methods=['POST'])
def switch_camera():
    camera.switch_camera()
    return "OK"

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

    if _client_main is None:
        return jsonify({"response": "Server chưa cấu hình Gemini API Key."})

    with _main_chat_lock:
        try:
            contents = _build_history_contents(_main_chat_history)
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

            resp = _client_main.models.generate_content(
                model=MAIN_MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=MAIN_SYSTEM,
                    temperature=0.7,
                    max_output_tokens=1000
                ),
            )
            reply = (resp.text or "").strip() or "Xin lỗi, mình chưa nghĩ ra câu trả lời. Bạn hỏi lại nhé!"

            _main_chat_history.append({"role": "user", "parts": [user_message]})
            _main_chat_history.append({"role": "model", "parts": [reply]})
            if len(_main_chat_history) > 40:
                del _main_chat_history[:2]

            return jsonify({"response": reply})
        except Exception as e:
            print(f"❌ Chat error: {e}")
            return jsonify({"response": f"Lỗi: {str(e)[:150]}"})


# ----- Learning Hub chat -----
@app.route('/learning_chat', methods=['POST'])
def learning_chat():
    data = request.get_json() or {}
    system_prompt = data.get('system_prompt', 'Bạn là AI gia sư Thiên Văn STEM thân thiện.')
    messages = data.get('messages', [])
    if not messages:
        return jsonify({"reply": "Không có tin nhắn."})

    if _client_learning is None:
        return jsonify({"reply": "Server chưa cấu hình Gemini API Key."})

    full_system = system_prompt + "\n\n" + LEARNING_FORMAT_RULES

    gemini_history = []
    for msg in messages[:-1]:
        role = "user" if msg.get('role') == 'user' else "model"
        gemini_history.append({"role": role, "parts": [msg.get('content', '')]})

    last_content = messages[-1].get('content', '')

    try:
        contents = _build_history_contents(gemini_history)
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=last_content)]))

        resp = _client_learning.models.generate_content(
            model=LEARNING_MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=full_system,
                temperature=0.8,
                max_output_tokens=800
            ),
        )
        reply = (resp.text or "").strip() or "Xin lỗi, mình chưa nghĩ ra câu trả lời. Bạn hỏi lại nhé!"
    except Exception as e:
        print(f"❌ Learning chat error: {e}")
        reply = f"Xin lỗi, AI đang gặp sự cố. Thử lại nhé! 🙏"

    return jsonify({"reply": reply})


# ----- Learning Report -----
@app.route('/learning_report', methods=['POST'])
def learning_report():
    data = request.get_json() or {}
    prompt_text = data.get('prompt', '').strip()
    if not prompt_text:
        return jsonify({"report": "Không có dữ liệu."})

    if _client_learning is None:
        return jsonify({"report": "Server chưa cấu hình Gemini API Key."})

    full_system = (
        "Bạn là AI gia sư Thiên Văn STEM thân thiện. "
        "Hãy viết báo cáo học tập cá nhân hóa cho học sinh: thân thiện, khuyến khích, thực tế.\n\n"
        + LEARNING_FORMAT_RULES
    )

    try:
        resp = _client_learning.models.generate_content(
            model=LEARNING_MODEL_NAME,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])],
            config=types.GenerateContentConfig(system_instruction=full_system),
        )
        report = (resp.text or "").strip() or "Không thể tạo báo cáo lúc này."
    except Exception as e:
        print(f"❌ Learning report error: {e}")
        report = f"Không thể tạo báo cáo. Thử lại sau. 🙏"

    return jsonify({"report": report})


if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    print("🌌 Kính Thiên Văn STEM đang chạy...")
    print("📍 Truy cập: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
