from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re
import sys

URL = "https://myanimelist.net/anime/49233/Youjo_Senki_II"

html = None
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("body")
        # ブラウザを閉じる「前」に HTML を取得しておく
        # (旧コードのバグ: browser.close() の後に page.locator(...) を呼んでいて必ず失敗していた)
        html = page.content()
    except Exception as e:
        print("ページ取得に失敗しました:", e)
    finally:
        browser.close()

if html is None:
    sys.exit(1)

with open("page.html", "w", encoding="utf-8") as f:
    f.write(html)
print("HTML saved.")

soup = BeautifulSoup(html, "html.parser")

# --- タイトル確認 (Bot対策ページ等、別物を取得していないかの簡易チェック) ---
title = soup.title.get_text(strip=True) if soup.title else ""
print("Page title:", title)

# --- スコア取得 ---
# .score-label というCSSクラスだけに頼らず、itemprop="ratingValue" という
# schema.org由来の属性を使う。MAL側のデザイン変更の影響を受けにくく、
# 隣接する脚注番号(例: "8.44" の直後にある注釈の "1")も巻き込まない。
score_tag = soup.find("span", attrs={"itemprop": "ratingValue"})
score = score_tag.get_text(strip=True) if score_tag else None

# --- メンバー数取得 ---
# ページ全文への正規表現 (旧コード) は "Members:" のコロンを考慮しておらず
# マッチに失敗していた。ここでは "dark_text" ラベルの要素を目印にして、
# その親要素のテキストからメンバー数だけを抜き出す。
members = None
for tag in soup.find_all("span", class_="dark_text"):
    if tag.get_text(strip=True).startswith("Members"):
        parent_text = tag.parent.get_text(" ", strip=True)
        m = re.search(r"Members[:\s]*([\d,]+)", parent_text)
        if m:
            members = m.group(1)
        break

print("==========")
print("Score:", score if score else "Score not found")
print("Members:", members if members else "Members not found")
