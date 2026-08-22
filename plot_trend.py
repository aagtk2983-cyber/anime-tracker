import os
import sys
import csv
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

CSV_PATH = os.path.join("data", "history.csv")
ANIME_LIST_PATH = "anime_list.csv"

for name in ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic"]:
    if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = name
        break

with open(ANIME_LIST_PATH, encoding="utf-8") as f:
    anime_list = [r for r in csv.DictReader(f) if (r.get("anime_id") or "").strip()]
meta = {a["anime_id"]: a for a in anime_list}

df = pd.read_csv(CSV_PATH)
if df.empty:
    raise SystemExit("data/history.csv にデータがありません。先に daily_tracker.py を実行してください。")

df["date"] = pd.to_datetime(df["date"])
df["mal_score"] = pd.to_numeric(df["mal_score"], errors="coerce")
df["mal_members"] = pd.to_numeric(
    df["mal_members"].astype(str).str.replace(",", "", regex=False), errors="coerce"
)

target_ids = sys.argv[1:] if len(sys.argv) > 1 else df["anime_id"].unique().tolist()

for aid in target_ids:
    sub = df[df["anime_id"] == aid].sort_values("date")
    if sub.empty:
        print(f"skip: {aid} のデータがありません")
        continue

    info = meta.get(aid, {})
    title = info.get("name", aid)
    genre = info.get("genre", "")
    season = info.get("season", "")

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    axes[0].plot(sub["date"], sub["mal_score"], marker="o", color="#4C72B0", label="Score")
    if sub["mal_score"].notna().any():
        avg_score = sub["mal_score"].mean()
        axes[0].axhline(avg_score, color="gray", linestyle="--", linewidth=1,
                         label=f"平均 {avg_score:.2f}")
    axes[0].set_title(f"{title}({season} / {genre}) - MALスコア推移")
    axes[0].set_ylabel("Score")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(sub["date"], sub["mal_members"], marker="o", color="#DD8452", label="Members")
    if sub["mal_members"].notna().any():
        avg_members = sub["mal_members"].mean()
        axes[1].axhline(avg_members, color="gray", linestyle="--", linewidth=1,
                         label=f"平均 {avg_members:,.0f}")
    axes[1].set_title(f"{title} - MALメンバー数推移")
    axes[1].set_ylabel("Members")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.autofmt_xdate()
    plt.tight_layout()

    out_path = os.path.join("data", f"trend_{aid}.png")
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved chart to {out_path}")

# --- ジャンル別サマリー ---
# 1タイトルが複数ジャンルを持つ場合、集計上は該当する全ジャンルに重複してカウントする
# (history.csv 自体は1タイトル1行のまま変わらない。ここはあくまで分析用の展開)
latest = df.sort_values("date").groupby("anime_id").tail(1).copy()
latest["genre"] = latest["anime_id"].map(lambda a: meta.get(a, {}).get("genre", "その他"))
latest["genre"] = latest["genre"].fillna("その他").replace("", "その他")
exploded = latest.assign(genre=latest["genre"].str.split(",")).explode("genre")
genre_summary = exploded.groupby("genre")["mal_score"].agg(["mean", "count"]).sort_values("mean", ascending=False)
if not genre_summary.empty:
    print("\n=== ジャンル別 直近スコア平均(1タイトルが複数ジャンルに属す場合は重複集計) ===")
    print(genre_summary.round(2).to_string())
