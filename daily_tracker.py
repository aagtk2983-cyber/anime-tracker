import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime

URL = "https://myanimelist.net/anime/49233/Youjo_Senki_II"

CSV_FILE = Path("youjo_senki_ii.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/137.0 Safari/537.36"
    )
}


def fetch():

    response = requests.get(URL, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ")

    score = re.search(r"Score\s*([0-9.]+)", text)
    members = re.search(r"Members\s*([\d,]+)", text)

    if score is None:
        raise Exception("Scoreが取得できません。")

    if members is None:
        raise Exception("Membersが取得できません。")

    return (
        float(score.group(1)),
        int(members.group(1).replace(",", ""))
    )


def save(score, members):

    today = datetime.now().strftime("%Y-%m-%d")

    row = pd.DataFrame([{
        "date": today,
        "score": score,
        "members": members
    }])

    if CSV_FILE.exists():

        df = pd.read_csv(CSV_FILE)

        if today in df["date"].values:
            print("今日は既に取得済みです。")
            return

        df = pd.concat([df, row], ignore_index=True)

    else:

        df = row

    df.to_csv(CSV_FILE, index=False)

    print("保存完了")
    print(df.tail())


if __name__ == "__main__":

    score, members = fetch()

    save(score, members)
