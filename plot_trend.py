import os
import csv
import shutil
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

DATA_DIR = "data"
TRENDS_DIR = "trends"
ANIME_LIST_PATH = "anime_list.csv"

for name in ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic"]:
    if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = name
        break

with open(ANIME_LIST_PATH, encoding="utf-8") as f:
    anime_list = [r for r in csv.DictReader(f) if (r.get("anime_id") or "").strip()]


def title_csv_path(season, anime_id):
    return os.path.join(DATA_DIR, season, "all_anime", f"{anime_id}.csv")


def title_png_path(season, anime_id):
    return os.path.join(TRENDS_DIR, season, "all_anime", f"{anime_id}.png")


def genre_png_path(season, genre, anime_id):
    return os.path.join(TRENDS_DIR, season, "genres", genre, f"{anime_id}.png")


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


for anime in anime_list:
    png_path = make_chart(anime)
    if not png_path:
        continue
    print(f"Saved chart to {png_path}")

    season = anime.get("season", "unknown")
    genres = [g.strip() for g in (anime.get("genre") or "").split(",") if g.strip()]
    for genre in genres:
        dest = genre_png_path(season, genre, anime["anime_id"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(png_path, dest)
