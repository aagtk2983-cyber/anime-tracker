# -*- coding: utf-8 -*-
"""
週次レポート生成スクリプト(Gemini API使用)。

やること:
  1. 現在シーズンの全アニメについて、直近7日間のMALスコア/会員数、
     dアニメお気に入り数/デイリーランキング順位の変化を集計する。
  2. Gemini APIに「全体の週次レポート」
     (多くの作品に共通する傾向 + 突出した動きをした作品のピックアップ +
      その要因の推測)を書かせる。
  3. 全体レポート生成に使ったトークン数を確認し、GEMINI_TOKEN_BUDGET に
     余裕があれば、作品数の多いジャンルから順にジャンル別レポートも生成する。
     トークン予算が尽きた場合や、Gemini側のレート制限(429)を検知した
     場合は、そこで安全に打ち切る。
  4. 結果を reports/<season>/<週ラベル>.md として保存する。
     例: reports/2026-summer/2026-W35.md
     (season は season_utils.py と同じ "<year>-<season名>" 形式)
     ファイルの保存だけを行い、コミット & プッシュは
     .github/workflows/weekly_report.yml 側で他のデータと同様に行う。

必要な環境変数:
  GEMINI_API_KEY            必須。Google AI Studio (https://aistudio.google.com/apikey)
                             で発行したAPIキー。
  GEMINI_MODEL               任意。既定値 "gemini-2.5-flash"。
  GEMINI_TOKEN_BUDGET         任意。1回の実行で使ってよい合計トークン数の目安。既定 100000。
  GEMINI_MAX_GENRE_REPORTS    任意。ジャンル別レポートの最大件数。既定 8。

注意:
  Gemini APIの無料枠のレート制限(1日あたりのリクエスト数など)は
  2025年末に大きく引き下げられており、かつ今後も変わりうる。
  本スクリプトはトークン数の見積もりに加えて、429エラー(レート制限)を
  検知した時点で残りのジャンル別レポートを打ち切るようにしている。
  実際の上限は https://ai.google.dev/gemini-api/docs/rate-limits を
  確認し、必要に応じて GEMINI_TOKEN_BUDGET / GEMINI_MAX_GENRE_REPORTS を
  調整すること。
"""

import os
import csv
import sys
import time
from datetime import datetime, timedelta
from collections import defaultdict

import requests

from season_utils import current_mal_season, JST

ANIME_LIST_PATH = "anime_list.csv"
DATA_DIR = "data"
REPORTS_DIR = "reports"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TOKEN_BUDGET = int(os.environ.get("GEMINI_TOKEN_BUDGET", "100000"))
GEMINI_MAX_GENRE_REPORTS = int(os.environ.get("GEMINI_MAX_GENRE_REPORTS", "8"))
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

WEEK_DAYS = 7
REQUEST_INTERVAL_SEC = 2  # 連続呼び出しでRPM制限に当たりにくくするための間隔


class RateLimitError(Exception):
    pass


def load_anime_list(season):
    with open(ANIME_LIST_PATH, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("anime_id") or "").strip()]
    return [r for r in rows if r.get("season") == season]


def to_float(value):
    if value is None:
        return None
    value = str(value).replace(",", "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_weekly_stats(anime, season, as_of):
    """1作品分のCSVを読み、直近WEEK_DAYS日間の始点/終点を比較する"""
    csv_path = os.path.join(DATA_DIR, season, "all_anime", f"{anime['anime_id']}.csv")
    if not os.path.exists(csv_path):
        return None

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    parsed = []
    for r in rows:
        try:
            dt = datetime.strptime(r["date"], "%Y-%m-%d")
        except (KeyError, ValueError):
            continue
        parsed.append((dt, r))
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0])

    window_start = as_of - timedelta(days=WEEK_DAYS)
    in_window = [p for p in parsed if window_start <= p[0] <= as_of]
    if len(in_window) < 2:
        # 直近1週間で比較できるデータ点が2つ未満 = 比較不能
        return None

    first_row, last_row = in_window[0][1], in_window[-1][1]

    score_first, score_last = to_float(first_row.get("mal_score")), to_float(last_row.get("mal_score"))
    members_first, members_last = to_float(first_row.get("mal_members")), to_float(last_row.get("mal_members"))
    rank_first, rank_last = to_float(first_row.get("danime_rank")), to_float(last_row.get("danime_rank"))

    def delta(a, b):
        return None if a is None or b is None else b - a

    def pct(a, b):
        return None if a is None or b is None or a == 0 else (b - a) / a * 100

    return {
        "anime_id": anime["anime_id"],
        "name": anime.get("name", anime["anime_id"]),
        "genres": [g.strip() for g in (anime.get("genre") or "").split(",") if g.strip()],
        "score_first": score_first,
        "score_last": score_last,
        "score_delta": delta(score_first, score_last),
        "members_first": members_first,
        "members_last": members_last,
        "members_delta": delta(members_first, members_last),
        "members_pct": pct(members_first, members_last),
        "rank_first": rank_first,
        "rank_last": rank_last,
    }


def format_rank_change(rank_first, rank_last):
    if rank_last is None:
        return "圏外/データなし"
    if rank_first is None:
        return f"{int(rank_last)}位(前週データなし)"
    delta = rank_last - rank_first
    if delta == 0:
        return f"{int(rank_last)}位(変動なし)"
    if delta < 0:
        return f"{int(rank_first)}位→{int(rank_last)}位({int(-delta)}ランクアップ)"
    return f"{int(rank_first)}位→{int(rank_last)}位({int(delta)}ランクダウン)"


def format_stats_table(stats_list):
    """Geminiに渡す簡潔なテキスト表(トークン節約のため1作品1行の " | " 区切り)"""
    lines = ["作品名 | スコア変化 | 会員数増加 | 会員数増加率 | dアニメ順位変化"]
    for s in stats_list:
        score_txt = f"{s['score_delta']:+.2f}" if s["score_delta"] is not None else "―"
        members_txt = f"{s['members_delta']:+,.0f}" if s["members_delta"] is not None else "―"
        pct_txt = f"{s['members_pct']:+.1f}%" if s["members_pct"] is not None else "―"
        rank_txt = format_rank_change(s["rank_first"], s["rank_last"])
        lines.append(f"{s['name']} | {score_txt} | {members_txt} | {pct_txt} | {rank_txt}")
    return "\n".join(lines)


def call_gemini(prompt, max_output_tokens=1500):
    if not GEMINI_API_KEY:
        raise RuntimeError("環境変数 GEMINI_API_KEY が設定されていません")

    url = GEMINI_ENDPOINT.format(model=GEMINI_MODEL)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": max_output_tokens,
        },
    }
    resp = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=120)

    if resp.status_code == 429:
        raise RateLimitError(resp.text[:500])
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason", "不明")
        raise RuntimeError(f"Geminiから本文が返りませんでした(reason={reason})")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    usage = data.get("usageMetadata", {})
    total_tokens = usage.get("totalTokenCount", 0)
    return text, total_tokens


OVERALL_PROMPT_TEMPLATE = """あなたはアニメ視聴動向の分析アナリストです。
以下は {season} シーズンに放送中のアニメについて、直近1週間(過去{days}日間)の
MyAnimeList(MAL)スコア・会員数増減と、dアニメストアのデイリーランキング順位変化を
まとめたデータです。値が「―」または「データなし」の項目は取得できなかったことを示します。

# データ(区切り文字は " | ")
{table}

# 依頼内容
このデータをもとに、日本語で以下の構成の週次レポートを書いてください。
1. 「今週の全体傾向」: 多くの作品に共通して見られた変化(会員数の伸び方やスコアの傾向など)を要約する
2. 「注目の作品」: 数値の変化が特に大きかった作品を2〜4本ピックアップし、それぞれの数値に軽く触れながら紹介する
3. 「推測される要因」: ピックアップした作品について、放送話数の進行やアニメ業界的な事情から
   「なぜそのような動きをしたと考えられるか」を推測して述べる(データから読み取れる推測であることが
   わかるように書き、断定的な言い方は避ける)
見出しは Markdown の "## " を使い、全体で800字程度を目安に簡潔にまとめてください。
データに存在しない情報(具体的な話数の内容など)を断定的に書かないでください。"""

GENRE_PROMPT_TEMPLATE = """あなたはアニメ視聴動向の分析アナリストです。
以下は {season} シーズンの「{genre}」ジャンルの作品について、直近1週間(過去{days}日間)の
MyAnimeList(MAL)スコア・会員数増減と、dアニメストアのデイリーランキング順位変化を
まとめたデータです。

# データ(区切り文字は " | ")
{table}

# 依頼内容
「{genre}」ジャンル内での傾向に絞って、日本語で以下を400字程度で簡潔にまとめてください。
1. ジャンル内で共通して見られた傾向
2. ジャンル内で特に動きが大きかった作品と、推測される要因(断定的な言い方は避ける)
見出しは Markdown の "## " を使ってください。"""


def build_report(season, as_of):
    anime_list = load_anime_list(season)
    if not anime_list:
        print(f"{season} シーズンの登録アニメが見つかりません")
        return None

    stats_by_id = {}
    for anime in anime_list:
        stats = load_weekly_stats(anime, season, as_of)
        if stats:
            stats_by_id[anime["anime_id"]] = stats

    if not stats_by_id:
        print("週次比較に使える十分なデータがありません(まだ7日分のデータが溜まっていない可能性)")
        return None

    all_stats = list(stats_by_id.values())

    # 全体レポート用データ: 会員数増加率の上位・下位を中心に絞ってトークンを節約する
    def sort_key(s):
        return s["members_pct"] if s["members_pct"] is not None else -1e9

    ranked = sorted(all_stats, key=sort_key, reverse=True)
    highlight_n = 15
    if len(ranked) > highlight_n * 2:
        highlighted = ranked[:highlight_n] + ranked[-highlight_n:]
    else:
        highlighted = ranked

    total_tokens_used = 0
    sections = [f"# {season} 週次レポート ({as_of.strftime('%Y-%m-%d')} 時点)\n"]

    overall_prompt = OVERALL_PROMPT_TEMPLATE.format(
        season=season, days=WEEK_DAYS, table=format_stats_table(highlighted)
    )
    print("Gemini API呼び出し中(全体レポート)...")
    try:
        overall_text, tokens = call_gemini(overall_prompt, max_output_tokens=1500)
    except RateLimitError as e:
        print("レート制限のため全体レポートを生成できませんでした:", e)
        return None
    except Exception as e:
        print("全体レポート生成中にエラーが発生しました:", e)
        return None

    total_tokens_used += tokens
    print(f"  使用トークン数: {tokens}(累計 {total_tokens_used})")
    sections.append("## 全体レポート\n\n" + overall_text + "\n")

    remaining_budget = GEMINI_TOKEN_BUDGET - total_tokens_used
    print(f"残りトークン予算(目安): {remaining_budget} / {GEMINI_TOKEN_BUDGET}")

    genre_reports_done = 0
    if remaining_budget <= 0:
        print("トークン予算が残っていないため、ジャンル別レポートはスキップします")
    else:
        genre_map = defaultdict(list)
        for s in all_stats:
            for g in s["genres"]:
                genre_map[g].append(s)
        # 作品データが2本以上あるジャンルのみ対象。作品数が多いジャンルから順に処理する。
        genre_items = sorted(
            ((g, lst) for g, lst in genre_map.items() if len(lst) >= 2),
            key=lambda kv: len(kv[1]),
            reverse=True,
        )

        if genre_items:
            sections.append("## ジャンル別レポート\n")
            time.sleep(REQUEST_INTERVAL_SEC)

        for genre, lst in genre_items:
            if genre_reports_done >= GEMINI_MAX_GENRE_REPORTS:
                print(f"ジャンル別レポートの上限({GEMINI_MAX_GENRE_REPORTS}件)に達したため打ち切ります")
                break

            # ここまでの平均消費トークンから、次の1件に必要な量を粗く見積もる
            avg_used = total_tokens_used / max(genre_reports_done + 1, 1)
            est_needed = max(avg_used, 1000)
            if GEMINI_TOKEN_BUDGET - total_tokens_used < est_needed:
                print(f"残りトークン予算が少ないため、「{genre}」以降のジャンル別レポートはスキップします")
                break

            genre_prompt = GENRE_PROMPT_TEMPLATE.format(
                season=season, genre=genre, days=WEEK_DAYS, table=format_stats_table(lst)
            )
            print(f"Gemini API呼び出し中(ジャンル別: {genre} / 対象{len(lst)}作品)...")
            try:
                genre_text, tokens = call_gemini(genre_prompt, max_output_tokens=800)
            except RateLimitError as e:
                print(f"レート制限を検知したため、ここでジャンル別レポートを打ち切ります: {e}")
                break
            except Exception as e:
                print(f"「{genre}」のレポート生成中にエラーが発生したためスキップします:", e)
                continue

            total_tokens_used += tokens
            genre_reports_done += 1
            print(f"  使用トークン数: {tokens}(累計 {total_tokens_used})")
            sections.append(f"### {genre}\n\n{genre_text}\n")

            time.sleep(REQUEST_INTERVAL_SEC)

    sections.append(
        "---\n"
        f"*本レポートは Gemini API ({GEMINI_MODEL}) による自動生成です。"
        f"生成に使用したトークン数は約{total_tokens_used}"
        f"(ジャンル別レポート{genre_reports_done}件を含む、予算{GEMINI_TOKEN_BUDGET})。"
        "推測を含む内容のため、参考情報としてご利用ください。*"
    )

    return "\n".join(sections)


def report_path(season, as_of):
    year, week, _ = as_of.isocalendar()
    week_label = f"{year}-W{week:02d}"
    return os.path.join(REPORTS_DIR, season, f"{week_label}.md")


def main():
    now_jst = datetime.now(JST)
    season = current_mal_season(now_jst)
    as_of = datetime(now_jst.year, now_jst.month, now_jst.day)

    print(f"対象シーズン: {season} / 基準日: {as_of.strftime('%Y-%m-%d')} / モデル: {GEMINI_MODEL}")

    report_text = build_report(season, as_of)
    if not report_text:
        print("レポートを生成できなかったため終了します")
        sys.exit(0)  # データ不足やAPIエラーでワークフロー自体は失敗扱いにしない

    out_path = report_path(season, as_of)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"レポートを保存しました: {out_path}")


if __name__ == "__main__":
    main()
