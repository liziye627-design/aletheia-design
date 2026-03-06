import argparse
import asyncio

from playwright.async_api import async_playwright


URLS = {
    "xiaohongshu": "https://www.xiaohongshu.com",
    "douyin": "https://www.douyin.com",
    "zhihu": "https://www.zhihu.com",
    "bilibili": "https://www.bilibili.com",
}


async def main():
    parser = argparse.ArgumentParser(description="保存 Playwright 登录态 storage_state")
    parser.add_argument("--platform", required=True, choices=URLS.keys())
    parser.add_argument("--out", required=True, help="输出 storage_state.json 路径")
    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()

        await page.goto(URLS[args.platform], wait_until="domcontentloaded")
        print(f"[{args.platform}] 请在浏览器中完成登录和验证")
        input("完成后回到终端按回车保存 storage_state...\n")

        await context.storage_state(path=args.out)
        print(f"✅ 已保存: {args.out}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
