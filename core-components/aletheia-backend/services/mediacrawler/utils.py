# -*- coding: utf-8 -*-
"""
MediaCrawler Utility Functions.
"""

import asyncio
import base64
import logging
import random
import string
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, parse_qs

try:
    from PIL import Image
except ImportError:
    Image = None


# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mediacrawler")


def convert_cookies(cookies: List[Dict]) -> Tuple[str, Dict[str, str]]:
    """
    Convert cookie list to string and dict formats.

    Args:
        cookies: List of cookie dictionaries from browser

    Returns:
        Tuple of (cookie_string, cookie_dict)
    """
    cookie_str = ""
    cookie_dict = {}
    for cookie in cookies:
        cookie_dict[cookie.get("name", "")] = cookie.get("value", "")
        cookie_str += f"{cookie.get('name')}={cookie.get('value')}; "
    return cookie_str.rstrip("; "), cookie_dict


def convert_str_cookie_to_dict(cookie_str: str) -> Dict[str, str]:
    """
    Convert cookie string to dictionary.

    Args:
        cookie_str: Cookie string like "name1=value1; name2=value2"

    Returns:
        Dictionary of cookie name-value pairs
    """
    cookie_dict = {}
    if not cookie_str:
        return cookie_dict
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookie_dict[name.strip()] = value.strip()
    return cookie_dict


def format_proxy_info(proxy_info: Any) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Format proxy info for playwright and httpx.

    Args:
        proxy_info: Proxy information object

    Returns:
        Tuple of (playwright_proxy, httpx_proxy)
    """
    if proxy_info is None:
        return None, None

    # Handle different proxy info formats
    if hasattr(proxy_info, 'ip') and hasattr(proxy_info, 'port'):
        host = proxy_info.ip
        port = proxy_info.port
        protocol = getattr(proxy_info, 'protocol', 'http')
        username = getattr(proxy_info, 'username', None)
        password = getattr(proxy_info, 'password', None)

        if username and password:
            proxy_url = f"{protocol}://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"{protocol}://{host}:{port}"

        playwright_proxy = {"server": proxy_url}
        return playwright_proxy, proxy_url

    return None, None


def get_user_agent() -> str:
    """Get a random user agent string."""
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    ]
    return random.choice(user_agents)


async def find_login_qrcode(page, selector: str) -> Optional[str]:
    """
    Find and extract QR code image from page.

    Args:
        page: Playwright page object
        selector: CSS selector for QR code image

    Returns:
        Base64 encoded QR code image or None
    """
    try:
        qrcode_element = await page.wait_for_selector(selector, timeout=5000)
        if qrcode_element:
            # Get the src attribute
            src = await qrcode_element.get_attribute("src")
            if src:
                # If it's a data URL, extract the base64 part
                if src.startswith("data:image"):
                    return src.split(",")[1] if "," in src else src
                # Otherwise, fetch the image
                return src
    except Exception as e:
        logger.error(f"[find_login_qrcode] Error finding QR code: {e}")
    return None


def show_qrcode(base64_image: str):
    """
    Display QR code in terminal (requires terminal image support).

    Args:
        base64_image: Base64 encoded QR code image
    """
    try:
        if Image is None:
            logger.info("[show_qrcode] PIL not installed, cannot display QR code")
            print(f"QR Code data: {base64_image[:100]}...")
            return

        # Decode base64 image
        image_data = base64.b64decode(base64_image)
        image = Image.open(BytesIO(image_data))

        # Try to show in terminal
        try:
            from terminal_image import display
            display(image)
        except ImportError:
            # Fallback: save to file
            qrcode_path = "qrcode.png"
            image.save(qrcode_path)
            logger.info(f"[show_qrcode] QR code saved to {qrcode_path}")
            print(f"Please scan the QR code saved to: {qrcode_path}")

    except Exception as e:
        logger.error(f"[show_qrcode] Error displaying QR code: {e}")


def extract_url_params_to_dict(url: str) -> Dict[str, str]:
    """
    Extract URL query parameters to dictionary.

    Args:
        url: URL string

    Returns:
        Dictionary of query parameters
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {k: v[0] if len(v) == 1 else v for k, v in params.items()}


def generate_random_string(length: int = 16) -> str:
    """Generate a random string of specified length."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


async def retry_async(func, max_retries: int = 3, delay: float = 1.0, *args, **kwargs):
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function call

    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                await asyncio.sleep(delay * (2 ** attempt))
    raise last_exception


class AsyncContextManager:
    """Base class for async context managers."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self):
        pass