# -*- coding: utf-8 -*-
"""
MALのシーズン区分(冬/春/夏/秋)に合わせてシーズン文字列を扱うユーティリティ。

シーズン文字列の形式: "<year>-<season>" 例: "2026-summer"
season は winter / spring / summer / fall のいずれか。

MALのシーズン月割り当て:
  winter: 1-3月
  spring: 4-6月
  summer: 7-9月
  fall  : 10-12月
"""
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

SEASON_ORDER = ["winter", "spring", "summer", "fall"]

_MONTH_TO_SEASON = {
    1: "winter", 2: "winter", 3: "winter",
    4: "spring", 5: "spring", 6: "spring",
    7: "summer", 8: "summer", 9: "summer",
    10: "fall", 11: "fall", 12: "fall",
}


def season_index(season_str):
    """'2026-summer' のようなシーズン文字列を、比較可能な整数に変換する。"""
    year_str, name = season_str.strip().split("-", 1)
    return int(year_str) * 4 + SEASON_ORDER.index(name)


def current_mal_season(now=None):
    """今日の日付(JST)から、MAL基準の現在シーズン文字列を返す。"""
    now = now or datetime.now(JST)
    return f"{now.year}-{_MONTH_TO_SEASON[now.month]}"


def next_mal_season(season_str=None, now=None):
    """指定シーズン(省略時は現在シーズン)の、次のシーズン文字列を返す。"""
    base = season_str or current_mal_season(now)
    idx = season_index(base) + 1
    year, name = divmod(idx, 4)
    return f"{year}-{SEASON_ORDER[name]}"


def seasons_elapsed(start_season_str, now=None):
    """
    現在シーズンが start_season から何シーズン後かを返す。
    0 = 開始シーズンそのもの, 1 = 次のシーズン, 2 = その次のシーズン ...
    """
    return season_index(current_mal_season(now)) - season_index(start_season_str)
