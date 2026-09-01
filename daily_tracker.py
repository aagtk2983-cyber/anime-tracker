from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import os
import csv
import shutil
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from season_utils import current_mal_season, seasons_elapsed

JST = ZoneInfo("Asia/Tokyo")
DATA_DIR = "data"
ANIME_LIST_PATH = "anime_list.csv"

# 1タイトルあたり何シーズン追跡するか(開始シーズン + 次シーズン = 2)
TRACK_SEASONS = 2

FIELDNAMES = [
    "anime_id", "season", "date", "time",
    "mal_score", "mal_members",
    "danime_favorites", "danime_rank",
]

# 以前は「デイリーランキング: コンプリート視聴されたアニメ」(CR00003003)を使っていたが、
# これは"最後まで見終えた"作品のランキングのため、放送中の新作はほぼ入らず、
# danime_rank が常に空欄になる原因になっていた。
# 「総合ランキング(視聴数ベース)」に切り替える。こちらは見放題内の視聴数を
# 元にしたランキングで、放送中の新作でも上位に来やすい。
DANIME_RANKING_URL = "https://animestore.docomo.ne.jp/animestore/CR/CR00000014?ranking_type=views"
DANIME_RANKING_PERIOD_TAB_TEXT = "デイリー"

# --- ABEMA 話数別視聴数 ---
# ABEMAは全アニメが配信されているわけではないため、まずは対象を明示的に
# 手動登録する方式にする(anime_id -> ABEMAのシリーズslug)。
# シリーズslugは https://abema.tv/video/episode/<slug>_p<話数> の <slug> 部分。
# 例: 幼女戦記Ⅱ 第1話 = https://abema.tv/video/episode/25-46_s2_p1 なので slug="25-46_s2"
# (幼女戦記は1期・2期でタイトルIDそのものは "25-46" を共有し、"_s2" が2期を表す)
ABEMA_TARGETS = {
    "youjosenki2": "25-46_s2",
}
ABEMA_FIELDNAMES = ["date", "time", "episode", "view_count"]


# ABEMAは地域制限があり、日本国外のIPからは中身が返ってこない
# (実際に検証済み: 「このサービスはお住まいの地域からはご利用になれません」)。
# GitHub Actionsのホスト型ランナーは日本国外にあるため、ABEMA部分だけは
# 環境変数で日本国内IPのプロキシを指定できるようにしておく。
# 未設定なら何もせず今までどおり(プロキシなし)で試行する。
ABEMA_PROXY_SERVER = os.environ.get("ABEMA_PROXY_SERVER", "").strip()
ABEMA_PROXY_USERNAME = os.environ.get("ABEMA_PROXY_USERNAME", "").strip()
ABEMA_PROXY_PASSWORD = os.environ.get("ABEMA_PROXY_PASSWORD", "").strip()


def abema_proxy_config():
    if not ABEMA_PROXY_SERVER:
        return None
    config = {"server": ABEMA_PROXY_SERVER}
    if ABEMA_PROXY_USERNAME:
        config["username"] = ABEMA_PROXY_USERNAME
    if ABEMA_PROXY_PASSWORD:
        config["password"] = ABEMA_PROXY_PASSWORD
    return config


def abema_view_csv_path(season, anime_id):
    return os.path.join(DATA_DIR, season, "abema_views", f"{anime_id}.csv")


def fetch_abema_episode_numbers(page, series_slug):
    """
    ABEMAのタイトルページから、現在配信されている話数の一覧を取得する。

    個々のDOM構造(クラス名など)に依存すると壊れやすいため、
    ページのHTML全体から "<series_slug>_p<数字>" というエピソードURLの
    パターンをそのまま正規表現で拾う方式にしている
    (リンクがどんなタグ・属性で埋め込まれていても拾える)。

    ここで取得できるHTMLは毎回 data/debug_abema_title.html / .png に
    上書き保存する。ABEMAは地域制限があり、日本国外のIPからアクセスすると
    「このサービスはお住まいの地域からはご利用になれません」という
    エラーページが(exceptionを出さずに)普通に200で返ってくるため、
    話数が1件も見つからない状態が続く場合はまずこのファイルを確認し、
    地域制限のエラーページになっていないかを見ること。
    """
    title_id = series_slug.split("_s")[0]
    url = f"https://abema.tv/video/title/{title_id}?s={series_slug}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    html = page.content()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "debug_abema_title.html"), "w", encoding="utf-8") as f:
        f.write(html)
    try:
        page.screenshot(path=os.path.join(DATA_DIR, "debug_abema_title.png"), full_page=True)
    except Exception:
        pass

    pattern = re.escape(series_slug) + r"_p(\d+)"
    episode_numbers = sorted({int(n) for n in re.findall(pattern, html)})
    return episode_numbers


def parse_abema_view_count(html):
    """
    ABEMAのエピソード視聴ページのHTMLから視聴数(目のアイコンの数字)を取り出す。

    ページの実際のDOM構造をこちらの環境からは確認できていない
    (ABEMAが地域制限をかけており、日本国内以外からのアクセスが
    「このサービスはお住まいの地域からはご利用になれません」で
    弾かれるため)。そのため下記は複数のフォールバックを試すベストエフォート
    実装になっている。実行後に data/debug_abema_episode.html / .png が
    毎回上書き保存されるので、うまく取得できていない場合はそれを見て
    セレクタを調整すること。
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) Next.js等のSSRアプリでよくある、埋め込みJSON(__NEXT_DATA__ など)から探す
    for script in soup.find_all("script"):
        script_text = script.string or script.get_text() or ""
        if not script_text.strip():
            continue
        m = re.search(r'"(?:viewCount|playCount|viewingCount)"\s*:\s*(\d+)', script_text)
        if m:
            return int(m.group(1))

    # 2) 画面上のテキストに "視聴数" のようなラベルがあればその直後の数字を使う
    text = soup.get_text(" ", strip=True)
    m = re.search(r"視聴数[^\d]{0,10}([\d,]+)", text)
    if m:
        return int(m.group(1).replace(",", ""))

    # 3) aria-label等に "視聴" を含む要素があれば、その中の数字を使う
    for el in soup.find_all(attrs={"aria-label": re.compile("視聴")}):
        m = re.search(r"([\d,]+)", el.get_text(" ", strip=True))
        if m:
            return int(m.group(1).replace(",", ""))

    return None


def fetch_abema_view_count(page, episode_url, save_debug=False):
    page.goto(episode_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    html = page.content()

    if save_debug:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "debug_abema_episode.html"), "w", encoding="utf-8") as f:
            f.write(html)
        try:
            page.screenshot(path=os.path.join(DATA_DIR, "debug_abema_episode.png"), full_page=True)
        except Exception:
            pass

    return parse_abema_view_count(html)


def write_abema_episode_rows(season, anime_id, date, time_str, episode_views):
    """
    1タイトル1ファイル(data/<season>/abema_views/<anime_id>.csv)に、
    話数ごとの視聴数を縦持ち(long format)で記録する。
    例えば8話まで配信されていれば、1話〜8話それぞれの行を1本ずつ書く。
    話数が増えれば、その分の行が新たに追加されていく。
    同じ日に再実行した場合は、その日×その話数の行を上書き(重複させない)。
    """
    path = abema_view_csv_path(season, anime_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    rows = [r for r in rows if r.get("date") != date]
    for episode, view_count in episode_views.items():
        rows.append({
            "date": date,
            "time": time_str,
            "episode": episode,
            "view_count": view_count if view_count is not None else "",
        })
    rows.sort(key=lambda r: (r.get("date", ""), int(r.get("episode") or 0)))

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ABEMA_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return path


def load_anime_list():
    with open(ANIME_LIST_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if (r.get("anime_id") or "").strip()]


def fetch_mal(page, mal_id, mal_slug):
    """MyAnimeList: スコアとメンバー数"""
    url = f"https://myanimelist.net/anime/{mal_id}/{mal_slug}" if mal_slug else f"https://myanimelist.net/anime/{mal_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body")
    html = page.content()

    soup = BeautifulSoup(html, "html.parser")
    score_tag = soup.find("span", attrs={"itemprop": "ratingValue"})
    score = score_tag.get_text(strip=True) if score_tag else None

    members = None
    for tag in soup.find_all("span", class_="dark_text"):
        if tag.get_text(strip=True).startswith("Members"):
            parent_text = tag.parent.get_text(" ", strip=True)
            m = re.search(r"Members[:\s]*([\d,]+)", parent_text)
            if m:
                members = m.group(1)
            break

    return score, members


def fetch_danime_favorites(page, danime_work_id):
    """dアニメストア: 気になる登録数(お気に入り相当)"""
    url = f"https://animestore.docomo.ne.jp/animestore/ci_pc?workId={danime_work_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body")
    html = page.content()
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    m = re.search(r"気になる登録数[：:]\s*([\d,]+)", text)
    return m.group(1) if m else None


DANIME_RANK_TITLE_RE = re.compile(r"^(\d{1,3})[.\s\u3000\xa0]*(.+)$")


def parse_danime_ranking_items(html):
    """
    dアニメストア デイリーランキングページのHTMLから、
    {danime_work_id: {"rank": int, "title": str}} の辞書を作る。

    このページは実際には「N位」ではなく「N.」という表記で、
    かつ HTML構造が2種類ある:
      - 1〜3位: <div class="itemModule ranking"> 内に
                <i class="iconRankN">N.</i> と
                <span class="ui-clamp webkit2LineClamp">タイトル</span> が別要素
      - 4位以降: <div class="itemModule list"> 内の
                <span class="ui-clamp webkit2LineClamp">N. タイトル</span> に
                順位とタイトルがまとめて入っている
    「気になる」チェックボックス <input class="favo ui-favo" data-workid="..."> には
    どちらの構造でも必ず data-workid が入っているため、これはタイトルの表記ゆれに
    影響されない確実なキーとして主キーに使う(4位以降は外側divにも付くが、
    1〜3位の外側divには付かないため input 側で統一して取得する)。
    """
    soup = BeautifulSoup(html, "html.parser")
    items = {}

    def get_work_id(div):
        checkbox = div.find("input", class_="favo")
        if checkbox and checkbox.get("data-workid"):
            return checkbox.get("data-workid")
        return div.get("data-workid")

    for div in soup.find_all("div", class_="itemModule ranking"):
        work_id = get_work_id(div)
        span = div.find("span", class_="ui-clamp webkit2LineClamp")
        if not span:
            continue
        title = span.get_text(strip=True)

        rank = None
        icon = div.find("i", class_=re.compile(r"iconRank\d+"))
        if icon:
            m = re.match(r"(\d+)", icon.get_text(strip=True))
            if m:
                rank = int(m.group(1))
        if rank is None:
            m = DANIME_RANK_TITLE_RE.match(title)
            if m:
                rank = int(m.group(1))
                title = m.group(2).strip()

        if work_id and rank is not None:
            items[work_id] = {"rank": rank, "title": title}

    for div in soup.find_all("div", class_="itemModule list"):
        work_id = get_work_id(div)
        span = div.find("span", class_="ui-clamp webkit2LineClamp")
        if not span:
            continue
        m = DANIME_RANK_TITLE_RE.match(span.get_text(strip=True))
        if not m or not work_id:
            continue
        items[work_id] = {"rank": int(m.group(1)), "title": m.group(2).strip()}

    return items


def fetch_danime_ranking_items(page, max_ranks=300, max_scrolls=40):
    """
    dアニメストア デイリーランキングページを取得する。

    このページは初期表示では上位20件分の要素しかDOMに存在せず、
    ページ最下部の <div id="loader" class="loader checkOnScreen"> が
    画面内に入ったタイミングで(IntersectionObserverによる無限スクロール)
    追加の20件が読み込まれる作りになっている。
    そのため一度読み込んだだけでは20位より下の順位が一切取得できず、
    「N位」という表記自体もページ内に存在しない(実際は「N.」表記)ため、
    以前の実装(get_text→"N位"を正規表現検索)は常に失敗していた。

    ここでは、読み込み済みの件数が増えなくなる/max_ranksに達するまで、
    ページ下部へのスクロール→少し待機、を繰り返して読み込みを促す。

    以前は「コンプリート視聴されたアニメ」ランキングを使っていたが、
    これは視聴し終えた作品のランキングであり、上位は劇場版まどか☆マギカや
    ちいかわのような定番の人気作・旧作が占め続け、放送中の新作
    (当システムが追跡する対象)はまだ最後まで見終えたユーザーが少ないため
    ほぼランクインしなかった。そのため danime_rank が常に空欄になっていた。
    現在は「総合ランキング(視聴数ベース)」(CR00000014, ranking_type=views)を
    参照する。こちらは視聴数ベースのため放送中の新作でも上位に来やすい。

    このランキングページは デイリー/ウィークリー/年間/全期間 のタブが
    JS切り替え(href="javascript:void(0)")になっており、URLだけでは
    期間を指定できない。デフォルト表示がどのタブになるかはページ側の
    実装依存で確実ではないため、念のため「デイリー」タブを明示的に
    クリックしてから読み込みを行う(見つからない/クリックできない場合は
    デフォルト表示のまま読み込みを続行する)。
    """
    try:
        page.goto(DANIME_RANKING_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print("ランキングページの取得に失敗(1回目):", e)
        try:
            # 一度だけリトライ(一時的なネットワーク遅延対策)
            page.goto(DANIME_RANKING_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
        except Exception as e2:
            print("ランキングページの取得に失敗(2回目、諦める):", e2)
            return {}

    # 「デイリー」タブを明示的に選択する(取れなくても致命的ではないので握りつぶす)
    try:
        page.get_by_text(DANIME_RANKING_PERIOD_TAB_TEXT, exact=True).first.click(timeout=5000)
        page.wait_for_timeout(2000)
    except Exception as e:
        print("「デイリー」タブのクリックに失敗(デフォルト表示のまま続行):", e)

    prev_count = -1
    for i in range(max_scrolls):
        html = page.content()
        items = parse_danime_ranking_items(html)
        loaded_max_rank = max((v["rank"] for v in items.values()), default=0)
        print(f"  ランキング読み込み中... {i + 1}回目: {len(items)}件 (最大順位 {loaded_max_rank}位)")

        if loaded_max_rank >= max_ranks:
            break
        if len(items) == prev_count:
            # スクロールしても件数が増えない = もうこれ以上読み込めない
            break
        prev_count = len(items)

        try:
            page.mouse.wheel(0, 4000)
        except Exception:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)

    html = page.content()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "debug_danime_ranking.html"), "w", encoding="utf-8") as f:
        f.write(html)
    try:
        page.screenshot(path=os.path.join(DATA_DIR, "debug_danime_ranking.png"), full_page=True)
    except Exception:
        pass

    return parse_danime_ranking_items(html)


def rank_from_items(ranking_items, danime_work_id, danime_title):
    """
    data-workid での完全一致を優先。

    タイトルでのフォールバックは完全一致のみに限定する。
    以前は「danime_title in info['title'] または info['title'] in danime_title」
    という部分一致(前方一致/後方一致)を許していたが、これは
    「幼女戦記」と「幼女戦記Ⅱ」、「ぐらんぶる」と「『ぐらんぶる』Season 3」のような
    "同じ作品の別シーズン/別作品" まで一致してしまう欠陥があった
    (実際に 2026-08-29 の記録で幼女戦記Ⅱ に無関係の「幼女戦記」の順位が
    誤って記録される事故が発生している)。
    誤ったランキングを記録するくらいなら記録しない方が安全なため、
    空白/全角スペースなどの表記ゆれのみ吸収した完全一致に限定する。
    """
    if not ranking_items:
        return None

    if danime_work_id and danime_work_id in ranking_items:
        return str(ranking_items[danime_work_id]["rank"])

    if danime_title:
        normalized_target = re.sub(r"[\s\u3000]+", "", danime_title)
        for info in ranking_items.values():
            normalized_title = re.sub(r"[\s\u3000]+", "", info["title"])
            if normalized_title == normalized_target:
                return str(info["rank"])

    return None


def title_csv_path(season, anime_id):
    return os.path.join(DATA_DIR, season, "all_anime", f"{anime_id}.csv")


def genre_csv_path(season, genre, anime_id):
    return os.path.join(DATA_DIR, season, "genres", genre, f"{anime_id}.csv")


def write_title_row(season, anime_id, new_row):
    """
    1タイトル1ファイル(data/<season>/all_anime/<anime_id>.csv)に日々の記録を追記する。
    同じ日に再実行した場合はその日の行を上書き(重複させない)。
    """
    path = title_csv_path(season, anime_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    rows = [r for r in rows if r.get("date") != new_row["date"]]
    rows.append(new_row)
    rows.sort(key=lambda r: r.get("date", ""))

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return path


def mirror_into_genres(season, anime_id, genre_field, source_path):
    """
    all_anime配下のファイルを、該当する各ジャンルフォルダにもコピーする。
    (元データは all_anime の1ファイルのみが正なので、ジャンル側は毎回上書きコピー)
    """
    genres = [g.strip() for g in (genre_field or "").split(",") if g.strip()]
    for genre in genres:
        dest = genre_csv_path(season, genre, anime_id)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(source_path, dest)


anime_list = load_anime_list()

now = datetime.now(JST)
today = now.strftime("%Y-%m-%d")
time_str = now.strftime("%H:%M:%S")

# --- シーズンによる追跡対象の絞り込み ---
# 各タイトルの season 列は「このシステムで追跡を開始したシーズン」を表す。
# 開始シーズンから TRACK_SEASONS 分(=開始シーズン自身 + 次シーズン)だけ記録し、
# それを超えたタイトルは自動的に追跡終了(データは削除せず、記録だけ止める)。
current_season = current_mal_season(now)
active_anime_list = []
ended_anime_list = []
for a in anime_list:
    start_season = (a.get("season") or "").strip()
    if not start_season:
        # season未設定の行は念のため対象に含める(除外条件が判断できないため)
        active_anime_list.append(a)
        continue
    age = seasons_elapsed(start_season, now)
    if 0 <= age < TRACK_SEASONS:
        active_anime_list.append(a)
    else:
        ended_anime_list.append(a)

print(f"現在シーズン: {current_season}")
print(f"追跡対象: {len(active_anime_list)}件 / 追跡終了(対象外): {len(ended_anime_list)}件")
for a in ended_anime_list:
    print(f"  終了: {a['anime_id']} (開始シーズン={a.get('season')})")

anime_list = active_anime_list

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    danime_ranking_items = fetch_danime_ranking_items(page)
    print(f"dアニメ デイリーランキング取得件数: {len(danime_ranking_items)}件")

    for anime in anime_list:
        aid = anime["anime_id"]
        season = anime.get("season", "unknown")
        mal_id = (anime.get("mal_id") or "").strip()
        danime_work_id = (anime.get("danime_work_id") or "").strip()
        danime_title = (anime.get("danime_title") or "").strip()

        if not mal_id:
            print(f"skip (MAL ID未登録): {aid}")
            continue

        print(f"===== {aid} ({anime['name']}) =====")
        mal_score = mal_members = None
        danime_favorites = danime_rank = None

        try:
            mal_score, mal_members = fetch_mal(page, mal_id, anime.get("mal_slug", ""))
        except Exception as e:
            print("MAL取得に失敗しました:", e)

        if danime_work_id:
            try:
                danime_favorites = fetch_danime_favorites(page, danime_work_id)
            except Exception as e:
                print("dアニメ(お気に入り)取得に失敗しました:", e)

        if danime_work_id or danime_title:
            danime_rank = rank_from_items(danime_ranking_items, danime_work_id, danime_title)

        print("MAL Score:", mal_score, "/ Members:", mal_members)
        print("dアニメ 気になる登録数:", danime_favorites, "/ ランキング:", danime_rank)

        new_row = {
            "anime_id": aid,
            "season": season,
            "date": today,
            "time": time_str,
            "mal_score": mal_score or "",
            "mal_members": mal_members or "",
            "danime_favorites": danime_favorites or "",
            "danime_rank": danime_rank or "",
        }
        title_path = write_title_row(season, aid, new_row)
        mirror_into_genres(season, aid, anime.get("genre", ""), title_path)

        time.sleep(2)  # サイトへの配慮として、タイトルごとに少し間隔を空ける

    # --- ABEMA 話数別視聴数 ---
    if ABEMA_TARGETS:
        print("\n===== ABEMA 話数別視聴数 =====")
        # season は anime_list.csv 側の値を使う(見つからなければ unknown)
        season_by_id = {a["anime_id"]: a.get("season", "unknown") for a in anime_list}

        # ABEMAは地域制限があるため、専用のプロキシ設定を使えるように
        # dアニメ/MAL用のpageとは別のbrowser contextを使う。
        # ABEMA_PROXY_SERVER が未設定ならプロキシなしの通常contextになる
        # (=これまでと同じ挙動。地域制限で失敗する可能性が高いが、
        #  日本国内で手元実行する場合などはこのままで動く)。
        proxy = abema_proxy_config()
        if proxy:
            print(f"ABEMA: プロキシ経由でアクセスします ({proxy['server']})")
        else:
            print("ABEMA: プロキシ未設定です。地域制限により取得できない可能性があります"
                  "(ABEMA_PROXY_SERVER 環境変数で日本国内プロキシを指定できます)")
        abema_context = browser.new_context(proxy=proxy) if proxy else browser.new_context()
        abema_page = abema_context.new_page()

        try:
            for aid, series_slug in ABEMA_TARGETS.items():
                season = season_by_id.get(aid, "unknown")
                print(f"--- {aid} (ABEMA slug={series_slug}) ---")
                try:
                    episode_numbers = fetch_abema_episode_numbers(abema_page, series_slug)
                except Exception as e:
                    print("ABEMA話数一覧の取得に失敗しました:", e)
                    continue

                if not episode_numbers:
                    print("配信中の話数が見つかりませんでした"
                          "(地域制限等でページが取得できていない可能性があります。"
                          "data/debug_abema_title.html を確認してください)")
                    continue

                max_episode = max(episode_numbers)
                print(f"配信中: {max_episode}話まで確認 (検出した話数: {episode_numbers})")

                episode_views = {}
                for ep in range(1, max_episode + 1):
                    url = f"https://abema.tv/video/episode/{series_slug}_p{ep}"
                    try:
                        views = fetch_abema_view_count(abema_page, url, save_debug=(ep == max_episode))
                    except Exception as e:
                        print(f"  {ep}話: 取得失敗 ({e})")
                        views = None
                    print(f"  {ep}話: 視聴数={views}")
                    episode_views[ep] = views
                    time.sleep(2)  # サイトへの配慮として、話数ごとに少し間隔を空ける

                write_abema_episode_rows(season, aid, today, time_str, episode_views)
        finally:
            abema_context.close()

    browser.close()

n_active = len([a for a in anime_list if (a.get("mal_id") or "").strip()])
print(f"\nRecorded {n_active}/{len(anime_list)} title(s): {today} {time_str}")
