from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 860})
        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path="/home/llwxy/aletheia/design/frontend/ui-current.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
