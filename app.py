from flask import Flask, request, render_template
from google_play_scraper import reviews, Sort
import requests
import re
import json

app = Flask(__name__)


SHEET_URL = "https://script.google.com/macros/s/AKfycbxHPvSykMBiVmHAIH6cmkbZ91dC3zxQy8MPN55UEMSZyD4jO7RwKfnfwhdHC6piVIbAxQ/exec"


# =========================
# TELEGRAM BOT
# =========================

BOT_TOKEN = "8998711422:AAHFqUS18433G7FgaEU6cp4CbqEW0fwcM3Y"
CHAT_ID = "6371284862"


def send_bot_message(app_name, date, total):

    message = f"""
✅ App Synced: {app_name}

📅 Date: {date}
📊 Total Reviews: {total}

📄 Google Sheet:
{SHEET_URL}
"""


    try:

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=10
        )


    except Exception as e:

        print("Bot error:", e)




# =========================
# GOOGLE SHEET SAVE
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

    sheet_link = response.text.strip()

    print("Google Sheet Link:", sheet_link)


except Exception as e:

    print("Sheet error:", str(e))



# =========================
# MATCH SYSTEM
# =========================

def match_keyword(comment, word):

    comment = str(comment).strip()
    word = str(word).strip()


    if not word:
        return False


    def is_symbol_only(text):

        return all(not c.isalnum() for c in text)



    if is_symbol_only(word):

        match = re.search(
            r'([^\w\s]+)$',
            comment.strip()
        )


        if not match:
            return False


        return match.group(1) == word



    pattern = r'(?<!\w)' + re.escape(word.lower()) + r'(?!\w)'


    return re.search(
        pattern,
        comment.lower()
    ) is not None





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





        for r in found_reviews:


            comment = r.get("content","")



            if rating:

                if r.get("score") != int(rating):

                    continue




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





        if data:


            save_to_google_sheet(

                package,

                data

            )


            send_bot_message(

                package,

                date,

                len(data)

            )




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
