from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)
session = requests.Session()

# ========== الإعدادات ==========
API_KEY = "OTMAN-V2"
BACKGROUND_FILENAME = "outfit.png"       # صورتك الخلفية
IMAGE_TIMEOUT = 8
CANVAS_SIZE = (500, 500)
BACKGROUND_MODE = 'cover'

# ========== رابط معلومات اللاعب ==========
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
        head_id = basic.get("headPic")
        return {"EquippedOutfit": clothes, "head_id": head_id}
    except Exception as e:
        print(f"خطأ في جلب المعلومات: {e}")
        return None

def fetch_image(url: str, size=None):
    try:
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        if size:
            img = img.resize(size, Image.LANCZOS)
        return img
    except Exception:
        return None

def get_clothes_image(item_id, size=(150,150)):
    if not item_id:
        return None
    url = f"https://iconapi.wasmer.app/{item_id}"
    return fetch_image(url, size)

def get_head_image(head_id, size=(180,180)):
    if not head_id:
        return None
    # استخدم رابطاً موثوقاً لصور الرأس
    url = f"https://iconapi.wasmer.app/{head_id}"
    return fetch_image(url, size)

@app.route('/')
def home():
    return jsonify({
        "name": "OTMAN OUTFIT API",
        "version": "3.0",
        "developer": "@otman_v2",
        "endpoints": {
            "/render?uid=UID&key=API_KEY": "صورة (رأس دائري + أزياء)",
            "/health": "فحص الحالة"
        }
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "developer": "@otman_v2"})

@app.route('/render', methods=['GET'])
def render():
    uid = request.args.get('uid')
    key = request.args.get('key')
    if key != API_KEY:
        return jsonify({'error': 'Invalid API key'}), 401
    if not uid:
        return jsonify({'error': 'Missing uid'}), 400

    data = fetch_player_info(uid)
    if not data:
        return jsonify({'error': 'Player not found'}), 500

    clothes_ids = data.get("EquippedOutfit", [])
    head_id = data.get("head_id")

    # قوائم الأزياء والبدائل
    required_starts = ["211","214","211","203","204","205","203"]
    fallback_ids    = ["211000000","214000000","208000000","203000000","204000000","205000000","212000000"]
    used = set()

    def get_match(idx, start):
        for cid in clothes_ids:
            sid = str(cid)
            if sid.startswith(start) and sid not in used:
                used.add(sid)
                return sid
        return fallback_ids[idx]

    futures = []
    for i, start in enumerate(required_starts):
        matched = get_match(i, start)
        futures.append(executor.submit(get_clothes_image, matched, (150,150)))

    # جلب صورة الرأس
    head_future = executor.submit(get_head_image, head_id, (180,180))

    # تحميل الخلفية
    bg_path = os.path.join(os.path.dirname(__file__), BACKGROUND_FILENAME)
    try:
        bg = Image.open(bg_path).convert("RGBA")
    except:
        return jsonify({'error': 'Background not found'}), 500

    # معالجة الحجم والتوسيط
    bg_w, bg_h = bg.size
    canvas_w, canvas_h = CANVAS_SIZE
    scale = max(canvas_w / bg_w, canvas_h / bg_h)
    new_w = int(bg_w * scale)
    new_h = int(bg_h * scale)
    bg_resized = bg.resize((new_w, new_h), Image.LANCZOS)
    offset_x = (canvas_w - new_w) // 2
    offset_y = (canvas_h - new_h) // 2

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0,0,0,255))
    canvas.paste(bg_resized, (offset_x, offset_y), bg_resized)

    # مواضع الأزياء (إحداثيات مطلقة بالنسبة للخلفية الأصلية 500x500)
    positions = [
        (350, 30),    # 0 أعلى
        (575, 130),   # 1 أعلى يمين
        (665, 350),   # 2 يمين
        (575, 550),   # 3 أسفل يمين
        (350, 654),   # 4 أسفل
        (135, 570),   # 5 أسفل يسار
        (135, 130)    # 6 يسار
    ]

    for idx, fu in enumerate(futures):
        img = fu.result()
        if img:
            x, y = positions[idx]
            px = offset_x + int(x * scale)
            py = offset_y + int(y * scale)
            w = int(150 * scale)
            h = int(150 * scale)
            resized = img.resize((w,h), Image.LANCZOS)
            canvas.paste(resized, (px, py), resized)

    # رسم الرأس الدائري في المنتصف
    head_img = head_future.result()
    if head_img:
        center_x = offset_x + int(350 * scale)
        center_y = offset_y + int(350 * scale)
        dia = int(180 * scale)
        # قناع دائري
        mask = Image.new("L", (dia, dia), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, dia, dia), fill=255)
        head_resized = head_img.resize((dia, dia), Image.LANCZOS)
        head_resized.putalpha(mask)
        paste_x = center_x - dia//2
        paste_y = center_y - dia//2
        canvas.paste(head_resized, (paste_x, paste_y), head_resized)

    # إرسال الصورة
    buf = BytesIO()
    canvas.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
