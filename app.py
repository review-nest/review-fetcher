from flask import Flask, request, render_template
from google_play_scraper import reviews, Sort
import requests
import re
import json

app = Flask(__name__)

SHEET_URL = "https://script.google.com/macros/s/AKfycbzOIABzoeCniCqVWON0506pM6351PWrtqwIVZKFI8GIfSXhh-vO2e-dHnoJOdzyPYNW/exec"


# =========================
# GOOGLE SHEET SAVE (FIXED)
# =========================
def save_to_google_sheet(package, reviews_data):

    rows = []

    for r in reviews_data:

        at_val = r.get("at")

        if hasattr(at_val, "strftime"):
            date = at_val.strftime("%Y-%m-%d")
            time = at_val.strftime("%H:%M:%S")
        else:
            date = str(at_val)[:10]
            time = str(at_val)[-8:]

        rows.append({
            "username": str(r.get("userName", "")),
            "review": str(r.get("content", "")),
            "rating": int(r.get("score", 0)),
            "date": date,
            "time": time,
            "package": package
        })

    if not rows:
        return

    import json

try:

    response = requests.post(
        SHEET_URL,
        data=json.dumps({
            "package": package,
            "reviews": rows
        }),
        headers={
            "Content-Type": "application/json"
        },
        timeout=30
    )

    print("Google Sheet response:", response.text)

except Exception as e:
    print("Sheet error:", str(e))


# =========================
# STRICT MATCH ENGINE (FINAL RULE)
# =========================
def match_keyword(comment, word):

    comment = str(comment).strip()
    word = str(word).strip()

    if not word:
        return False

    # =========================
    # SYMBOL / EMOJI MODE
    # =========================
    def is_symbol_only(text):
        return all(not c.isalnum() for c in text)

    if is_symbol_only(word):

        # ONLY END OF COMMENT MATCH ALLOWED
        comment = comment.strip()

        # extract last symbol block
        match = re.search(r'([^\w\s]+)$', comment)

        if not match:
            return False

        last_block = match.group(1)

        return last_block == word

    # =========================
    # NORMAL TEXT MODE
    # =========================
    comment_low = comment.lower()
    word_low = word.lower()

    escaped = re.escape(word_low)
    pattern = r'(?<!\w)' + escaped + r'(?!\w)'

    return re.search(pattern, comment_low) is not None


# =========================
# FLASK ROUTE
# =========================
@app.route("/", methods=["GET", "POST"])
def home():

    data = []
    package = ""

    if request.method == "POST":

        package = request.form["package"]
        date = request.form["date"]
        rating = request.form.get("rating")
        keyword = request.form.get("keyword")

        token = None
        found_reviews = []

        # =========================
        # FETCH REVIEWS
        # =========================
        while True:

            result, token = reviews(
                package,
                country="in",
                lang="en",
                sort=Sort.NEWEST,
                count=500,
                continuation_token=token
            )

            if not result:
                break

            stop = False

            for r in result:

                review_date = r["at"].strftime("%Y-%m-%d")

                if review_date == date:
                    found_reviews.append(r)

                if review_date < date:
                    stop = True
                    break

            if stop or token is None:
                break

            if len(found_reviews) >= 5000:
                break

        # =========================
        # FILTER LOGIC
        # =========================
        for r in found_reviews:

            comment = r.get("content", "")

            # rating filter
            if rating:
                if r.get("score") != int(rating):
                    continue

            # keyword filter
            if keyword:

                words = keyword.split("\n")
                match = False

                for word in words:

                    word = word.strip()

                    if match_keyword(comment, word):
                        match = True
                        break

                if not match:
                    continue

            data.append(r)

        # =========================
        # SAVE TO SHEET
        # =========================
        if data:
            save_to_google_sheet(package, data)

    return render_template(
        "index.html",
        reviews=data,
        package=package
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )
