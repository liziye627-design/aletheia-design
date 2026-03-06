import { chromium } from "@playwright/test";

const BASE_URL = process.env.LIVE_BASE_URL || "http://127.0.0.1:5173";

function nowStamp() {
  const d = new Date();
  const s = `${d.getHours()}`.padStart(2, "0")
    + `${d.getMinutes()}`.padStart(2, "0")
    + `${d.getSeconds()}`.padStart(2, "0");
  return s;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  page.on("console", (msg) => {
    console.log(`BROWSER_${msg.type()}:${msg.text()}`);
  });
  page.on("pageerror", (err) => {
    console.log(`PAGEERROR:${err?.message || err}`);
  });
  const claimText = `请核验 WHO 今日是否发布新的全球卫生倡议（live-${Date.now()}）`;
  const keyword = "WHO global health initiative";

  try {
    await page.goto(BASE_URL, { waitUntil: "networkidle", timeout: 60_000 });
    await page.fill("#claimInput", claimText);
    await page.fill("#keywordInput", keyword);
    const injected = await page.evaluate(() => ({
      claimLen: (document.querySelector("#claimInput")?.value || "").length,
      runStatus: (document.querySelector("#runStatus")?.textContent || "").trim(),
    }));
    console.log(`LIVE_PRECHECK:${JSON.stringify(injected)}`);
    await page.dispatchEvent("#runButton", "click");

    let finalStatus = "";
    for (let i = 0; i < 35; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      finalStatus = await page.evaluate(() => {
        const el = document.querySelector("#runStatus");
        return (el?.textContent || "").trim();
      });
      console.log(`LIVE_STATUS_TICK:${i}:${finalStatus}`);
      if (finalStatus.includes("完成") || finalStatus.includes("失败")) break;
      // eslint-disable-next-line no-await-in-loop
      await page.waitForTimeout(3_000);
    }
    if (!finalStatus.includes("完成") && !finalStatus.includes("失败")) {
      throw new Error(`run status timeout, current=${finalStatus}`);
    }

    const verifyShot = `test-results/live-verify-${nowStamp()}.png`;
    await page.screenshot({ path: verifyShot, fullPage: true });

    await page.click('[data-tab="report"]');
    await page.waitForSelector("#claimGraphPanel", { timeout: 30_000 });
    await page.waitForTimeout(1_800);

    const claimCards = page.locator("#claimGraphPanel .claim-card");
    const claimCount = await claimCards.count();
    if (claimCount > 0) {
      await claimCards.first().click();
      await page.waitForTimeout(500);
    }

    const reportShot = `test-results/live-report-${nowStamp()}.png`;
    await page.screenshot({ path: reportShot, fullPage: true });

    const summary = await page.evaluate(() => {
      const text = (selector) => (document.querySelector(selector)?.textContent || "").trim();
      const claims = Array.from(document.querySelectorAll("#claimGraphPanel .claim-card")).map((node) =>
        (node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 240)
      );
      const queue = Array.from(document.querySelectorAll("#reviewQueuePanel .review-item")).map((node) =>
        (node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 180)
      );
      const traces = Array.from(document.querySelectorAll("#evidenceTracePanel .trace-item")).map((node) =>
        (node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 180)
      );
      const stepSummaries = Array.from(document.querySelectorAll("#stepSummaryPanel .step-summary-card")).map((node) =>
        (node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 220)
      );
      return {
        run_status: text("#runStatus"),
        backend_status: text("#backendStatus"),
        report_header: text("#reportContent h2"),
        claim_count: claims.length,
        review_count: queue.length,
        trace_count: traces.length,
        step_summary_count: stepSummaries.length,
        first_claim: claims[0] || null,
        first_review: queue[0] || null,
        first_trace: traces[0] || null,
        first_step_summary: stepSummaries[0] || null,
      };
    });

    console.log(
      `LIVE_RESULT:${JSON.stringify(
        {
          base_url: BASE_URL,
          claim: claimText,
          keyword,
          screenshots: [verifyShot, reportShot],
          summary,
        },
        null,
        2
      )}`
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(`LIVE_RESULT_ERROR:${error?.stack || error}`);
  process.exit(1);
});
