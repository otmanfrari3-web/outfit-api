from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)
session = requests.Session()

API_KEY = "OTMAN-V2"
BACKGROUND_FILENAME = "outfit.png"
IMAGE_TIMEOUT = 8
CANVAS_SIZE = (500, 500)
BACKGROUND_MODE = 'cover'

PLAYER_INFO_URL = "https://otman-info.vercel.app/player-info?uid={uid}"

def fetch_player_info(uid: str):
    if not uid:
        return None
    try:
        url = PLAYER_INFO_URL.format(uid=uid)
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        basic = data.get("basicInfo", {})
        profile = data.get("profileInfo", {})
        clothes = profile.get("clothes", [])
        head_id = basic.get("headPic", None)
        return {"EquippedOutfit": clothes, "head_id": head_id}
    except Exception as e:
        print(f"خطأ: {e}")
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

def get_item_image(item_id: str, size: tuple = None):
    if not item_id:
        return None
    url = f'https://iconapi.wasmer.app/{item_id}'
    return fetch_and_process_image(url, size)

def get_head_image(head_id: str, size: tuple = None):
    if not head_id:
        return None
    # استخدام الرابط الصحيح لصور الرأس
    url = f'https://iconapi.wasmer.app/{head_id}'
    return fetch_and_process_image(url, size)

@app.route('/')
def home():
    return jsonify({
        "name": "OTMAN OUTFIT API",
        "version": "3.0",
        "developer": "@otman_v2",
        "endpoints": {
            "/render?uid=UID&key=API_KEY": "جلب صورة اللاعب (رأس + أزياء)",
            "/health": "فحص حالة API"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "developer": "@otman_v2", "api_key": API_KEY})

@app.route('/render', methods=['GET'])
def outfit_image():
    uid = request.args.get('uid')
    key = request.args.get('key')
    if key != API_KEY:
        return jsonify({'error': 'Invalid API key'}), 401
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    player_data = fetch_player_info(uid)
    if player_data is None:
        return jsonify({'error': 'Failed to fetch player info'}), 500

    outfit_ids = player_data.get("EquippedOutfit", []) or []
    head_id = player_data.get("head_id")

    required_starts = ["211", "214", "211", "203", "204", "205", "203"]
    fallback_ids = ["211000000", "214000000", "208000000", "203000000", "204000000", "205000000", "212000000"]
    used_ids = set()

    def fetch_outfit_image(idx, code):
        matched = None
        for oid in outfit_ids:
            try:
                str_oid = str(oid)
            except:
                continue
            if str_oid.startswith(code) and str_oid not in used_ids:
                matched = str_oid
                used_ids.add(str_oid)
                break
        if matched is None:
            matched = fallback_ids[idx]
        return get_item_image(matched, size=(150, 150))

    futures = []
    for idx, code in enumerate(required_starts):
        futures.append(executor.submit(fetch_outfit_image, idx, code))

    head_future = executor.submit(get_head_image, head_id, size=(180, 180))

    # تحميل الخلفية
    bg_path = os.path.join(os.path.dirname(__file__), BACKGROUND_FILENAME)
    try:
        background_image = Image.open(bg_path).convert("RGBA")
    except Exception as e:
        return jsonify({'error': f'Background error: {str(e)}'}), 500

    bg_w, bg_h = background_image.size
    canvas_w, canvas_h = CANVAS_SIZE
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

    # مواقع الأزياء
    positions = [
        {'x': 350, 'y': 30, 'size': 150},
        {'x': 575, 'y': 130, 'size': 150},
        {'x': 665, 'y': 350, 'size': 150},
        {'x': 575, 'y': 550, 'size': 150},
        {'x': 350, 'y': 654, 'size': 150},
        {'x': 135, 'y': 570, 'size': 150},
        {'x': 135, 'y': 130, 'size': 150},
    ]

    for idx, future in enumerate(futures):
        img = future.result()
        if not img:
            continue
        pos = positions[idx]
        size = int(pos['size'] * scale_x)
        paste_x = offset_x + int(pos['x'] * scale_x)
        paste_y = offset_y + int(pos['y'] * scale_y)
        resized = img.resize((size, size), Image.LANCZOS)
        canvas.paste(resized, (paste_x, paste_y), resized)

    # رسم الرأس في المنتصف
    head_img = head_future.result()
    if head_img:
        head_size = int(180 * scale_x)
        center_x = offset_x + int(350 * scale_x)
        center_y = offset_y + int(350 * scale_y)
        paste_x = center_x - head_size // 2
        paste_y = center_y - head_size // 2
        head_resized = head_img.resize((head_size, head_size), Image.LANCZOS)
        # جعل الصورة دائرية
        mask = Image.new("L", (head_size, head_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, head_size, head_size), fill=255)
        head_resized.putalpha(mask)
        canvas.paste(head_resized, (paste_x, paste_y), head_resized)

    output = BytesIO()
    canvas.save(output, format='PNG')
    output.seek(0)
    return send_file(output, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
