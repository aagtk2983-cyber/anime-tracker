from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import os
import csv
import time
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
ANIME_LIST_PATH = "anime_list.csv"
CSV_PATH = os.path.join(DATA_DIR, "history.csv")

FIELDNAMES = [
    "anime_id", "season", "date", "time",
    "mal_score", "mal_members",
    "danime_favorites", "danime_rank",
]

DANIME_RANKING_URL = "https://animestore.docomo.ne.jp/animestore/CR/CR00003003"


def load_anime_list():
    with open(ANIME_LIST_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if (r.get("anime_id") or "").strip()]


def fetch_mal(page, anime_id, mal_id, mal_slug):
    """MyAnimeList: スコアとメンバー数"""
    url = f"https://myanimelist.net/anime/{mal_id}/{mal_slug}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body")
    html = page.content()

    soup = BeautifulSoup(html, "html.parser")
    score_tag = soup.find("span", attrs={"itemprop": "ratingValue"})
    score = score_tag.get_text(strip=True) if score_tag else None

    members = None
    for tag in soup.find_all("span", class_="dark_text"):
        if tag.get_text(strip=True).startswith("Members"):
            parent_text = tag.parent.get_text(" ", strip=True)
            m = re.search(r"Members[:\s]*([\d,]+)", parent_text)
            if m:
                members = m.group(1)
            break

    return score, members


def fetch_danime_favorites(page, anime_id, danime_work_id):
    """dアニメストア: 気になる登録数(お気に入り相当)"""
    url = f"https://animestore.docomo.ne.jp/animestore/ci_pc?workId={danime_work_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body")
    html = page.content()

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    m = re.search(r"気になる登録数[：:]\s*([\d,]+)", text)
    return m.group(1) if m else None


def fetch_danime_ranking_text(page):
    """dアニメストア デイリーランキングページを一度だけ取得してテキスト化する
    (タイトルが増えても、ランキングページ自体は1回読み込めば済むため)"""
    try:
        page.goto(DANIME_RANKING_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print("ランキングページの取得に失敗:", e)
        return None

    html = page.content()
    with open(os.path.join(DATA_DIR, "debug_danime_ranking.html"), "w", encoding="utf-8") as f:
        f.write(html)
    try:
        page.screenshot(path=os.path.join(DATA_DIR, "debug_danime_ranking.png"), full_page=True)
    except Exception:
        pass

    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def rank_from_text(ranking_text, danime_title):
    if not ranking_text:
        return None
    idx = ranking_text.find(danime_title)
    if idx == -1:
        return None
    before = ranking_text[max(0, idx - 30):idx]
    matches = list(re.finditer(r"(\d{1,3})\s*位", before))
    return matches[-1].group(1) if matches else None


anime_list = load_anime_list()

rows = []
if os.path.exists(CSV_PATH):
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

now = datetime.now(JST)
today = now.strftime("%Y-%m-%d")
time_str = now.strftime("%H:%M:%S")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # ランキングページはタイトル数に関わらず1回だけ取得する
    danime_ranking_text = fetch_danime_ranking_text(page)

    for anime in anime_list:
        aid = anime["anime_id"]
        mal_id = (anime.get("mal_id") or "").strip()
        danime_work_id = (anime.get("danime_work_id") or "").strip()
        danime_title = (anime.get("danime_title") or "").strip()

        if not mal_id:
            print(f"skip (MAL ID未登録): {aid}")
            continue

        print(f"===== {aid} ({anime['name']}) =====")
        mal_score = mal_members = None
        danime_favorites = danime_rank = None

        try:
            mal_score, mal_members = fetch_mal(page, aid, mal_id, anime.get("mal_slug", ""))
        except Exception as e:
            print("MAL取得に失敗しました:", e)

        if danime_work_id:
            try:
                danime_favorites = fetch_danime_favorites(page, aid, danime_work_id)
            except Exception as e:
                print("dアニメ(お気に入り)取得に失敗しました:", e)

        if danime_title:
            danime_rank = rank_from_text(danime_ranking_text, danime_title)

        print("MAL Score:", mal_score, "/ Members:", mal_members)
        print("dアニメ 気になる登録数:", danime_favorites, "/ ランキング:", danime_rank)

        rows = [r for r in rows if not (r.get("anime_id") == aid and r.get("date") == today)]
        rows.append({
            "anime_id": aid,
            "season": anime.get("season", ""),
            "date": today,
            "time": time_str,
            "mal_score": mal_score or "",
            "mal_members": mal_members or "",
            "danime_favorites": danime_favorites or "",
            "danime_rank": danime_rank or "",
        })

        time.sleep(2)  # サイトへの配慮として、タイトルごとに少し間隔を空ける

    browser.close()

rows.sort(key=lambda r: (r.get("anime_id", ""), r.get("date", "")))

with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in FIELDNAMES})

n_active = len([a for a in anime_list if a.get("mal_id", "").strip()])
print(f"\nRecorded {n_active}/{len(anime_list)} title(s) to {CSV_PATH}: {today} {time_str}")
