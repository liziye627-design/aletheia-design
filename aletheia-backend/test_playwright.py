#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simple Playwright test to diagnose browser issues.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_playwright_basic():
    """Test basic Playwright functionality."""
    print("Testing Playwright basic functionality...")

    try:
        from playwright.async_api import async_playwright

        print("  [1] Importing playwright... OK")

        async with async_playwright() as p:
            print("  [2] Starting playwright... OK")

            # Try to launch browser in headless mode
            print("  [3] Launching browser (headless=True)...")
            browser = await p.chromium.launch(headless=True)
            print("  [3] Browser launched! OK")

            # Create context
            print("  [4] Creating context...")
            context = await browser.new_context()
            print("  [4] Context created! OK")

            # Create page
            print("  [5] Creating page...")
            page = await context.new_page()
            print("  [5] Page created! OK")

            # Navigate to a simple page
            print("  [6] Navigating to example.com...")
            await page.goto("https://example.com", timeout=30000)
            title = await page.title()
            print(f"  [6] Page loaded! Title: {title}")

            # Cleanup
            await browser.close()
            print("  [7] Browser closed. OK")

        print("\n✅ Playwright test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ Playwright test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_crawler_config_only():
    """Test crawler without browser - just config."""
    print("\nTesting Crawler Config (no browser)...")

    try:
        from services.mediacrawler.config import CrawlerConfig, get_config
        from services.mediacrawler.factory import CrawlerFactory

        print("  [1] Testing config...")
        config = get_config()
        config.KEYWORDS = "伊朗与以色列为敌"
        config.CRAWLER_TYPE = "search"
        print(f"  [1] Config OK - Keywords: {config.KEYWORDS}")

        print("  [2] Testing factory...")
        platforms = CrawlerFactory.list_platforms()
        print(f"  [2] Factory OK - Platforms: {platforms}")

        print("  [3] Creating crawler instance...")
        crawler = CrawlerFactory.create_crawler("xhs")
        print(f"  [3] Crawler created: {type(crawler).__name__}")

        print("\n✅ Crawler config test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ Crawler config test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("Playwright Diagnostic Test")
    print("=" * 60)

    # Test 1: Basic Playwright
    result1 = asyncio.run(test_playwright_basic())

    # Test 2: Crawler Config
    result2 = asyncio.run(test_crawler_config_only())

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Playwright Basic: {'✅ PASS' if result1 else '❌ FAIL'}")
    print(f"  Crawler Config: {'✅ PASS' if result2 else '❌ FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()