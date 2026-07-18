from playwright.sync_api import sync_playwright

URL = "https://myanimelist.net/anime/49233/Youjo_Senki_II"

with sync_playwright() as p:

    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    )

    page.goto(URL, wait_until="networkidle", timeout=60000)

    print("Title:")
    print(page.title())

    print("\nURL:")
    print(page.url)

    print("\nFirst 500 chars:")
    print(page.content()[:500])

    browser.close()
