from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import sys
import os
import csv
from datetime import datetime

MAL_URL = "https://myanimelist.net/anime/49233/Youjo_Senki_II"
DANIME_URL = "https://animestore.docomo.ne.jp/animestore/ci_pc?workId=29084"
DANIME_RANKING_URL = "https://animestore.docomo.ne.jp/animestore/CR/CR00003003"
DANIME_TITLE = "幼女戦記Ⅱ"  # dアニメ側の表記(ローマ数字の"Ⅱ")に合わせる
ANIKORE_URL = "https://www.anikore.jp/anime/15538/"  # 幼女戦記II(ユーザー確認済み)
# エピソードURL(https://abema.tv/video/episode/25-46_s2_p3)から推測したタイトルページ。
# 実際に開けるか・想定の話数一覧が表示されるかは未確認。
ABEMA_URL = "https://abema.tv/video/title/25-46"

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


def fetch_mal(page):
    """MyAnimeList: スコアとメンバー数"""
    page.goto(MAL_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body")
    html = page.content()
    with open(os.path.join(DATA_DIR, "debug_mal.html"), "w", encoding="utf-8") as f:
        f.write(html)

    soup = BeautifulSoup(html, "html.parser")

    # スコア: itemprop="ratingValue" (CSSクラスより壊れにくく、脚注番号も巻き込まない)
    score_tag = soup.find("span", attrs={"itemprop": "ratingValue"})
    score = score_tag.get_text(strip=True) if score_tag else None

    # メンバー数: "dark_text" ラベルの親要素からコロン込みで抜き出す
    members = None
    for tag in soup.find_all("span", class_="dark_text"):
        if tag.get_text(strip=True).startswith("Members"):
            parent_text = tag.parent.get_text(" ", strip=True)
            m = re.search(r"Members[:\s]*([\d,]+)", parent_text)
            if m:
                members = m.group(1)
            break

    return score, members


def fetch_danime_favorites(page):
    """dアニメストア: 気になる登録数(お気に入り相当)"""
    page.goto(DANIME_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body")
    html = page.content()
    with open(os.path.join(DATA_DIR, "debug_danime.html"), "w", encoding="utf-8") as f:
        f.write(html)

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    m = re.search(r"気になる登録数[：:]\s*([\d,]+)", text)
    return m.group(1) if m else None


def fetch_danime_daily_rank(page):
    """
    dアニメストア: デイリーランキングでの順位(ベストエフォート)。

    このページはJavaScriptでランキング一覧を描画するSPA的な作りで、
    事前に構造を確認できていない。ここでは「レンダリング後のテキストから
    作品名の近くにある数字+"位"を探す」という緩い方法で拾っている。
    見つからない場合は None を返すので、data/debug_danime_ranking.html /
    .png を見て実際の構造を確認し、必要ならセレクタを調整すること。
    """
    try:
        page.goto(DANIME_RANKING_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)  # JS描画の猶予
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

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    idx = text.find(DANIME_TITLE)
    if idx == -1:
        return None

    # タイトル直前にある一番近い「N位」を採用する
    # (単純に前後30文字のウィンドウ内を検索すると、隣の作品の順位を
    #  誤って拾ってしまうことがあったため、直前側だけを見て最後の
    #  マッチ=タイトルに一番近いものを選ぶようにしている)
    before = text[max(0, idx - 30):idx]
    matches = list(re.finditer(r"(\d{1,3})\s*位", before))
    return matches[-1].group(1) if matches else None


def fetch_anikore(page):
    """
    あにこれ: 総合得点(ベストエフォート)。

    注意: anikore.jpはボット検知で単純なHTTP取得(web_fetch相当)を弾いてくる
    ことを確認済み。Playwright(実ブラウザ)なら通る可能性があるが未検証。
    総合得点はページタイトルに "【94.4点】幼女戦記..." のような形で
    含まれることが分かっているので、そこから抜き出す方式にしている。
    星の数(5段階評価)の表示箇所は未確認のため、今回は取得していない。
    """
    try:
        page.goto(ANIKORE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("body")
    except Exception as e:
        print("あにこれ取得に失敗:", e)
        return None

    html = page.content()
    with open(os.path.join(DATA_DIR, "debug_anikore.html"), "w", encoding="utf-8") as f:
        f.write(html)

    soup = BeautifulSoup(html, "html.parser")
    title_text = soup.title.get_text(strip=True) if soup.title else ""
    m = re.search(r"【([\d.]+)点】", title_text)
    return m.group(1) if m else None

def fetch_abema(page):
    """
    ABEMA: 最新話の視聴数(ベストエフォート・未検証)。

    重要な注意点:
    - ABEMAは日本国外からのアクセスを地域制限でブロックすることを直接確認済み。
      GitHub Actionsの実行サーバーは海外(主に米国)にあることが多く、同じ理由で
      ブロックされる可能性が高い。その場合は日本国内のマシン(自分のPC等)で
      別途ローカル実行する必要がある。
    - ABEMA_URL はエピソードURLから推測したタイトルページで、実際にこの構成に
      なっているかは未確認。
    - 抽出パターンは提供いただいたスクリーンショットの
      「第N話 タイトル ... N.N万視聴」という見た目のテキストから組んでいる。
      実際のHTML構造(クラス名など)は未確認。
    """
    try:
        page.goto(ABEMA_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print("ABEMA取得に失敗:", e)
        return None

    html = page.content()
    with open(os.path.join(DATA_DIR, "debug_abema.html"), "w", encoding="utf-8") as f:
        f.write(html)
    try:
        page.screenshot(path=os.path.join(DATA_DIR, "debug_abema.png"), full_page=True)
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


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    mal_score = mal_members = None
    danime_favorites = danime_rank = None
    anikore_score = None
    abema_views = None

    try:
        mal_score, mal_members = fetch_mal(page)
    except Exception as e:
        print("MAL取得に失敗しました:", e)

    try:
        danime_favorites = fetch_danime_favorites(page)
    except Exception as e:
        print("dアニメ(お気に入り)取得に失敗しました:", e)

    try:
        danime_rank = fetch_danime_daily_rank(page)
    except Exception as e:
        print("dアニメ(ランキング)取得に失敗しました:", e)

    try:
        anikore_score = fetch_anikore(page)
    except Exception as e:
        print("あにこれ取得に失敗しました:", e)

    try:
        abema_views = fetch_abema(page)
    except Exception as e:
        print("ABEMA取得に失敗しました:", e)

    browser.close()

print("==========")
print("MAL Score:", mal_score if mal_score else "not found")
print("MAL Members:", mal_members if mal_members else "not found")
print("dアニメ 気になる登録数:", danime_favorites if danime_favorites else "not found")
print("dアニメ デイリーランキング:", danime_rank if danime_rank else "not found (要: data/debug_danime_ranking.png を確認)")
print("あにこれ 総合得点:", anikore_score if anikore_score else "not found (要: data/debug_anikore.html を確認)")
print("ABEMA 最新話視聴数:", abema_views if abema_views else "not found (要: data/debug_abema.png を確認。地域制限の可能性大)")

# --- data/history.csv に記録 ---
# 同じ日付の行がすでにあれば上書き(手動で複数回実行しても重複しない)、
# なければ追加して日付順に並べ直す。
# anikore_score / anikore_stars / x_followers / abema_views は
# まだ自動取得先が確定していない列。手動でCSVに書き込んでもOK
# (その場合はこのスクリプトの再実行時、当日の行だけ空欄で上書きされる点に注意)。
CSV_PATH = os.path.join(DATA_DIR, "history.csv")
FIELDNAMES = [
    "date", "time",
    "mal_score", "mal_members",
    "danime_favorites", "danime_rank",
    "anikore_score", "anikore_stars",
    "x_followers", "abema_views",
]

now = datetime.now()
today = now.strftime("%Y-%m-%d")
time_str = now.strftime("%H:%M:%S")

rows = []
if os.path.exists(CSV_PATH):
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

# 同じ日にすでに手動入力された列(anikore/X/ABEMA)があれば、
# 自動取得できていない今回の実行で空欄上書きしてしまわないよう引き継ぐ
existing_today = next((r for r in rows if r.get("date") == today), None)
manual_carry = {
    k: (existing_today or {}).get(k, "")
    for k in ("anikore_stars", "x_followers")
}

rows = [r for r in rows if r.get("date") != today]
rows.append({
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
rows.sort(key=lambda r: r["date"])

with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in FIELDNAMES})

print(f"Recorded to {CSV_PATH}: {today} {time_str}")
