from flask import Flask, request, render_template
from google_play_scraper import reviews, Sort
import requests
import re

app = Flask(__name__)

SHEET_URL = "https://script.google.com/macros/s/AKfycbxEDtFnk5IUVy1Kx8so8f3XKEHQosqSLyYAGXDmge9awgLWOifbS_DqE_4cmYSsx7I4/exec"


# =========================
# SAVE TO GOOGLE SHEET
# =========================
def save_to_google_sheet(package, reviews_data):

    rows = []

    for r in reviews_data:
        rows.append({
            "username": str(r.get("userName", "")),
            "review": str(r.get("content", "")),
            "rating": int(r.get("score", 0)),
            "date": r["at"].strftime("%Y-%m-%d"),
            "time": r["at"].strftime("%H:%M:%S"),
            "package": package
        })

    if not rows:
        return

    try:
        requests.post(
            SHEET_URL,
            json={"reviews": rows},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
    except Exception as e:
        print("Sheet error:", e)


# =========================
# STRICT MATCH ENGINE (FINAL)
# =========================
def match_keyword(comment, word):

    comment = str(comment)
    word = str(word).strip()

    if not word:
        return False

    # =========================
    # SYMBOL / EMOJI MODE
    # =========================
    def is_symbol_only(text):
        return all(not c.isalnum() and not c.isspace() for c in text)

    if is_symbol_only(word):

        # extract all symbol/emojis groups from comment
        blocks = re.findall(r'[^\w\s]+', comment)

        # EXACT MATCH ONLY
        return word in blocks

    # =========================
    # NORMAL TEXT MODE
    # =========================
    comment = comment.lower()
    word = word.lower()

    escaped = re.escape(word)

    pattern = r'(?<!\w)' + escaped + r'(?!\w)'

    return re.search(pattern, comment) is not None


# =========================
# MAIN ROUTE
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
