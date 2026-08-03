from flask import Flask, render_template, request, send_file
from google_play_scraper import reviews, Sort, app as play_app
import threading
import requests
import json
import re
import time
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# =====================================
# MOVIEPY SAFE IMPORT FIX (v1.x & v2.x)
# =====================================
try:
    from moviepy.editor import ImageClip, concatenate_videoclips
except ImportError:
    from moviepy.video.io.ImageClip import ImageClip
    from moviepy.video.compositing.concatenate import concatenate_videoclips

app = Flask(__name__)

# =====================================
# CONFIG
# =====================================
SHEET_URL = "https://script.google.com/macros/s/AKfycbxz8OWXF5MxvzJwok3reHunQhdTdMTPhEhk9AAFARGvP6U3wYAScuc9qXAZf-PdY1zyeQ/exec"
BOT_TOKEN = "8998711422:AAHFqUS18433G7FgaEU6cp4CbqEW0fwcM3Y"
CHAT_ID = "6371284862"

MAX_FETCH = 50000
BATCH_SIZE = 300

# Global storage for fetched reviews and app info
CURRENT_FETCHED_REVIEWS = []
CURRENT_APP_INFO = {}

# =====================================
# UTILITY: EXTRACT PACKAGE NAME FROM LINK/ID
# =====================================
def extract_package_id(input_str):
    if not input_str:
        return ""
    input_str = input_str.strip()
    match = re.search(r'id=([a-zA-Z0-9_.]+)', input_str)
    if match:
        return match.group(1)
    return input_str

# =====================================
# TELEGRAM BOT
# =====================================
def send_bot_message(app_name, date, total):
    message = f"""
✅ App Synced
📱 App : {app_name}
📅 Date : {date}
📊 Total Reviews : {total}
✅ Upload Completed Successfully
"""
    try:  
        requests.post(  
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",  
            json={  
                "chat_id": CHAT_ID,  
                "text": message  
            },  
            timeout=30  
        )  
    except Exception as e:  
        print("Telegram Error :", e)

# =====================================
# GOOGLE SHEET UPLOAD (BACKGROUND TASK)
# =====================================
def save_batch(package, search_date, rows):
    try:  
        response = requests.post(  
            SHEET_URL,  
            json={  
                "package": package,  
                "search_date": search_date,  
                "reviews": rows  
            },  
            timeout=120  
        )  
        print("Sheet Response:", response.text)  
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

    if not rows:  
        return  

    print(f"Async Task Started for {len(rows)} reviews...")  

    for i in range(0, len(rows), BATCH_SIZE):  
        batch = rows[i:i + BATCH_SIZE]  
        print(f"Uploading Batch {i + len(batch)}/{len(rows)}")  
        save_batch(package, rows[0]["date"], batch)  
        time.sleep(0.3)  

    print("Google Sheet Upload Completed via Background Thread")
    send_bot_message(app_title, search_date, len(rows))

# =====================================
# MATCH SYSTEM & KEYWORDS
# =====================================
def is_symbol_only(text):
    if not text:  
        return False  
    return all(not ch.isalnum() for ch in text)

def match_keyword(comment, keyword):
    comment = str(comment).strip()  
    keyword = str(keyword).strip()  

    if not comment or not keyword:  
        return False  

    if is_symbol_only(keyword):  
        m = re.search(r'([^\w\s]+)$', comment)  
        if not m:  
            return False  
        return m.group(1) == keyword  

    pattern = r'(?<!\w)' + re.escape(keyword.lower()) + r'(?!\w)'  
    return re.search(pattern, comment.lower()) is not None

def keyword_match(comment, keyword_text):
    if not keyword_text:  
        return True  

    keywords = [k.strip() for k in keyword_text.splitlines() if k.strip()]  

    if not keywords:  
        return True  

    for word in keywords:  
        if match_keyword(comment, word):  
            return True  

    return False

def review_pass(review, rating=None, keyword=None):
    if rating:  
        try:  
            if review.get("score") != int(rating):  
                return False  
        except:  
            return False  

    if keyword:  
        if not keyword_match(review.get("content", ""), keyword):  
            return False  

    return True

# =====================================
# APP INFO
# =====================================
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
    except Exception as e:  
        print("App Info Error :", e)  
        return {  
            "title": package,  
            "icon": "",  
            "developer": "",  
            "installs": "",  
            "score": ""  
        }

def review_date(review):
    at = review.get("at")  
    if hasattr(at, "strftime"):  
        return at.strftime("%Y-%m-%d")  
    return str(at)[:10]  

# =====================================
# REVIEW FETCH ENGINE
# =====================================
def fetch_reviews(package, search_date, rating=None, keyword=None):
    data = []  
    token = None  
    total_scanned = 0  

    while True:  
        try:  
            result, token = reviews(  
                package,  
                lang="en",  
                country="in",  
                sort=Sort.NEWEST,  
                count=200,  
                continuation_token=token  
            )  
        except Exception as e:  
            print("Fetch Error :", e)  
            break  

        if not result:  
            break  

        stop = False  

        for review in result:  
            total_scanned += 1  
            r_date = review_date(review)  

            if r_date < search_date:  
                stop = True  
                break  

            if r_date != search_date:  
                continue  

            if not review_pass(review, rating, keyword):  
                continue  

            data.append(review)  

        print(f"Scanned : {total_scanned} | Matched : {len(data)}")  

        if stop or token is None or total_scanned >= MAX_FETCH:  
            break  

        time.sleep(0.1)  

    return data  

# =====================================
# PERFECT FRAME GENERATOR FOR VIDEO
# =====================================
def create_review_frame(user_name, rating_score, content, app_title, output_path):
    img = Image.new('RGB', (1080, 1920), color='#f8fafc')
    draw = ImageDraw.Draw(img)

    try:
        font_header = ImageFont.truetype("arial.ttf", 45)
        font_sub = ImageFont.truetype("arial.ttf", 35)
        font_content = ImageFont.truetype("arial.ttf", 36)
    except:
        font_header = font_sub = font_content = ImageFont.load_default()

    # White Card Frame
    draw.rounded_rectangle([80, 450, 1000, 1450], radius=32, fill="#ffffff", outline="#dadce0", width=2)

    # App Info
    draw.text((120, 510), str(app_title)[:30], fill="#202124", font=font_header)
    draw.text((120, 570), "Play Store Ratings & Reviews", fill="#5f6368", font=font_sub)

    # Divider
    draw.line([(120, 640), (960, 640)], fill="#e8eaed", width=2)

    # User & Stars
    draw.text((120, 680), f"👤  {user_name}", fill="#202124", font=font_header)
    stars = "★" * int(rating_score)
    draw.text((120, 750), stars, fill="#01875f", font=font_header)

    # Wrapped Text Content
    words = content.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + " " + word) <= 35:
            current_line += " " + word
        else:
            lines.append(current_line.strip())
            current_line = word
    if current_line:
        lines.append(current_line.strip())

    y_offset = 840
    for line in lines[:8]:
        draw.text((120, y_offset), line, fill="#3c4043", font=font_content)
        y_offset += 55

    img.save(output_path)

# =====================================
# VIDEO GENERATION ROUTE (EXACT END)
# =====================================
@app.route("/generate-video", methods=["POST"])
def generate_video():
    global CURRENT_FETCHED_REVIEWS, CURRENT_APP_INFO
    
    if not CURRENT_FETCHED_REVIEWS:
        return "No reviews available to generate video", 400

    clips = []
    temp_images = []
    app_title = CURRENT_APP_INFO.get("title", "App Reviews")

    # Limit to maximum 10 latest reviews
    sample_reviews = CURRENT_FETCHED_REVIEWS[:10]

    for idx, r in enumerate(sample_reviews):
        img_filename = f"temp_frame_{idx}.png"
        create_review_frame(
            user_name=r.get("userName", "Google User"),
            rating_score=r.get("score", 5),
            content=r.get("content", ""),
            app_title=app_title,
            output_path=img_filename
        )
        temp_images.append(img_filename)

        # 3 Seconds per slide
        clip = ImageClip(img_filename).set_duration(3.0)
        clips.append(clip)

    # Sequence Clips without extra blank frames
    final_video = concatenate_videoclips(clips, method="compose")
    output_filename = "PlayStore_Reviews_Video.mp4"
    
    # Save exact duration video
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio=False)

    # Clean up Temp Files
    for img_file in temp_images:
        if os.path.exists(img_file):
            os.remove(img_file)

    return send_file(output_filename, as_attachment=True, mimetype="video/mp4")

# =====================================
# MAIN ROUTE
# =====================================
@app.route("/", methods=["GET", "POST"])
def home():
    global CURRENT_FETCHED_REVIEWS, CURRENT_APP_INFO
    data = []  
    raw_input = ""  
    package = ""
    app_info = {}  

    if request.method == "POST":  
        raw_input = request.form.get("package", "").strip()  
        date = request.form.get("date", "").strip()  
        rating = request.form.get("rating", "").strip()  
        keyword = request.form.get("keyword", "").strip()  

        package = extract_package_id(raw_input)

        if package:  
            app_info = get_app_info(package)  

        if package and date:  
            data = fetch_reviews(package=package, search_date=date, rating=rating, keyword=keyword)  

            CURRENT_FETCHED_REVIEWS = data
            CURRENT_APP_INFO = app_info

            if len(data) > 0:  
                thread = threading.Thread(
                    target=process_and_upload_async, 
                    args=(package, date, data, app_info.get("title", package))
                )
                thread.start()

    return render_template(  
        "index.html",  
        reviews=data,  
        package=raw_input,  
        app_info=app_info  
    )  

# =====================================
# HEALTH CHECK
# =====================================
@app.route("/health")
def health():
    return {  
        "status": "ok",  
        "service": "Google Play Review Fetcher"  
    }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
    
