"""lists/anime_list_<年>-<season>.csv を全部まとめて読み込む。
新シーズンはファイルを1つ追加するだけで追跡対象になる(例: lists/anime_list_2027-winter.csv)。"""
import csv
import glob
import os
import re

LISTS_DIR = "lists"
_PATTERN = re.compile(r"^anime_list_(\d{4})-(winter|spring|summer|fall)\.csv$")


def list_files():
    return sorted(p for p in glob.glob(os.path.join(LISTS_DIR, "anime_list_*.csv"))
                  if _PATTERN.match(os.path.basename(p)))


def load_all(season=None):
    rows, seen = [], set()
    for path in list_files():
        file_season = _PATTERN.match(os.path.basename(path)).group(0)[len("anime_list_"):-len(".csv")]
        if season and file_season != season:
            continue
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not (r.get("anime_id") or "").strip() or r["anime_id"] in seen:
                    continue
                if not (r.get("season") or "").strip():
                    r["season"] = file_season
                seen.add(r["anime_id"])
                rows.append(r)
    return rows


def season_path(season):
    return os.path.join(LISTS_DIR, f"anime_list_{season}.csv")
