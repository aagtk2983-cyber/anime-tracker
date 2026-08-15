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
    anime_list = list(csv.DictReader(f))
names = {a["anime_id"]: a["name"] for a in anime_list}

df = pd.read_csv(CSV_PATH)
if df.empty:
    raise SystemExit("data/history.csv にデータがありません。先に daily_tracker.py を実行してください。")

df["date"] = pd.to_datetime(df["date"])
df["mal_score"] = pd.to_numeric(df["mal_score"], errors="coerce")
df["mal_members"] = pd.to_numeric(
    df["mal_members"].astype(str).str.replace(",", "", regex=False), errors="coerce"
)

# 指定があればそのタイトルだけ、なければ登録されている全タイトル分を出力
target_ids = sys.argv[1:] if len(sys.argv) > 1 else df["anime_id"].unique().tolist()

for aid in target_ids:
    sub = df[df["anime_id"] == aid].sort_values("date")
    if sub.empty:
        print(f"skip: {aid} のデータがありません")
        continue

    title = names.get(aid, aid)
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    axes[0].plot(sub["date"], sub["mal_score"], marker="o", color="#4C72B0", label="Score")
    if sub["mal_score"].notna().any():
        avg_score = sub["mal_score"].mean()
        axes[0].axhline(avg_score, color="gray", linestyle="--", linewidth=1,
                         label=f"平均 {avg_score:.2f}")
    axes[0].set_title(f"{title} - MALスコア推移")
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
