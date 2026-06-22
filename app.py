from flask import Flask, request, render_template
from google_play_scraper import reviews, Sort
import requests
import re


app = Flask(__name__)


SHEET_URL = "https://script.google.com/macros/s/AKfycbxEDtFnk5IUVy1Kx8so8f3XKEHQosqSLyYAGXDmge9awgLWOifbS_DqE_4cmYSsx7I4/exec"


# =========================
# TEXT NORMALIZER (NEW FIX)
# =========================
def normalize(text):
    text = str(text).lower().strip()

    # remove commas and dashes only (as you wanted)
    text = re.sub(r"[,\-]", "", text)

    # fix extra spaces
    text = re.sub(r"\s+", " ", text)

    return text


# =========================
# SAVE TO SHEET (SAME)
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
        print("No data found")
        return

    try:
        response = requests.post(
            SHEET_URL,
            json={"reviews": rows},
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        print("Google Sheet response:", response.text)

    except Exception as e:
        print("Sheet error:", e)


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
        # FILTERING FIX (HINT LOGIC)
        # =========================
        for r in found_reviews:

            comment = r.get("content", "")

            # rating filter
            if rating:
                if r.get("score") != int(rating):
                    continue

            # keyword / hint filter (FIXED)
            if keyword:

                words = keyword.split("\n")
                match = False

                comment_clean = normalize(comment)

                for word in words:

                    word = normalize(word.strip())

                    if not word:
                        continue

                    # strict matching (your requirement style)
                    if word in comment_clean:
                        match = True
                        break

                if not match:
                    continue

            data.append(r)

        # Google Sheet save
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
