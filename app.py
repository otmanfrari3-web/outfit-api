from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)
session = requests.Session()

# ========== إعدادات API (OTMAN) ==========
API_KEY = "OTMAN"                     # مفتاح API الخاص بك
BACKGROUND_FILENAME = "outfit.png"       # الصورة الخلفية
IMAGE_TIMEOUT = 8
CANVAS_SIZE = (500, 500)
BACKGROUND_MODE = 'cover'

# ========== API معلومات اللاعب (OTMAN) ==========
# استخدم API معلومات اللاعب الخاص بك
PLAYER_INFO_URL = "https://otman-info.vercel.app/player-info?uid={uid}"

def fetch_player_info(uid: str):
    if not uid:
        return None
    try:
        url = PLAYER_INFO_URL.format(uid=uid)
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # استخراج الأزياء حسب تنسيق API الخاص بك
        player_data = data.get("data", {})
        profile = player_data.get("profileInfo", {})
        return {"EquippedOutfit": profile.get("clothes", [])}
    except Exception as e:
        print(f"خطأ في جلب معلومات اللاعب: {e}")
        return None

def fetch_and_process_image(image_url: str, size: tuple = None):
    try:
        resp = session.get(image_url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        if size:
            img = img.resize(size, Image.LANCZOS)
        return img
    except Exception:
        return None

@app.route('/')
def home():
    return jsonify({
        "name": "OTMAN OUTFIT API",
        "version": "2.0",
        "developer": "@otman_v2",
        "endpoints": {
            "/render?uid=UID&key=API_KEY": "جلب صورة اللاعب",
            "/health": "فحص حالة API"
        }
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "developer": "@otman_v2",
        "api_key": API_KEY
    })

@app.route('/render', methods=['GET'])
def outfit_image():
    uid = request.args.get('uid')
    key = request.args.get('key')

    if key != API_KEY:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    if not uid:
        return jsonify({'error': 'Missing uid parameter'}), 400

    player_data = fetch_player_info(uid)
    if player_data is None:
        return jsonify({'error': 'Failed to fetch player info'}), 500

    outfit_ids = player_data.get("EquippedOutfit", []) or []

    required_starts = ["211", "214", "211", "203", "204", "205", "203"]
    fallback_ids = ["211000000", "214000000", "208000000", "203000000", "204000000", "205000000", "212000000"]

    used_ids = set()

    def fetch_outfit_image(idx, code):
        matched = None
        for oid in outfit_ids:
            try:
                str_oid = str(oid)
            except Exception:
                continue
            if str_oid.startswith(code) and str_oid not in used_ids:
                matched = str_oid
                used_ids.add(str_oid)
                break
        if matched is None:
            matched = fallback_ids[idx]
        image_url = f'https://iconapi.wasmer.app/{matched}'
        return fetch_and_process_image(image_url, size=(150, 150))

    futures = []
    for idx, code in enumerate(required_starts):
        futures.append(executor.submit(fetch_outfit_image, idx, code))

    # تحميل الصورة الخلفية
    bg_path = os.path.join(os.path.dirname(__file__), BACKGROUND_FILENAME)
    try:
        background_image = Image.open(bg_path).convert("RGBA")
    except FileNotFoundError:
        return jsonify({'error': f'Background image not found: {BACKGROUND_FILENAME}'}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to open background image: {str(e)}'}), 500

    bg_w, bg_h = background_image.size

    if CANVAS_SIZE is None:
        canvas_w, canvas_h = bg_w, bg_h
        scale_x = scale_y = 1.0
        new_w, new_h = bg_w, bg_h
        background_resized = background_image
        offset_x, offset_y = 0, 0
    else:
        canvas_w, canvas_h = CANVAS_SIZE
        if BACKGROUND_MODE == 'contain':
            scale = min(canvas_w / bg_w, canvas_h / bg_h)
        else:
            scale = max(canvas_w / bg_w, canvas_h / bg_h)
        new_w = max(1, int(bg_w * scale))
        new_h = max(1, int(bg_h * scale))
        background_resized = background_image.resize((new_w, new_h), Image.LANCZOS)
        offset_x = (canvas_w - new_w) // 2
        offset_y = (canvas_h - new_h) // 2
        scale_x = new_w / bg_w
        scale_y = new_h / bg_h

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
    canvas.paste(background_resized, (offset_x, offset_y), background_resized)

    # مواقع الأزياء (7 فراغات حالياً)
    positions = [
        {'x': 350, 'y': 30, 'height': 150, 'width': 150},
        {'x': 575, 'y': 130, 'height': 150, 'width': 150},
        {'x': 665, 'y': 350, 'height': 150, 'width': 150},
        {'x': 575, 'y': 550, 'height': 150, 'width': 150},
        {'x': 350, 'y': 654, 'height': 150, 'width': 150},
        {'x': 135, 'y': 570, 'height': 150, 'width': 150},
        {'x': 135, 'y': 130, 'height': 150, 'width': 150}
    ]

    for idx, future in enumerate(futures):
        outfit_img = future.result()
        if not outfit_img:
            continue
        pos = positions[idx]
        paste_x = offset_x + int(pos['x'] * scale_x)
        paste_y = offset_y + int(pos['y'] * scale_y)
        paste_w = max(1, int(pos['width'] * scale_x))
        paste_h = max(1, int(pos['height'] * scale_y))
        resized = outfit_img.resize((paste_w, paste_h), Image.LANCZOS)
        canvas.paste(resized, (paste_x, paste_y), resized)

    output = BytesIO()
    canvas.save(output, format='PNG')
    output.seek(0)
    return send_file(output, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("="*50)
    print("🎨 OTMAN OUTFIT API")
    print(f"🔑 API Key: {API_KEY}")
    print(f"🌐 Running on port {port}")
    print("="*50)
    app.run(host='0.0.0.0', port=port, debug=False)
