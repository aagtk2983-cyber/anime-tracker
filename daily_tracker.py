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
    "anime_id", "date", "time",
    "mal_score", "mal_members",
    "danime_favorites", "danime_rank",
    "anikore_score", "anikore_stars",
    "x_followers", "abema_views",
]


def load_anime_list():
    with open(ANIME_LIST_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fetch_mal(page, anime_id, mal_id, mal_slug):
    """MyAnimeList: スコアとメンバー数"""
    url = f"https://myanimelist.net/anime/{mal_id}/{mal_slug}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body")
    html = page.content()
    with open(os.path.join(DATA_DIR, f"debug_{anime_id}_mal.html"), "w", encoding="utf-8") as f:
        f.write(html)

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
    with open(os.path.join(DATA_DIR, f"debug_{anime_id}_danime.html"), "w", encoding="utf-8") as f:
        f.write(html)

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    m = re.search(r"気になる登録数[：:]\s*([\d,]+)", text)
    return m.group(1) if m else None


DANIME_RANKING_URL = "https://animestore.docomo.ne.jp/animestore/CR/CR00003003"


def fetch_danime_daily_rank(page, anime_id, danime_title):
    """dアニメストア: デイリーランキングでの順位(ベストエフォート・未検証)"""
    try:
        page.goto(DANIME_RANKING_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print("ランキングページの取得に失敗:", e)
        return None

    html = page.content()
    with open(os.path.join(DATA_DIR, f"debug_{anime_id}_danime_ranking.html"), "w", encoding="utf-8") as f:
        f.write(html)
    try:
        page.screenshot(path=os.path.join(DATA_DIR, f"debug_{anime_id}_danime_ranking.png"), full_page=True)
    except Exception:
        pass

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    idx = text.find(danime_title)
    if idx == -1:
        return None

    before = text[max(0, idx - 30):idx]
    matches = list(re.finditer(r"(\d{1,3})\s*位", before))
    return matches[-1].group(1) if matches else None


def fetch_anikore(page, anime_id, anikore_id):
    """あにこれ: 総合得点(ベストエフォート・ボット検知の影響で未検証)"""
    url = f"https://www.anikore.jp/anime/{anikore_id}/"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("body")
    except Exception as e:
        print("あにこれ取得に失敗:", e)
        return None

    html = page.content()
    with open(os.path.join(DATA_DIR, f"debug_{anime_id}_anikore.html"), "w", encoding="utf-8") as f:
        f.write(html)

    soup = BeautifulSoup(html, "html.parser")
    title_text = soup.title.get_text(strip=True) if soup.title else ""
    m = re.search(r"【([\d.]+)点】", title_text)
    return m.group(1) if m else None


def fetch_abema(page, anime_id, abema_title_id):
    """ABEMA: 最新話の視聴数(ベストエフォート・地域制限の影響で未検証)"""
    if not abema_title_id:
        return None
    url = f"https://abema.tv/video/title/{abema_title_id}"
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print("ABEMA取得に失敗:", e)
        return None

    html = page.content()
    with open(os.path.join(DATA_DIR, f"debug_{anime_id}_abema.html"), "w", encoding="utf-8") as f:
        f.write(html)
    try:
        page.screenshot(path=os.path.join(DATA_DIR, f"debug_{anime_id}_abema.png"), full_page=True)
    except Exception:
        pass

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    episodes = []
    for ep_match in re.finditer(r"第(\d+)話", text):
        ep_num = int(ep_match.group(1))
        window = text[ep_match.end():ep_match.end() + 100]
        view_match = re.search(r"([\d.]+)\s*万?\s*視聴", window)
        if view_match:
            episodes.append((ep_num, view_match.group(1), "万" in window[:view_match.end()]))

    if not episodes:
        return None
    episodes.sort(key=lambda x: x[0])
    latest_ep, views, is_man = episodes[-1]
    return f"{views}万" if is_man else views


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

    for anime in anime_list:
        aid = anime["anime_id"]
        print(f"===== {aid} ({anime['name']}) =====")

        mal_score = mal_members = None
        danime_favorites = danime_rank = None
        anikore_score = None
        abema_views = None

        try:
            mal_score, mal_members = fetch_mal(page, aid, anime["mal_id"], anime["mal_slug"])
        except Exception as e:
            print("MAL取得に失敗しました:", e)

        try:
            danime_favorites = fetch_danime_favorites(page, aid, anime["danime_work_id"])
        except Exception as e:
            print("dアニメ(お気に入り)取得に失敗しました:", e)

        try:
            danime_rank = fetch_danime_daily_rank(page, aid, anime["danime_title"])
        except Exception as e:
            print("dアニメ(ランキング)取得に失敗しました:", e)

        try:
            anikore_score = fetch_anikore(page, aid, anime["anikore_id"])
        except Exception as e:
            print("あにこれ取得に失敗しました:", e)

        try:
            abema_views = fetch_abema(page, aid, anime.get("abema_title_id"))
        except Exception as e:
            print("ABEMA取得に失敗しました:", e)

        print("MAL Score:", mal_score, "/ Members:", mal_members)
        print("dアニメ 気になる登録数:", danime_favorites, "/ ランキング:", danime_rank)
        print("あにこれ 総合得点:", anikore_score)
        print("ABEMA 最新話視聴数:", abema_views)

        existing_today = next((r for r in rows if r.get("anime_id") == aid and r.get("date") == today), None)
        manual_carry = {
            k: (existing_today or {}).get(k, "")
            for k in ("anikore_stars", "x_followers")
        }

        rows = [r for r in rows if not (r.get("anime_id") == aid and r.get("date") == today)]
        rows.append({
            "anime_id": aid,
            "date": today,
            "time": time_str,
            "mal_score": mal_score or "",
            "mal_members": mal_members or "",
            "danime_favorites": danime_favorites or "",
            "danime_rank": danime_rank or "",
            "anikore_score": anikore_score or "",
            "abema_views": abema_views or "",
            **manual_carry,
        })

        time.sleep(2)  # サイトへの配慮として、タイトルごとに少し間隔を空ける

    browser.close()

rows.sort(key=lambda r: (r.get("anime_id", ""), r.get("date", "")))

with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in FIELDNAMES})

print(f"\nRecorded {len(anime_list)} title(s) to {CSV_PATH}: {today} {time_str}")
