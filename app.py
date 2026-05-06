from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)
session = requests.Session()

# ========== إعدادات API ==========
API_KEY = "OTMAN-V2"
BACKGROUND_FILENAME = "outfit.png"
IMAGE_TIMEOUT = 8
CANVAS_SIZE = (1000, 1000)  # حجم أكبر للصورة
BACKGROUND_MODE = 'cover'

# ========== API معلومات اللاعب ==========
PLAYER_INFO_URL = "https://otman-info.vercel.app/player-info?uid={uid}"

def fetch_player_info(uid: str):
    """جلب جميع معلومات اللاعب"""
    if not uid:
        return None
    try:
        url = PLAYER_INFO_URL.format(uid=uid)
        print(f"📡 جلب معلومات اللاعب: {url}")
        
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        # استخراج جميع البيانات
        basic = data.get("basicInfo", {})
        profile = data.get("profileInfo", {})
        social = data.get("socialInfo", {})
        clan = data.get("clanBasicInfo", {})
        pet = data.get("petInfo", {})
        
        # الأزياء
        clothes = profile.get("clothes", [])
        
        # السلاح (أول سلاح في القائمة)
        weapons = basic.get("weaponSkinShows", [])
        weapon_id = weapons[0] if weapons else None
        
        # الشخصية الرئيسية (Avatar)
        avatar_id = profile.get("avatarId", 102000005)
        
        # رقصة الدخول (إذا وجدت)
        dance_id = social.get("danceId", None)
        
        # الصورة الشخصية (HeadPic)
        head_id = basic.get("headPic", None)
        
        print(f"✅ UID: {uid}")
        print(f"   🎽 Clothes: {clothes}")
        print(f"   🔫 Weapon: {weapon_id}")
        print(f"   🎭 Avatar: {avatar_id}")
        print(f"   💃 Dance: {dance_id}")
        
        return {
            "EquippedOutfit": clothes,
            "weapon_id": weapon_id,
            "avatar_id": avatar_id,
            "dance_id": dance_id,
            "head_id": head_id,
            "name": basic.get("nickname", "Unknown"),
            "level": basic.get("level", 0),
            "guild": clan.get("clanName", "")
        }
        
    except Exception as e:
        print(f"❌ خطأ في جلب معلومات اللاعب {uid}: {e}")
        return None

def fetch_and_process_image(image_url: str, size: tuple = None, is_avatar=False):
    """جلب صورة من رابط مع إمكانية التحويل إلى دائري للشخصية"""
    try:
        resp = session.get(image_url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        
        if size:
            img = img.resize(size, Image.LANCZOS)
        
        # جعل الصورة دائرية إذا كانت الشخصية الرئيسية
        if is_avatar and size:
            mask = Image.new("L", size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, size[0], size[1]), fill=255)
            img.putalpha(mask)
        
        return img
    except Exception as e:
        print(f"❌ خطأ في جلب الصورة {image_url}: {e}")
        return None

def get_item_image(item_id: str, size: tuple = None):
    """جلب صورة سلاح أو أيقونة من iconapi"""
    if not item_id:
        return None
    url = f'https://iconapi.wasmer.app/{item_id}'
    return fetch_and_process_image(url, size)

def get_avatar_image(avatar_id: str, size: tuple = None):
    """جلب صورة الشخصية الرئيسية"""
    if not avatar_id:
        return None
    url = f'https://raw.githubusercontent.com/saarthak703/character-api-danger/main/pngs/{avatar_id}.png'
    return fetch_and_process_image(url, size, is_avatar=True)

def get_head_image(head_id: str, size: tuple = None):
    """جلب الصورة الشخصية (الوجه)"""
    if not head_id:
        return None
    url = f'https://raw.githubusercontent.com/saarthak703/character-api-danger/main/pngs/{head_id}.png'
    return fetch_and_process_image(url, size, is_avatar=True)

@app.route('/')
def home():
    return jsonify({
        "name": "OTMAN OUTFIT API",
        "version": "3.0",
        "developer": "@otman_v2",
        "description": "يستخرج: شخصية + أزياء + سلاح + رقصة",
        "endpoints": {
            "/render?uid=UID&key=API_KEY": "جلب صورة اللاعب الكاملة",
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

    print(f"🖼️ طلب صورة لـ UID: {uid}")

    if key != API_KEY:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    if not uid:
        return jsonify({'error': 'Missing uid parameter'}), 400

    player_data = fetch_player_info(uid)
    if player_data is None:
        return jsonify({'error': 'Failed to fetch player info'}), 500

    outfit_ids = player_data.get("EquippedOutfit", []) or []
    weapon_id = player_data.get("weapon_id")
    avatar_id = player_data.get("avatar_id")
    head_id = player_data.get("head_id")
    name = player_data.get("name", "Unknown")
    level = player_data.get("level", 0)

    # الأزياء المطلوبة (7 قطع)
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
        return get_item_image(matched, size=(150, 150))

    # جلب جميع الأزياء بالتوازي
    futures = []
    for idx, code in enumerate(required_starts):
        futures.append(executor.submit(fetch_outfit_image, idx, code))

    # جلب السلاح والشخصية الرئيسية والصورة الشخصية بالتوازي
    weapon_future = executor.submit(get_item_image, weapon_id, size=(200, 200))
    avatar_future = executor.submit(get_avatar_image, avatar_id, size=(300, 300))
    head_future = executor.submit(get_head_image, head_id, size=(180, 180))

    # تحميل الصورة الخلفية
    bg_path = os.path.join(os.path.dirname(__file__), BACKGROUND_FILENAME)
    try:
        background_image = Image.open(bg_path).convert("RGBA")
        print("✅ تم تحميل الصورة الخلفية")
    except FileNotFoundError:
        return jsonify({'error': f'Background image not found: {BACKGROUND_FILENAME}'}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to open background image: {str(e)}'}), 500

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

    # ============================================================
    # 8 فراغات للأزياء حول الشخصية
    # ============================================================
    positions = [
        {'x': 350, 'y': 30, 'size': 150},   # أعلى
        {'x': 575, 'y': 130, 'size': 150},  # أعلى يمين
        {'x': 665, 'y': 350, 'size': 150},  # يمين
        {'x': 575, 'y': 550, 'size': 150},  # أسفل يمين
        {'x': 350, 'y': 654, 'size': 150},  # أسفل
        {'x': 135, 'y': 570, 'size': 150},  # أسفل يسار
        {'x': 135, 'y': 130, 'size': 150},  # يسار
        {'x': 500, 'y': 350, 'size': 220}   # وسط (للسلاح)
    ]

    # رسم الأزياء
    for idx, future in enumerate(futures):
        outfit_img = future.result()
        if not outfit_img:
            continue
        pos = positions[idx]
        size = int(pos['size'] * scale_x)
        paste_x = offset_x + int(pos['x'] * scale_x)
        paste_y = offset_y + int(pos['y'] * scale_y)
        resized = outfit_img.resize((size, size), Image.LANCZOS)
        canvas.paste(resized, (paste_x, paste_y), resized)

    # رسم الشخصية الرئيسية في الوسط
    avatar_img = avatar_future.result()
    if avatar_img:
        avatar_size = int(250 * scale_x)
        avatar_x = offset_x + int(370 * scale_x) - (avatar_size // 4)
        avatar_y = offset_y + int(370 * scale_y) - (avatar_size // 4)
        avatar_resized = avatar_img.resize((avatar_size, avatar_size), Image.LANCZOS)
        canvas.paste(avatar_resized, (avatar_x, avatar_y), avatar_resized)

    # رسم السلاح في الفراغ الثامن (يمين الوسط)
    weapon_img = weapon_future.result()
    if weapon_img:
        pos = positions[7]
        size = int(pos['size'] * scale_x)
        paste_x = offset_x + int(pos['x'] * scale_x)
        paste_y = offset_y + int(pos['y'] * scale_y)
        weapon_resized = weapon_img.resize((size, size), Image.LANCZOS)
        canvas.paste(weapon_resized, (paste_x, paste_y), weapon_resized)

    # إضافة اسم المطور في أسفل اليمين
    try:
        draw = ImageDraw.Draw(canvas)
        draw.text((canvas_w - 150, canvas_h - 40), "@otman_v2", fill="white", font=None)
        
        # إضافة اسم اللاعب ومستواه في الأعلى
        draw.text((50, 20), f"{name} (Lvl.{level})", fill="white", font=None)
    except Exception as e:
        print(f"خطأ في إضافة النص: {e}")

    output = BytesIO()
    canvas.save(output, format='PNG')
    output.seek(0)
    print("✅ تم إنشاء الصورة بنجاح")
    return send_file(output, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("="*50)
    print("🎨 OTMAN OUTFIT API v3.0 (شخصية + أزياء + سلاح)")
    print(f"🔑 API Key: {API_KEY}")
    print(f"🌐 Running on port {port}")
    print("="*50)
    app.run(host='0.0.0.0', port=port, debug=False)
