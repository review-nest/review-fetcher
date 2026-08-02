from flask import Flask, render_template, request, send_file
from google_play_scraper import reviews, Sort, app as play_app
import threading
import requests
import json
import re
import time
import os
from PIL import Image, ImageDraw, ImageFont

# MoviePy Compatibility
try:
    from moviepy.editor import ImageClip, concatenate_videoclips
except ImportError:
    from moviepy import ImageClip, concatenate_videoclips

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
# SAFE FRAME GENERATOR (No Font Crash)
# =====================================
def create_review_frame(user_name, rating_score, content, app_title, output_path):
    img = Image.new('RGB', (720, 1280), color='#f1f5f9')
    draw = ImageDraw.Draw(img)

    # Card background
    draw.rectangle([40, 200, 680, 1080], fill="#ffffff", outline="#cbd5e1", width=2)

    # Title & User
    draw.text((70, 240), f"App: {str(app_title)[:25]}", fill="#0f172a")
    draw.text((70, 290), f"User: {str(user_name)[:25]}", fill="#334155")
    
    stars = "★ " * int(rating_score if rating_score else 5)
    draw.text((70, 340), f"Rating: {stars}", fill="#01875f")
    draw.line([(70, 390), (650, 390)], fill="#e2e8f0", width=2)

    # Content Line Wrapper
    words = str(content).split()
    lines, current_line = [], ""
    for word in words:
        if len(current_line + " " + word) <= 30:
            current_line += " " + word
        else:
            lines.append(current_line.strip())
            current_line = word
    if current_line: lines.append(current_line.strip())

    y = 420
    for line in lines[:10]:
        draw.text((70, y), line, fill="#1e293b")
        y += 40

    img.save(output_path)

# =====================================
# DIRECT PAYLOAD VIDEO GENERATOR
# =====================================
@app.route("/generate-video", methods=["POST"])
def generate_video():
    try:
        req_data = request.get_json(force=True, silent=True) or {}
        reviews_list = req_data.get("reviews", [])
        app_title = req_data.get("app_title", "Play Store App")

        if not reviews_list:
            return "No reviews received to build video", 400

        clips = []
        temp_files = []

        # Process max 10 reviews for smooth render
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
            
            # Create Clip with duration
            clip = ImageClip(frame_path).set_duration(3.0)
            clips.append(clip)

        final_clip = concatenate_videoclips(clips, method="compose")
        out_path = "/tmp/reviews_video.mp4" if os.path.exists("/tmp") else "reviews_video.mp4"
        
        final_clip.write_videofile(
            out_path, 
            fps=24, 
            codec="libx264", 
            audio=False, 
            preset="ultrafast"
        )

        # Cleanup Frame Images
        for f in temp_files:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass

        return send_file(out_path, as_attachment=True, download_name="PlayStore_Reviews_Video.mp4", mimetype="video/mp4")

    except Exception as e:
        print("VIDEO RENDER CRASH LOG:", str(e))
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
                                             
