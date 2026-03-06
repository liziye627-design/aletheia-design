import subprocess
from pathlib import Path


PROJECT_ROOT = Path("/home/llwxy/aletheia/design/frontend")
OUTPUT_PATH = PROJECT_ROOT / "ui-current.png"


def main():
    script = f"""
import {{ chromium }} from '@playwright/test';

const browser = await chromium.launch({{ headless: true }});
const page = await browser.newPage({{ viewport: {{ width: 1366, height: 860 }} }});
await page.goto('http://localhost:5173', {{ waitUntil: 'networkidle' }});
await page.waitForTimeout(1000);
await page.screenshot({{ path: '{OUTPUT_PATH}', fullPage: true }});
await browser.close();
"""
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=PROJECT_ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
