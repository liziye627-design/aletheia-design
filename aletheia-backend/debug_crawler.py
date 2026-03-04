#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Debug script to test the crawler flow with the keyword: 伊朗与以色列为敌
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_crawler_flow():
    """Test the complete crawler flow."""
    print("=" * 60)
    print("Starting Crawler Debug Test")
    print("Keyword: 伊朗与以色列为敌")
    print("=" * 60)

    # Step 1: Test imports
    print("\n[Step 1] Testing imports...")
    try:
        from services.mediacrawler.factory import CrawlerFactory
        print(f"  ✓ CrawlerFactory imported")
        print(f"  Available platforms: {CrawlerFactory.list_platforms()}")
    except Exception as e:
        print(f"  ✗ Failed to import CrawlerFactory: {e}")
        return

    # Step 2: Test platform registration
    print("\n[Step 2] Testing platform registration...")
    try:
        # Force re-registration
        import importlib
        import services.mediacrawler.factory as factory_module
        importlib.reload(factory_module)
        from services.mediacrawler.factory import CrawlerFactory
        platforms = CrawlerFactory.list_platforms()
        print(f"  Registered platforms: {platforms}")
        if not platforms:
            print("  ⚠ No platforms registered! Checking imports...")
            # Try manual imports
            try:
                from services.mediacrawler.platforms.xhs import XiaoHongShuCrawler
                print("    ✓ XHS crawler can be imported")
            except ImportError as e:
                print(f"    ✗ XHS import failed: {e}")
    except Exception as e:
        print(f"  ✗ Platform registration error: {e}")
        import traceback
        traceback.print_exc()

    # Step 3: Test config
    print("\n[Step 3] Testing config...")
    try:
        from services.mediacrawler.config import CrawlerConfig, get_config
        config = get_config()
        config.KEYWORDS = "伊朗与以色列为敌"
        config.CRAWLER_TYPE = "search"
        config.CRAWLER_MAX_NOTES_COUNT = 5
        config.ENABLE_GET_COMMENTS = False
        config.HEADLESS = True
        print(f"  ✓ Config created with keywords: {config.KEYWORDS}")
    except Exception as e:
        print(f"  ✗ Config error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 4: Try to create a crawler instance
    print("\n[Step 4] Creating crawler instance...")
    try:
        if "xhs" in CrawlerFactory.list_platforms():
            crawler = CrawlerFactory.create_crawler("xhs")
            print(f"  ✓ XHS crawler instance created: {type(crawler)}")
        else:
            print("  ⚠ XHS not registered, trying manual creation...")
            from services.mediacrawler.platforms.xhs.core import XiaoHongShuCrawler
            crawler = XiaoHongShuCrawler(config)
            print(f"  ✓ Manual XHS crawler created: {type(crawler)}")
    except Exception as e:
        print(f"  ✗ Crawler creation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 5: Test the manager
    print("\n[Step 5] Testing CrawlerManager...")
    try:
        from services.mediacrawler.manager import CrawlerManager, get_crawler_manager
        manager = get_crawler_manager()
        print(f"  ✓ Manager created")
        print(f"  Available platforms: {manager.list_platforms()}")
    except Exception as e:
        print(f"  ✗ Manager creation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 6: Try to start a crawler task (without actually running it fully)
    print("\n[Step 6] Starting crawler task...")
    try:
        # We'll start the task but limit it
        platform = "xhs" if "xhs" in manager.list_platforms() else manager.list_platforms()[0] if manager.list_platforms() else None

        if not platform:
            print("  ✗ No platforms available!")
            return

        task_id = await manager.start_crawler(
            platform=platform,
            keywords=["伊朗与以色列为敌"],
            config={
                "headless": True,
                "enable_comments": False,
                "max_notes": 3,
            }
        )
        print(f"  ✓ Task started with ID: {task_id}")

        # Wait a bit and check status
        await asyncio.sleep(2)
        status = manager.get_task_status(task_id)
        print(f"  Task status: {status}")

    except Exception as e:
        print(f"  ✗ Task start failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Debug Test Completed")
    print("=" * 60)


async def test_basic_components():
    """Test basic component imports and functionality."""
    print("\n" + "=" * 60)
    print("Testing Basic Components")
    print("=" * 60)

    # Test base crawler
    print("\n[1] Testing base_crawler...")
    try:
        from services.mediacrawler.base_crawler import AbstractCrawler, AbstractApiClient, AbstractLogin, AbstractStore
        print("  ✓ base_crawler imports successful")
    except Exception as e:
        print(f"  ✗ base_crawler import failed: {e}")

    # Test utils
    print("\n[2] Testing utils...")
    try:
        from services.mediacrawler.utils import convert_cookies, logger, get_user_agent
        print("  ✓ utils imports successful")
    except Exception as e:
        print(f"  ✗ utils import failed: {e}")

    # Test config
    print("\n[3] Testing config...")
    try:
        from services.mediacrawler.config import CrawlerConfig, get_config
        config = CrawlerConfig()
        print(f"  ✓ config imports successful, default platform: {config.PLATFORM}")
    except Exception as e:
        print(f"  ✗ config import failed: {e}")

    # Test store
    print("\n[4] Testing store...")
    try:
        from services.mediacrawler.store import get_store, JsonStore, MemoryStore
        store = get_store("xhs", "memory")
        print(f"  ✓ store imports successful, store type: {type(store)}")
    except Exception as e:
        print(f"  ✗ store import failed: {e}")

    # Test individual platform imports
    print("\n[5] Testing platform imports...")
    platforms = ["xhs", "douyin", "bilibili", "weibo", "zhihu", "kuaishou", "tieba"]
    for platform in platforms:
        try:
            module = __import__(
                f"services.mediacrawler.platforms.{platform}",
                fromlist=[""]
            )
            print(f"  ✓ {platform} module imported")
        except ImportError as e:
            print(f"  ✗ {platform} import failed: {e}")


def main():
    """Main entry point."""
    print("\n" + "#" * 70)
    print("# Crawler Debug Test - 伊朗与以色列为敌")
    print("#" * 70)

    # First run basic component tests
    asyncio.run(test_basic_components())

    # Then run the full flow test
    asyncio.run(test_crawler_flow())


if __name__ == "__main__":
    main()