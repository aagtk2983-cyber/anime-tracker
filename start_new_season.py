# -*- coding: utf-8 -*-
"""
新しいシーズンが始まったタイミングで実行するスクリプト。

MAL(MyAnimeList)公式のシーズン新作一覧を、非公式APIの Jikan
(https://jikan.moe/, 無料・APIキー不要)経由で取得し、
anime_list.csv に「season = 新シーズン」の行として追加する。

・すでに mal_id が anime_list.csv に存在する場合はスキップ(重複追加防止)。
・danime_work_id / danime_title は空欄のまま追加する。
  → 前回同様、dアニメストア側のID一覧(PDFや作品ページ)と突き合わせて
    別途 fill_danime_ids.py 方式で埋める必要がある。
・追跡終了(2シーズン経過)の判定は daily_tracker.py 側の season_utils が
  自動で行うので、このスクリプトは「追加」だけを担当する。

実行例:
  python start_new_season.py                # 現在シーズンを自動判定して取り込む
  python start_new_season.py --season 2026-fall   # シーズンを明示指定
  python start_new_season.py --dry-run       # 追加内容を確認するだけ(csvは変更しない)
"""
import argparse
import csv
import re
import time
import urllib.request
import urllib.error
import json

from season_utils import current_mal_season

ANIME_LIST_PATH = "anime_list.csv"
JIKAN_SEASON_URL = "https://api.jikan.moe/v4/seasons/{year}/{season}"
FIELDNAMES = [
    "anime_id", "name", "season", "genre",
    "mal_id", "mal_slug", "danime_work_id", "danime_title",
]

# Jikanは無料の代わりにレート制限が厳しめ(概ね3リクエスト/秒)なので、
# ページ送りの合間に少し待つ。
REQUEST_INTERVAL_SEC = 1.0


def slugify(text, max_len=40):
    """MALのローマ字タイトルから、既存の anime_id 命名規則に寄せたスラッグを作る。"""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_len].rstrip("_")


def mal_slug_from_url(url):
    """MALのURL(.../anime/12345/Some_Title)から末尾のスラッグ部分を取り出す。"""
    if not url:
        return ""
    return url.rstrip("/").split("/")[-1]


def fetch_season_anime(year, season_name):
    """Jikan APIからそのシーズンの新作一覧を取得する(ページネーション対応)。"""
    results = []
    page = 1
    while True:
        url = JIKAN_SEASON_URL.format(year=year, season=season_name) + f"?page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "anime-tracker-bot"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            print(f"Jikan APIエラー(page={page}):", e)
            break

        results.extend(payload.get("data", []))

        has_next = payload.get("pagination", {}).get("has_next_page", False)
        if not has_next:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL_SEC)

    return results


def load_anime_list():
    with open(ANIME_LIST_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_anime_list(rows):
    with open(ANIME_LIST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def build_new_row(entry, season_str, existing_ids):
    mal_id = str(entry.get("mal_id", ""))
    title = entry.get("title") or ""
    genres = entry.get("genres", []) + entry.get("explicit_genres", [])
    genre_str = ",".join(g.get("name", "") for g in genres if g.get("name"))
    mal_slug = mal_slug_from_url(entry.get("url", ""))

    base_id = slugify(title)
    anime_id = base_id
    suffix = 2
    while anime_id in existing_ids:
        anime_id = f"{base_id}_{suffix}"[:40]
        suffix += 1

    return {
        "anime_id": anime_id,
        "name": title,
        "season": season_str,
        "genre": genre_str,
        "mal_id": mal_id,
        "mal_slug": mal_slug,
        "danime_work_id": "",
        "danime_title": "",
    }


def main():
    parser = argparse.ArgumentParser(description="新シーズンの新作をanime_list.csvに追加する")
    parser.add_argument("--season", help="例: 2026-fall (省略時は現在シーズンを自動判定)")
    parser.add_argument("--dry-run", action="store_true", help="csvを書き換えず、追加予定を表示するだけ")
    args = parser.parse_args()

    season_str = args.season or current_mal_season()
    year_str, season_name = season_str.split("-", 1)

    print(f"対象シーズン: {season_str}")
    entries = fetch_season_anime(int(year_str), season_name)
    print(f"Jikanから取得した件数: {len(entries)}")

    rows = load_anime_list()
    existing_mal_ids = {(r.get("mal_id") or "").strip() for r in rows if (r.get("mal_id") or "").strip()}
    existing_ids = {r["anime_id"] for r in rows}

    new_rows = []
    for entry in entries:
        mal_id = str(entry.get("mal_id", ""))
        if not mal_id or mal_id in existing_mal_ids:
            continue  # 既存タイトル(継続追跡中など)は追加しない
        new_row = build_new_row(entry, season_str, existing_ids)
        existing_ids.add(new_row["anime_id"])
        existing_mal_ids.add(mal_id)
        new_rows.append(new_row)

    print(f"新規追加予定: {len(new_rows)}件")
    for r in new_rows:
        print(f"  + {r['anime_id']} | {r['name']} | mal_id={r['mal_id']}")

    if args.dry_run:
        print("(--dry-run のためcsvは変更していません)")
        return

    if new_rows:
        save_anime_list(rows + new_rows)
        print(f"anime_list.csv に {len(new_rows)}件追加しました。")
        print("danime_work_id / danime_title は空欄です。dアニメ側のID一覧と突き合わせて埋めてください。")
    else:
        print("追加対象はありませんでした。")


if __name__ == "__main__":
    main()
