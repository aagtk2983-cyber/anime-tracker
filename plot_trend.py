import os
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

CSV_PATH = os.path.join("data", "history.csv")
OUT_PATH = os.path.join("data", "trend.png")

# 日本語ラベルが豆腐(□□□)にならないよう、CJK対応フォントがあれば使う。
# 無ければ標準フォントにフォールバックする(GitHub Actions側で
# fonts-noto-cjk をインストールしておくことを想定)。
for name in ["Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic"]:
    if any(name.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = name
        break

df = pd.read_csv(CSV_PATH)
if df.empty:
    raise SystemExit("data/history.csv にデータがありません。先に daily_tracker.py を実行してください。")

df["date"] = pd.to_datetime(df["date"])
df["score"] = pd.to_numeric(df["score"], errors="coerce")
df["members"] = pd.to_numeric(
    df["members"].astype(str).str.replace(",", "", regex=False), errors="coerce"
)
df = df.sort_values("date")

fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# --- スコア推移 ---
axes[0].plot(df["date"], df["score"], marker="o", color="#4C72B0", label="Score")
if df["score"].notna().any():
    avg_score = df["score"].mean()
    axes[0].axhline(avg_score, color="gray", linestyle="--", linewidth=1,
                     label=f"平均 {avg_score:.2f}")
axes[0].set_title("幼女戦記II - MALスコア推移")
axes[0].set_ylabel("Score")
axes[0].legend()
axes[0].grid(alpha=0.3)

# --- メンバー数推移 ---
axes[1].plot(df["date"], df["members"], marker="o", color="#DD8452", label="Members")
if df["members"].notna().any():
    avg_members = df["members"].mean()
    axes[1].axhline(avg_members, color="gray", linestyle="--", linewidth=1,
                     label=f"平均 {avg_members:,.0f}")
axes[1].set_title("幼女戦記II - MALメンバー数推移")
axes[1].set_ylabel("Members")
axes[1].legend()
axes[1].grid(alpha=0.3)

axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
fig.autofmt_xdate()
plt.tight_layout()

os.makedirs("data", exist_ok=True)
plt.savefig(OUT_PATH, dpi=150)
print(f"Saved chart to {OUT_PATH}")
