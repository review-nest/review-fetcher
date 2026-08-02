from flask import Flask, render_template, request, send_file
from google_play_scraper import reviews, Sort, app as play_app
import threading
import requests
import json
import re
import time
import os
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np

app = Flask(__name__)

# =====================================
# CONFIG
# =====================================
SHEET_URL = "https://script.google.com/macros/s/AKfycbxz8OWXF5MxvzJwok3reHunQhdTdMTPhEhk9AAFARGvP6U3wYAScuc9qXAZf-PdY1zyeQ/exec"
BOT_TOKEN = "8998711422:AAHFqUS18433G7FgaEU6cp4CbqEW0fwcM3Y"
CHAT_ID = "6371284862"

MAX_FETCH = 50000
BATCH_SIZE = 300

# =====================================
# UTILITY
# =====================================
def extract_package_id(input_str):
    input_str = input_str.strip()
    match = re.search(r'id=([a-zA-Z0-9_.]+)', input_str)
    if match:
        return match.group(1)
    return input_str

def send_bot_message(app_name, date, total):
    message = f"\n✅ App Synced\n📱 App : {app_name}\n📅 Date : {date}\n📊 Total Reviews : {total}\n✅ Upload Completed Successfully\n"
    try:  
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": message}, timeout=15)  
    except Exception as e:  
        print("Telegram Error :", e)

def save_batch(package, search_date, rows):
    try:  
        requests.post(SHEET_URL, json={"package": package, "search_date": search_date, "reviews": rows}, timeout=60)  
    except Exception as e:  
        print("Batch Upload Error :", e)

def process_and_upload_async(package, search_date, reviews_data, app_title):
    rows = []  
    for r in reviews_data:  
        at = r.get("at")  
        if hasattr(at, "strftime"):  
            date = at.strftime("%Y-%m-%d")  
            review_time = at.strftime("%H:%M:%S")  
        else:  
            date = str(at)[:10]  
            review_time = str(at)[11:19]  

        rows.append({  
            "username": str(r.get("userName", "")),  
            "review": str(r.get("content", "")),  
            "rating": int(r.get("score", 0)),  
            "date": date,  
            "time": review_time,  
            "package": package  
        })  

    if not rows: return  

    for i in range(0, len(rows), BATCH_SIZE):  
        batch = rows[i:i + BATCH_SIZE]  
        save_batch(package, rows[0]["date"], batch)  
        time.sleep(0.2)  

    send_bot_message(app_title, search_date, len(rows))

def is_symbol_only(text):
    return all(not ch.isalnum() for ch in text) if text else False

def match_keyword(comment, keyword):
    comment, keyword = str(comment).strip(), str(keyword).strip()
    if not comment or not keyword: return False
    if is_symbol_only(keyword):  
        m = re.search(r'([^\w\s]+)$', comment)  
        return m.group(1) == keyword if m else False
    pattern = r'(?<!\w)' + re.escape(keyword.lower()) + r'(?!\w)'  
    return re.search(pattern, comment.lower()) is not None

def keyword_match(comment, keyword_text):
    if not keyword_text: return True  
    keywords = [k.strip() for k in keyword_text.splitlines() if k.strip()]  
    if not keywords: return True  
    return any(match_keyword(comment, word) for word in keywords)

def review_pass(review, rating=None, keyword=None):
    if rating and str(review.get("score")) != str(rating): return False  
    if keyword and not keyword_match(review.get("content", ""), keyword): return False  
    return True

def get_app_info(package):
    try:  
        info = play_app(package, country="in", lang="en")  
        return {  
            "title": info.get("title", package),  
            "icon": info.get("icon", ""),  
            "developer": info.get("developer", ""),  
            "installs": info.get("installs", ""),  
            "score": info.get("score", "")  
        }  
    except Exception:  
        return {"title": package, "icon": "", "developer": "", "installs": "", "score": ""}

def fetch_reviews(package, search_date, rating=None, keyword=None):
    data, token, total_scanned = [], None, 0  
    while True:  
        try:  
            result, token = reviews(package, lang="en", country="in", sort=Sort.NEWEST, count=200, continuation_token=token)  
        except Exception: break  
        if not result: break  
        stop = False  
        for review in result:  
            total_scanned += 1  
            at = review.get("at")  
            r_date = at.strftime("%Y-%m-%d") if hasattr(at, "strftime") else str(at)[:10]  

            if r_date < search_date:  
                stop = True; break  
            if r_date != search_date or not review_pass(review, rating, keyword):  
                continue  
            data.append(review)  

        if stop or token is None or total_scanned >= MAX_FETCH: break  
        time.sleep(0.1)  
    return data  

# =====================================
# REEL FORMAT FRAME GENERATOR (1080x1920)
# =====================================
def create_review_frame(user_name, rating_score, content, app_title, output_path):
    # Standard Instagram/Shorts Reel Size
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H), color='#0f172a') # Stylish dark background
    draw = ImageDraw.Draw(img)

    # Decorative Reel Header
    draw.text((80, 180), "PLAY STORE REVIEWS", fill="#38bdf8")
    draw.text((80, 240), str(app_title)[:30], fill="#ffffff")

    # Review Card Container (Centered Reel Card)
    card_x1, card_y1 = 70, 450
    card_x2, card_y2 = 1010, 1450
    draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=30, fill="#1e293b", outline="#334155", width=3)

    # User Info
    draw.text((120, 520), f"👤  {str(user_name)[:22]}", fill="#f8fafc")
    
    # Rating Stars
    stars = "★ " * int(rating_score if rating_score else 5)
    draw.text((120, 590), stars, fill="#4ade80")
    
    draw.line([(120, 660), (960, 660)], fill="#334155", width=2)

    # Wrapped Text Content
    words = str(content).split()
    lines, current_line = [], ""
    for word in words:
        if len(current_line + " " + word) <= 28:
            current_line += " " + word
        else:
            lines.append(current_line.strip())
            current_line = word
    if current_line: lines.append(current_line.strip())

    y = 700
    for line in lines[:12]:
        draw.text((120, y), line, fill="#cbd5e1")
        y += 55

    # Save PNG Image
    img.save(output_path)

# =====================================
# REEL VIDEO GENERATOR (COMPATIBLE CODEC)
# =====================================
@app.route("/generate-video", methods=["POST"])
def generate_video():
    try:
        req_data = request.get_json(force=True, silent=True) or {}
        reviews_list = req_data.get("reviews", [])
        app_title = req_data.get("app_title", "Play Store App")

        if not reviews_list:
            return "No reviews received to build video", 400

        out_path = "/tmp/reel_video.mp4" if os.path.exists("/tmp") else "reel_video.mp4"
        
        # 1080x1920 Reel Dimensions
        width, height = 1080, 1920
        
        # Universal Codecs for Mobile Video Playback
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        fps = 30 # 30 FPS for smooth video creation
        video = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

        # Fallback codec if avc1 is not available on environment
        if not video.isOpened():
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            out_path = out_path.replace('.mp4', '.avi')
            video = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

        temp_files = []

        # Process max 10 reviews
        for idx, r in enumerate(reviews_list[:10]):
            frame_path = f"/tmp/frame_{idx}.png" if os.path.exists("/tmp") else f"frame_{idx}.png"
            create_review_frame(
                user_name=r.get("userName", "Google User"),
                rating_score=r.get("score", 5),
                content=r.get("content", ""),
                app_title=app_title,
                output_path=frame_path
            )
            temp_files.append(frame_path)
            
            frame = cv2.imread(frame_path)
            
            # Write 90 frames for each review (3 seconds display per review at 30 FPS)
            for _ in range(90):
                video.write(frame)

        video.release()

        # Cleanup Image Frames
        for f in temp_files:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass

        mimetype = "video/avi" if out_path.endswith('.avi') else "video/mp4"
        download_name = "PlayStore_Reel.avi" if out_path.endswith('.avi') else "PlayStore_Reel.mp4"

        return send_file(out_path, as_attachment=True, download_name=download_name, mimetype=mimetype)

    except Exception as e:
        print("VIDEO RENDER ERROR:", str(e))
        return str(e), 500

# =====================================
# MAIN ROUTE
# =====================================
@app.route("/", methods=["GET", "POST"])
def home():
    data, raw_input, app_info = [], "", {}  
    if request.method == "POST":  
        raw_input = request.form.get("package", "").strip()  
        date = request.form.get("date", "").strip()  
        rating = request.form.get("rating", "").strip()  
        keyword = request.form.get("keyword", "").strip()  

        package = extract_package_id(raw_input)
        if package: app_info = get_app_info(package)  
        if package and date:  
            data = fetch_reviews(package=package, search_date=date, rating=rating, keyword=keyword)  
            if len(data) > 0:  
                threading.Thread(target=process_and_upload_async, args=(package, date, data, app_info.get("title", package))).start()

    return render_template("index.html", reviews=data, package=raw_input, app_info=app_info)  

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
        
