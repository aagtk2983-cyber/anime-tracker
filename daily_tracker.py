import json
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

URL = "https://myanimelist.net/anime/49233/Youjo_Senki_II"

CSV = Path("data/history.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def fetch():

    r = requests.get(URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # JSON-LDを探す
    for script in soup.find_all("script", type="application/ld+json"):

        try:
            data = json.loads(script.string)

            if data.get("@type") == "TVSeries":

                score = float(data["aggregateRating"]["ratingValue"])

                break

        except Exception:
            pass

    else:
        raise Exception("Score取得失敗")

    text = soup.get_text(" ")

    m = re.search(r"Members\s*([\d,]+)", text)

    if m is None:
        raise Exception("Members取得失敗")

    members = int(m.group(1).replace(",", ""))

    return score, members


def save(score, members):

    CSV.parent.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")

    row = pd.DataFrame([{
        "date": today,
        "score": score,
        "members": members
    }])

    if CSV.exists():

        df = pd.read_csv(CSV)

        if today in df["date"].values:
            print("今日のデータは保存済み")
            return

        df = pd.concat([df, row], ignore_index=True)

    else:

        df = row

    df.to_csv(CSV, index=False)

    print(df.tail())


if __name__ == "__main__":

    score, members = fetch()

    print(score, members)

    save(score, members)
