import os
import csv
import shutil
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import anime_lists

DATA_DIR = "data"
TRENDS_DIR = "trends"
ANIME_LIST_PATH = "anime_list.csv"

for name in ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic"]:
    if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = name
        break

anime_list = anime_lists.load_all()


def title_csv_path(season, anime_id):
    return os.path.join(DATA_DIR, season, "all_anime", f"{anime_id}.csv")


def title_png_path(season, anime_id):
    return os.path.join(TRENDS_DIR, season, "all_anime", f"{anime_id}.png")


def genre_png_path(season, genre, anime_id):
    return os.path.join(TRENDS_DIR, season, "genres", genre, f"{anime_id}.png")


def genre_csv_path(season, genre):
    if season is None:
        return os.path.join(DATA_DIR, "genres", genre, "all_anime.csv")
    return os.path.join(DATA_DIR, season, "genres", genre, "all_anime.csv")


def genre_trend_png_path(season, genre):
    if season is None:
        return os.path.join(TRENDS_DIR, "genres", genre, "all_anime.png")
    return os.path.join(TRENDS_DIR, season, "genres", genre, "all_anime.png")


def write_genre_csv(season, genre, animes):
    rows = []
    for anime in animes:
        path = os.path.join(DATA_DIR, anime["season"], "genres", genre,
                            f"{anime['anime_id']}.csv")
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))

    if not rows:
        return None

    rows.sort(key=lambda row: (row["date"], row["anime_id"], row["time"]))
    out_path = genre_csv_path(season, genre)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def make_chart(anime):
    aid = anime["anime_id"]
    season = anime.get("season", "unknown")
    csv_path = title_csv_path(season, aid)
    if not os.path.exists(csv_path):
        print(f"skip: {csv_path} がありません")
        return None

    df = pd.read_csv(csv_path)
    if df.empty:
        return None

    df["date"] = pd.to_datetime(df["date"])
    df["mal_score"] = pd.to_numeric(df["mal_score"], errors="coerce")
    df["mal_members"] = pd.to_numeric(
        df["mal_members"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    df = df.sort_values("date")

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    axes[0].plot(df["date"], df["mal_score"], marker="o", color="#4C72B0", label="Score")
    if df["mal_score"].notna().any():
        avg_score = df["mal_score"].mean()
        axes[0].axhline(avg_score, color="gray", linestyle="--", linewidth=1,
                         label=f"平均 {avg_score:.2f}")
    axes[0].set_title(f"{anime['name']}({season} / {anime.get('genre', '')}) - MALスコア推移")
    axes[0].set_ylabel("Score")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(df["date"], df["mal_members"], marker="o", color="#DD8452", label="Members")
    if df["mal_members"].notna().any():
        avg_members = df["mal_members"].mean()
        axes[1].axhline(avg_members, color="gray", linestyle="--", linewidth=1,
                         label=f"平均 {avg_members:,.0f}")
    axes[1].set_title(f"{anime['name']} - MALメンバー数推移")
    axes[1].set_ylabel("Members")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.autofmt_xdate()
    plt.tight_layout()

    out_path = title_png_path(season, aid)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def make_genre_chart(season, genre, animes):
    csv_path = genre_csv_path(season, genre)
    if not os.path.exists(csv_path):
        return None

    df = pd.read_csv(csv_path)
    if df.empty:
        return None

    df["date"] = pd.to_datetime(df["date"])
    df["mal_score"] = pd.to_numeric(df["mal_score"], errors="coerce")
    df["mal_members"] = pd.to_numeric(
        df["mal_members"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    anime_names = {anime["anime_id"]: anime["name"] for anime in animes}
    anime_rows = list(df.groupby("anime_id"))
    fig_height = min(24, max(8, 6 + 0.25 * len(anime_rows)))
    fig, axes = plt.subplots(2, 1, figsize=(12, fig_height), sharex=True)

    for anime_id, rows in anime_rows:
        rows = rows.sort_values("date")
        name = anime_names.get(anime_id, anime_id)
        axes[0].plot(rows["date"], rows["mal_score"], marker="o", markersize=2,
                     linewidth=1, label=name)
        axes[1].plot(rows["date"], rows["mal_members"], marker="o", markersize=2,
                     linewidth=1, label=name)

    scope = season or "全シーズン"
    axes[0].set_title(f"{scope} / {genre} - MALスコア推移")
    axes[0].set_ylabel("Score")
    axes[1].set_title(f"{scope} / {genre} - MALメンバー数推移")
    axes[1].set_ylabel("Members")
    for axis in axes:
        axis.grid(alpha=0.3)
        axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize="small")

    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.subplots_adjust(right=0.76, hspace=0.35)
    fig.autofmt_xdate()

    out_path = genre_trend_png_path(season, genre)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


genres_by_season = {}
animes_by_genre = {}
for anime in anime_list:
    png_path = make_chart(anime)
    if not png_path:
        print(f"skip: {anime['anime_id']} の個別トレンドグラフを作成できませんでした")
    else:
        print(f"Saved chart to {png_path}")

    season = anime.get("season", "unknown")
    genres = [g.strip() for g in (anime.get("genre") or "").split(",") if g.strip()]
    for genre in genres:
        if png_path:
            dest = genre_png_path(season, genre, anime["anime_id"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(png_path, dest)
        genres_by_season.setdefault((season, genre), []).append(anime)
        animes_by_genre.setdefault(genre, []).append(anime)

for (season, genre), animes in sorted(genres_by_season.items()):
    csv_path = write_genre_csv(season, genre, animes)
    if not csv_path:
        print(f"skip: {season} / {genre} の集約データがありません")
        continue
    print(f"Saved genre data to {csv_path}")

    png_path = make_genre_chart(season, genre, animes)
    if png_path:
        print(f"Saved genre chart to {png_path}")

for genre, animes in sorted(animes_by_genre.items()):
    csv_path = write_genre_csv(None, genre, animes)
    if not csv_path:
        print(f"skip: 全シーズン / {genre} の集約データがありません")
        continue
    print(f"Saved all-season genre data to {csv_path}")

    for anime in animes:
        season = anime.get("season", "unknown")
        source = title_png_path(season, anime["anime_id"])
        if os.path.exists(source):
            dest = os.path.join(TRENDS_DIR, "genres", genre, f"{anime['anime_id']}.png")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(source, dest)

    png_path = make_genre_chart(None, genre, animes)
    if png_path:
        print(f"Saved all-season genre chart to {png_path}")
