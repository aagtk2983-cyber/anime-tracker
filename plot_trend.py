import os
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

TREND_METRICS = (
    ("mal_score", "MALスコア", "Score"),
    ("mal_members", "MALメンバー数", "Members"),
    ("danime_favorites", "dアニメ 気になる登録数", "Favorites"),
    ("danime_rank", "dアニメ ランキング", "Rank"),
    ("danime_weekly_rank", "dアニメ ウィークリーランキング", "Weekly Rank"),
)

for name in ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic"]:
    if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = name
        break

anime_list = anime_lists.load_all()


def percent_change(values):
    baseline_values = values.dropna()
    if baseline_values.empty or baseline_values.iloc[0] == 0:
        return pd.Series(float("nan"), index=values.index)
    return (values / baseline_values.iloc[0] - 1) * 100


def add_change_rates(df, per_anime=False):
    """Add percentage change from each metric's first valid observation."""
    for column, _, _ in TREND_METRICS:
        if per_anime:
            df[f"{column}_change_pct"] = df.groupby(
                "anime_id", sort=False
            )[column].transform(percent_change)
        else:
            df[f"{column}_change_pct"] = percent_change(df[column])
    return df


def latest_change_label(series):
    changes = series.dropna()
    if changes.empty:
        return "開始比 ―"
    return f"開始比 {changes.iloc[-1]:+.1f}%"


def title_csv_path(season, anime_id):
    return os.path.join(DATA_DIR, season, "all_anime", f"{anime_id}.csv")


def title_png_path(season, anime_id):
    return os.path.join(TRENDS_DIR, season, "all_anime", f"{anime_id}.png")


def genre_png_path(season, genre, anime_id):
    return os.path.join(TRENDS_DIR, season, "genres", genre, f"{anime_id}.png")


def genre_data_dir(season, genre):
    if season is None:
        return os.path.join(DATA_DIR, "genres", genre)
    return os.path.join(DATA_DIR, season, "genres", genre)


def genre_csv_path(season, genre, anime_id):
    return os.path.join(genre_data_dir(season, genre), f"{anime_id}.csv")


def genre_trend_png_path(season, genre):
    if season is None:
        return os.path.join(TRENDS_DIR, "genres", genre, "all_anime.png")
    return os.path.join(TRENDS_DIR, season, "genres", genre, "all_anime.png")


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
    for column in ("danime_favorites", "danime_rank", "danime_weekly_rank"):
        if column not in df:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.sort_values("date")
    add_change_rates(df)

    colors = ("#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3")
    fig, axes = plt.subplots(len(TREND_METRICS) * 2, 1,
                             figsize=(10, 2.5 * len(TREND_METRICS) * 2),
                             sharex=True)
    for index, (column, label, ylabel) in enumerate(TREND_METRICS):
        value_axis = axes[index * 2]
        rate_axis = axes[index * 2 + 1]
        rate_column = f"{column}_change_pct"
        values = df[column]

        value_axis.plot(df["date"], values, marker="o", color=colors[index],
                        label=ylabel)
        if values.notna().any():
            average = values.mean()
            average_label = (
                f"平均 {average:.2f}" if column == "mal_score"
                else f"平均 {average:,.0f}" if column in ("mal_members", "danime_favorites")
                else f"平均 {average:.1f}"
            )
            value_axis.axhline(average, color="gray", linestyle="--", linewidth=1,
                               label=average_label)
        value_axis.set_title(
            f"{anime['name']} - {label}推移 ({latest_change_label(df[rate_column])})"
        )
        value_axis.set_ylabel(ylabel)
        value_axis.legend()
        value_axis.grid(alpha=0.3)
        if column in ("danime_rank", "danime_weekly_rank") and values.notna().any():
            value_axis.invert_yaxis()

        rate_axis.plot(df["date"], df[rate_column], marker="o", color=colors[index])
        rate_axis.axhline(0, color="gray", linestyle="--", linewidth=1)
        rank_note = (
            "・負の値は順位改善"
            if column in ("danime_rank", "danime_weekly_rank") else ""
        )
        rate_axis.set_title(f"{label}変化率 (初回取得日比{rank_note})")
        rate_axis.set_ylabel("%")
        rate_axis.grid(alpha=0.3)

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.autofmt_xdate()
    plt.tight_layout()

    out_path = title_png_path(season, aid)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def make_collection_chart(season, title, animes, anime_frames, out_path):
    if not anime_frames:
        return None

    df = pd.concat(anime_frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["mal_score"] = pd.to_numeric(df["mal_score"], errors="coerce")
    df["mal_members"] = pd.to_numeric(
        df["mal_members"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    for column in ("danime_favorites", "danime_rank", "danime_weekly_rank"):
        if column not in df:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.sort_values(["anime_id", "date"])
    add_change_rates(df, per_anime=True)
    anime_names = {anime["anime_id"]: anime["name"] for anime in animes}
    anime_rows = list(df.groupby("anime_id"))
    fig_height = min(48, max(18, 12 + 0.5 * len(anime_rows)))
    fig, axes = plt.subplots(len(TREND_METRICS) * 2, 1,
                             figsize=(12, fig_height), sharex=True)

    for index, (column, label, ylabel) in enumerate(TREND_METRICS):
        value_axis = axes[index * 2]
        rate_axis = axes[index * 2 + 1]
        for anime_id, rows in anime_rows:
            name = anime_names.get(anime_id, anime_id)
            line, = value_axis.plot(
                rows["date"], rows[column], marker="o", markersize=2,
                linewidth=1, label=name,
            )
            rate_axis.plot(
                rows["date"], rows[f"{column}_change_pct"], marker="o",
                markersize=2, linewidth=1, color=line.get_color(),
            )
        value_axis.set_title(f"{season or '全シーズン'} / {title} - {label}推移")
        value_axis.set_ylabel(ylabel)
        rank_note = (
            "・負の値は順位改善"
            if column in ("danime_rank", "danime_weekly_rank") else ""
        )
        rate_axis.set_title(f"{label}変化率 (各作品の初回取得日比{rank_note})")
        rate_axis.set_ylabel("%")
        rate_axis.axhline(0, color="gray", linestyle="--", linewidth=1)
        if column in ("danime_rank", "danime_weekly_rank") and df[column].notna().any():
            value_axis.invert_yaxis()
        value_axis.grid(alpha=0.3)
        rate_axis.grid(alpha=0.3)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center left", bbox_to_anchor=(0.77, 0.5),
               fontsize="small")

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.subplots_adjust(right=0.75, hspace=0.7)
    fig.autofmt_xdate()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def make_genre_chart(season, genre, animes):
    anime_frames = []
    for anime in animes:
        path = genre_csv_path(season, genre, anime["anime_id"])
        if not os.path.exists(path):
            continue
        anime_df = pd.read_csv(path)
        if not anime_df.empty:
            anime_frames.append(anime_df)

    return make_collection_chart(
        season, genre, animes, anime_frames, genre_trend_png_path(season, genre)
    )


def make_season_chart(season, animes):
    anime_frames = []
    for anime in animes:
        path = title_csv_path(season, anime["anime_id"])
        if not os.path.exists(path):
            continue
        anime_df = pd.read_csv(path)
        if not anime_df.empty:
            anime_frames.append(anime_df)

    out_path = os.path.join(TRENDS_DIR, season, "all_anime", "all_anime.png")
    return make_collection_chart(season, "全作品", animes, anime_frames, out_path)


def remove_legacy_genre_csv(season, genre):
    path = os.path.join(genre_data_dir(season, genre), "all_anime.csv")
    if os.path.exists(path):
        os.remove(path)


genres_by_season = {}
animes_by_genre = {}
animes_by_season = {}
for anime in anime_list:
    png_path = make_chart(anime)
    if not png_path:
        print(f"skip: {anime['anime_id']} の個別トレンドグラフを作成できませんでした")
    else:
        print(f"Saved chart to {png_path}")

    season = anime.get("season", "unknown")
    animes_by_season.setdefault(season, []).append(anime)
    genres = [g.strip() for g in (anime.get("genre") or "").split(",") if g.strip()]
    for genre in genres:
        source_data = title_csv_path(season, anime["anime_id"])
        if os.path.exists(source_data):
            for scope in (season, None):
                dest = genre_csv_path(scope, genre, anime["anime_id"])
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(source_data, dest)
        if png_path:
            dest = genre_png_path(season, genre, anime["anime_id"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(png_path, dest)
        genres_by_season.setdefault((season, genre), []).append(anime)
        animes_by_genre.setdefault(genre, []).append(anime)

for season, animes in sorted(animes_by_season.items()):
    png_path = make_season_chart(season, animes)
    if png_path:
        print(f"Saved season chart to {png_path}")

for (season, genre), animes in sorted(genres_by_season.items()):
    remove_legacy_genre_csv(season, genre)

    png_path = make_genre_chart(season, genre, animes)
    if png_path:
        print(f"Saved genre chart to {png_path}")

for genre, animes in sorted(animes_by_genre.items()):
    remove_legacy_genre_csv(None, genre)

    for anime in animes:
        season = anime.get("season", "unknown")
        source_chart = title_png_path(season, anime["anime_id"])
        if os.path.exists(source_chart):
            dest = os.path.join(TRENDS_DIR, "genres", genre, f"{anime['anime_id']}.png")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(source_chart, dest)

    png_path = make_genre_chart(None, genre, animes)
    if png_path:
        print(f"Saved all-season genre chart to {png_path}")
