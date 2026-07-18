from playwright.sync_api import sync_playwright
import re

URL = "https://myanimelist.net/anime/49233/Youjo_Senki_II"

with sync_playwright() as p:

    browser = p.chromium.launch(headless=True)

    page = browser.new_page()

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    page.wait_for_timeout(5000)

html = page.content()

with open("page.html", "w", encoding="utf-8") as f:
    f.write(html)

print("HTML saved.")

    page.wait_for_timeout(5000)

    page.wait_for_selector("body")

    text = page.locator("body").inner_text()

    browser.close()

    score = re.search(r"Score\s*([0-9.]+)", text)

    members = re.search(r"Members\s*([\d,]+)", text)

    print("==========")

    score = None

try:
    score = page.locator(".score-label").inner_text()
except:
    pass

if score:
    print("Score:", score)
else:
    print("Score not found")

    

    if members:
        print("Members:", members.group(1))
    else:
        print("Members not found")
