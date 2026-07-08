from flask import Flask, render_template, request
from google_play_scraper import reviews, Sort, app as play_app

import requests
import json
import re
import time
from datetime import datetime

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
# GOOGLE SHEET
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

        print(response.text)

    except Exception as e:

        print("Batch Upload Error :", e)


def save_to_google_sheet(package, reviews_data):

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

            "username": str(
                r.get("userName", "")
            ),

            "review": str(
                r.get("content", "")
            ),

            "rating": int(
                r.get("score", 0)
            ),

            "date": date,

            "time": review_time,

            "package": package

        })

    if len(rows) == 0:
        return

    print("Total Reviews :", len(rows))

    for i in range(0, len(rows), BATCH_SIZE):

        batch = rows[i:i + BATCH_SIZE]

        print(
            f"Uploading Batch {i+BATCH_SIZE}/{len(rows)}"
        )

        save_batch(
            package,
            rows[0]["date"],
            batch
        )

        time.sleep(0.5)

    print("Google Sheet Upload Completed")
    # =====================================
# MATCH SYSTEM
# =====================================

def is_symbol_only(text):

    if not text:
        return False

    return all(not ch.isalnum() for ch in text)


def match_keyword(comment, keyword):

    comment = str(comment).strip()
    keyword = str(keyword).strip()

    if comment == "" or keyword == "":
        return False

    # Symbol match (Example: ".", "..", "!")
    if is_symbol_only(keyword):

        m = re.search(r'([^\w\s]+)$', comment)

        if not m:
            return False

        return m.group(1) == keyword

    # Normal word match
    pattern = r'(?<!\w)' + re.escape(keyword.lower()) + r'(?!\w)'

    return re.search(
        pattern,
        comment.lower()
    ) is not None


# =====================================
# MULTIPLE KEYWORDS
# =====================================

def keyword_match(comment, keyword_text):

    if not keyword_text:
        return True

    keywords = [

        k.strip()

        for k in keyword_text.splitlines()

        if k.strip()

    ]

    if len(keywords) == 0:
        return True

    for word in keywords:

        if match_keyword(comment, word):
            return True

    return False


# =====================================
# FILTER REVIEW
# =====================================

def review_pass(review, rating=None, keyword=None):

    # Rating Filter
    if rating:

        try:

            if review.get("score") != int(rating):
                return False

        except:
            return False

    # Keyword Filter
    if keyword:

        if not keyword_match(
            review.get("content", ""),
            keyword
        ):
            return False

    return True


# =====================================
# APP INFO
# =====================================

def get_app_info(package):

    try:

        info = play_app(

            package,

            country="in",

            lang="en"

        )

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


# =====================================
# FORMAT REVIEW DATE
# =====================================

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

            if not review_pass(
                review,
                rating,
                keyword
            ):
                continue

            data.append(review)

        print(
            f"Scanned : {total_scanned} | Matched : {len(data)}"
        )

        if stop:
            break

        if token is None:
            break

        if total_scanned >= MAX_FETCH:
            print("Maximum Fetch Limit Reached")
            break

        time.sleep(0.2)

    print("--------------------------------")
    print("Total Reviews Scanned :", total_scanned)
    print("Matched Reviews :", len(data))
    print("--------------------------------")

    return data
    # =====================================
# MAIN ROUTE
# =====================================

@app.route("/", methods=["GET", "POST"])
def home():

    data = []
    package = ""
    app_info = {}

    if request.method == "POST":

        package = request.form.get(
            "package",
            ""
        ).strip()

        date = request.form.get(
            "date",
            ""
        ).strip()

        rating = request.form.get(
            "rating",
            ""
        ).strip()

        keyword = request.form.get(
            "keyword",
            ""
        ).strip()

        # Get App Information
        if package:

            app_info = get_app_info(package)

        # Validation
        if package and date:

            print("=" * 50)
            print("Package :", package)
            print("Date :", date)
            print("Rating :", rating)
            print("=" * 50)

            # Fetch Reviews
            data = fetch_reviews(

                package=package,

                search_date=date,

                rating=rating,

                keyword=keyword

            )

            print(
                f"Matched Reviews : {len(data)}"
            )

            # Save Google Sheet
            if len(data) > 0:

                try:

                    save_to_google_sheet(

                        package,

                        data

                    )

                except Exception as e:

                    print(
                        "Google Sheet Error :",
                        e
                    )

                # Telegram Notification
                try:

                    send_bot_message(

                        app_info.get(
                            "title",
                            package
                        ),

                        date,

                        len(data)

                    )

                except Exception as e:

                    print(
                        "Telegram Error :",
                        e
                    )

    return render_template(

        "index.html",

        reviews=data,

        package=package,

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


# =====================================
# RUN SERVER
# =====================================

if __name__ == "__main__":

    print("=" * 50)
    print("Google Play Review Fetcher Started")
    print("=" * 50)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
