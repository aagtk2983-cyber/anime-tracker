"""lists/anime_list_<年>-<season>.csv を全部まとめて読み込む。
新シーズンはファイルを1つ追加するだけで追跡対象になる(例: lists/anime_list_2027-winter.csv)。"""
import csv
import glob
import os
import re

LISTS_DIR = "lists"
DATA_DIR = "data"
_PATTERN = re.compile(r"^anime_list_(\d{4})-(winter|spring|summer|fall)\.csv$")
_DATA_FIELDNAMES = [
    "anime_id",
    "season",
    "date",
    "time",
    "mal_score",
    "mal_members",
    "danime_favorites",
    "danime_rank",
]
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


def _write_csv(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _season_data_rows(season):
    all_anime_dir = os.path.join(DATA_DIR, season, "all_anime")
    if not os.path.isdir(all_anime_dir):
        return []

    rows = []
    for path in sorted(glob.glob(os.path.join(all_anime_dir, "*.csv"))):
        if os.path.basename(path) == "all_anime.csv":
            continue
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                anime_id = (row.get("anime_id") or os.path.splitext(os.path.basename(path))[0]).strip()
                if not anime_id or anime_id.lower() == "demo":
                    continue
                if not (row.get("date") or "").strip():
                    continue
                normalized = {field: row.get(field, "") for field in _DATA_FIELDNAMES}
                normalized["anime_id"] = anime_id
                normalized["season"] = (row.get("season") or season).strip()
                rows.append(normalized)
    rows.sort(key=lambda r: (
        r.get("season") or "",
        r.get("date") or "",
        r.get("time") or "",
        r.get("anime_id") or "",
    ))
    return rows


def export_data_csvs():
    season_dirs = sorted(
        os.path.join(DATA_DIR, d)
        for d in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, d)) and re.fullmatch(r"\d{4}-(winter|spring|summer|fall)", d)
    )

    season_rows = {}
    for season_dir in season_dirs:
        season_name = os.path.basename(season_dir)
        rows = _season_data_rows(season_name)
        season_rows[season_name] = rows
        _write_csv(os.path.join(season_dir, "all_anime", "all_anime.csv"), _DATA_FIELDNAMES, rows)

    all_rows = []
    for season_name in sorted(season_rows):
        all_rows.extend(season_rows[season_name])
    _write_csv(os.path.join(DATA_DIR, "all_anime.csv"), _DATA_FIELDNAMES, all_rows)


def season_path(season):
    return os.path.join(LISTS_DIR, f"anime_list_{season}.csv")
