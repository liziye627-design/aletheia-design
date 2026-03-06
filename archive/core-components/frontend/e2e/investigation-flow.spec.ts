import { expect, Page, test } from "@playwright/test";

type JsonRecord = Record<string, unknown>;

function buildMockResult(runId: string): JsonRecord {
  return {
    run_id: runId,
    status: "insufficient_evidence",
    request: {
      claim: "openal出版gpt5.3模型",
      keyword: "openal出版gpt5.3模型",
    },
    search: {
      keyword: "openal出版gpt5.3模型",
      data: {
        news: [
          {
            title: "网传信息未获权威证实",
            content: "多平台未发现官方发布信息",
            author: "system",
          },
        ],
      },
    },
    steps: [
      { id: "enhanced_reasoning", status: "success" },
      { id: "multiplatform_search", status: "success" },
      { id: "cross_platform_credibility", status: "success" },
      { id: "multi_agent", status: "success" },
      { id: "report_template_render", status: "success" },
    ],
    enhanced: {
      reasoning_chain: {
        final_score: 0.35,
        final_level: "LIKELY_FALSE",
        risk_flags: ["UNVERIFIED_CLAIM", "LOW_CREDIBILITY_SOURCE"],
        steps: [
          {
            stage: "preprocessing",
            reasoning: "提取主张中的实体、动作与时间约束。",
            conclusion: "识别到一个核心主张。",
            evidence: ["原文提取", "关键词识别"],
            concerns: [],
          },
          {
            stage: "cross_validation",
            reasoning: "交叉检索官方来源与权威媒体来源。",
            conclusion: "缺乏可回溯具体内容页。",
            evidence: ["官方来源检索未命中", "第三方权威媒体未证实"],
            concerns: ["需要补证"],
          },
        ],
      },
    },
    credibility: {
      credibility_score: 0.32,
      anomalies: [
        {
          type: "spread_pattern",
          description: "传播链条集中在重复转发，原创证据稀少。",
        },
      ],
    },
    agent_outputs: {
      recommendation: "证据不足，建议补充官方来源后复核。",
      consensus_points: ["缺乏官方证据", "来源相关性偏低"],
      conflicts: ["是否存在未公开内部版本"],
      overall_credibility: 0.28,
      platform_results: {
        news: {
          small_model_analysis: {
            credibility_score: 0.3,
            risk_flags: ["NO_DATA"],
          },
        },
      },
      generated_article: {
        title: "openal出版gpt5.3模型 核验简报",
        lead: "当前证据链不足以支撑高置信结论。",
        body_markdown: "建议增加官方站点检索与时间窗扩展。",
        highlights: ["证据不足", "需补证"],
        insufficient_evidence: ["缺少可回溯链接"],
      },
    },
    evidence_registry: [
      {
        id: "ev_1",
        source_tier: 1,
        source_name: "openai_release_notes",
        snippet: "未检索到 GPT 5.3 官方发布记录",
        stance: "refute",
        confidence: 0.82,
        validation_status: "reachable",
      },
      {
        id: "ev_2",
        source_tier: 3,
        source_name: "news",
        snippet: "非权威转载内容，未给出可追溯出处",
        stance: "context",
        confidence: 0.55,
        validation_status: "raw",
      },
    ],
    score_breakdown: {
      platform_coverage_score: 0.4,
      evidence_specificity_score: 0.2,
      model_consensus_score: 0.33,
      synthesis_score: 0.28,
      evidence_count: 2,
    },
    dual_profile_result: {
      tob_result: { score: 0.35, level: "LIKELY_FALSE" },
      tog_result: { score: 0.31, level: "LIKELY_FALSE" },
      combined_result: { score: 0.33, level: "LIKELY_FALSE" },
    },
    report_sections: [
      {
        id: "summary",
        title: "执行摘要",
        content_markdown: "关键词：openal出版gpt5.3模型",
        evidence_ids: ["ev_1"],
      },
      {
        id: "evidence",
        title: "证据链",
        content_markdown: "- [openai_release_notes] 未检索到官方发布记录",
        evidence_ids: ["ev_1", "ev_2"],
      },
    ],
    no_data_explainer: {
      reason_code: "INSUFFICIENT_EVIDENCE",
      attempted_platforms: ["news", "xinhua", "openai_release_notes"],
      retrieval_scope: {
        total_platforms: 3,
        platforms_with_data: 1,
        total_items: 4,
        specific_items: 0,
      },
      coverage_ratio: 0,
      next_queries: [
        "openal出版gpt5.3模型",
        "openal出版gpt5.3模型 官方 声明",
        "openal出版gpt5.3模型 site:openai.com",
      ],
    },
  };
}

function buildSseBody(runId: string): string {
  const rows = [
    {
      id: "1",
      event: "run_started",
      data: { run_id: runId },
    },
    {
      id: "2",
      event: "step_update",
      data: { step_id: "enhanced_reasoning", status: "running" },
    },
    {
      id: "3",
      event: "step_update",
      data: { step_id: "enhanced_reasoning", status: "success" },
    },
    {
      id: "4",
      event: "run_completed",
      data: { run_id: runId, status: "insufficient_evidence" },
    },
  ];

  return rows
    .map((r) => `id: ${r.id}\nevent: ${r.event}\ndata: ${JSON.stringify(r.data)}\n`)
    .join("\n");
}

async function installMockInvestigationApi(
  page: Page,
  runId: string,
  result: JsonRecord,
  onExportPayload?: (payload: JsonRecord) => void
): Promise<void> {
  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "healthy", version: "1.0.0" }),
    });
  });

  await page.route(/\/api\/v1\/reports\/\?page=\d+&page_size=\d+/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        has_more: false,
      }),
    });
  });

  await page.route("**/api/v1/investigations/run", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        accepted_at: new Date().toISOString(),
        initial_status: "queued",
      }),
    });
  });

  await page.route(`**/api/v1/investigations/${runId}/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
      body: buildSseBody(runId),
    });
  });

  await page.route(`**/api/v1/investigations/${runId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(result),
    });
  });

  await page.route("**/api/v1/reports/generate-from-run", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "report_mock",
        title: "mock",
        summary: "mock",
        content_html: "<p>mock</p>",
        credibility_score: 0.33,
        status: "insufficient_evidence",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        sources: [],
        tags: [],
      }),
    });
  });

  await page.route("**/api/v1/reports/export", async (route) => {
    const payload = (route.request().postDataJSON() as JsonRecord) || {};
    onExportPayload?.(payload);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        file_name: "mock.md",
        mime_type: "text/markdown; charset=utf-8",
        content_base64: "IyBNb2NrIFJlcG9ydAo=",
      }),
    });
  });
}

test("first step event appears within 5s", async ({ page }) => {
  const runId = "run_mock_first_step";
  await installMockInvestigationApi(page, runId, buildMockResult(runId));

  await page.goto("/");
  await page.fill("#claimInput", `mock-first-step-${Date.now()}`);

  const start = Date.now();
  await page.click("#runButton");

  await expect(
    page.locator('.timeline-step[data-status="running"], .timeline-step[data-status="success"]').first()
  ).toBeVisible({ timeout: 5000 });

  const elapsed = Date.now() - start;
  expect(elapsed).toBeLessThanOrEqual(5000);
});

test("live backend: run accepted and stream endpoint reachable", async ({ page }) => {
  test.skip(process.env.E2E_LIVE !== "1", "Set E2E_LIVE=1 to run backend-integrated smoke");

  await page.goto("/");
  await page.fill("#claimInput", `live-e2e-${Date.now()}-gpt5.3`);

  const streamResponsePromise = page.waitForResponse(
    (res) =>
      res.url().includes("/api/v1/investigations/") &&
      res.url().endsWith("/stream") &&
      res.status() === 200,
    { timeout: 30_000 }
  );

  await page.click("#runButton");

  await expect(page.locator("#runStatus")).toContainText("运行中", { timeout: 10_000 });
  const streamResponse = await streamResponsePromise;
  expect(streamResponse.status()).toBe(200);
});

test("insufficient-evidence panel and step details render", async ({ page }) => {
  const runId = "run_mock_insufficient";
  await installMockInvestigationApi(page, runId, buildMockResult(runId));

  await page.goto("/");
  await page.fill("#claimInput", "mock claim");
  await page.click("#runButton");

  await expect(page.locator("#runStatus")).toContainText("完成");

  await page.click('button[data-tab="report"]');
  await expect(page.locator("#noDataPanel.show")).toBeVisible();
  await expect(page.locator("#noDataPanel")).toContainText("检索平台");
  await expect(page.locator("#noDataPanel")).toContainText("官方 声明");

  const firstStep = page.locator(".step-detail").first();
  await firstStep.locator("summary").click();
  await expect(firstStep).toContainText("推理：");
  await expect(firstStep).toContainText("证据：");
});

test("export request contains section markdown and evidence trace", async ({ page }) => {
  const runId = "run_mock_export";
  let exportPayload: JsonRecord | undefined;
  await installMockInvestigationApi(
    page,
    runId,
    buildMockResult(runId),
    (payload) => {
      exportPayload = payload;
    }
  );

  await page.goto("/");
  await page.fill("#claimInput", "mock export claim");
  await page.click("#runButton");
  await expect(page.locator("#runStatus")).toContainText("完成");

  await page.click('button[data-tab="report"]');
  await page.click("#exportMd");

  await expect.poll(() => Boolean(exportPayload), { timeout: 5000 }).toBeTruthy();
  expect(exportPayload?.format).toBe("md");

  const payload = (exportPayload?.payload as JsonRecord) || {};
  expect(String(payload.content || "")).toContain("## 执行摘要");
  expect(String(payload.content || "")).toContain("## 证据卡片");
  expect(Array.isArray(payload.evidence_registry)).toBeTruthy();
  expect(((payload.evidence_registry as unknown[]) || []).length).toBeGreaterThan(0);
});
