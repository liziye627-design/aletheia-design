import { expect, Page, test } from '@playwright/test'

type JsonRecord = Record<string, unknown>

function buildRunResult(runId: string): JsonRecord {
  return {
    run_id: runId,
    status: 'completed',
    duration_sec: 2.4,
    search: { keyword: '测试主张' },
    latest_related_content_at: '2026-03-01T10:00:00.000Z',
    risk_flags: ['NEEDS_REVIEW'],
    acquisition_report: {
      external_evidence_count: 6,
      external_primary_count: 3,
      external_background_count: 3,
    },
    claim_analysis: {
      run_verdict: 'UNCERTAIN',
      review_queue: [{ claim_id: 'c1', reasons: ['INSUFFICIENT_EVIDENCE'] }],
      claims: [
        {
          claim_id: 'c1',
          text: '测试主张',
          verdict: 'UNCERTAIN',
          score: 0.42,
          gate_passed: false,
          gate_reasons: ['INSUFFICIENT_EVIDENCE'],
          linked_evidence: [{ url: 'https://example.com/e1' }],
        },
      ],
      claim_reasoning: [
        {
          claim_id: 'c1',
          claim_text: '测试主张',
          conclusion_text: '证据不足',
          citations: [
            {
              url: 'https://example.com/e1',
              platform: 'news',
              tier: 'T1',
              published_at: '2026-03-01T09:00:00.000Z',
              snippet: '示例引用',
            },
          ],
        },
      ],
    },
    opinion_monitoring: {
      risk_level: 'high',
      suspicious_ratio: 0.4,
      real_comment_ratio: 0.3,
      anomaly_tags: ['BURST_PATTERN'],
      sample_comments: [{ text: '异常传播样本', platform: 'weibo', url: 'https://example.com/c1' }],
    },
    step_summaries: [
      { step_id: 'intent_preview', status: 'success', summary: '已完成预分析' },
      { step_id: 'multiplatform_search', status: 'partial', summary: '证据存在缺口' },
      { step_id: 'claim_analysis', status: 'success', summary: '主张已判定 UNCERTAIN' },
    ],
  }
}

function buildSseBody(runId: string): string {
  const rows = [
    { id: '1', event: 'step_update', data: { step_id: 'intent_preview', status: 'success' } },
    { id: '2', event: 'step_update', data: { step_id: 'multiplatform_search', status: 'partial' } },
    { id: '3', event: 'step_update', data: { step_id: 'claim_analysis', status: 'success' } },
    { id: '4', event: 'run_completed', data: { run_id: runId, status: 'completed' } },
  ]
  return rows.map((r) => `id: ${r.id}\nevent: ${r.event}\ndata: ${JSON.stringify(r.data)}\n`).join('\n')
}

async function installProgramUiMocks(page: Page, runId: string): Promise<void> {
  const result = buildRunResult(runId)

  await page.route(/\/api\/v1\/reports\/\?page=\d+&page_size=\d+/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 'r1',
            title: '历史报告-测试',
            summary: 'mock',
            content_html: '<p>mock</p>',
            credibility_score: 0.42,
            status: 'completed',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            sources: [],
            tags: [`run_${runId}`],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        has_more: false,
      }),
    })
  })

  await page.route('**/api/v1/reports/r1', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'r1',
        title: '历史报告-测试',
        summary: 'mock',
        content_html: '<p>mock</p>',
        credibility_score: 0.42,
        status: 'completed',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        sources: [],
        tags: [`run_${runId}`],
      }),
    })
  })

  await page.route('**/api/v1/investigations/preview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        preview_id: 'p1',
        status: 'ready',
        intent_summary: 'mock preview done',
        event_type: 'rumor',
        domain: 'public',
        claims_draft: [{ claim_id: 'c1', text: '测试主张', type: 'fact', confidence: 0.8, editable: true }],
        source_plan: {},
        risk_notes: ['需要补证'],
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
      }),
    })
  })

  await page.route('**/api/v1/investigations/run', async (route) => {
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        run_id: runId,
        accepted_at: new Date().toISOString(),
        initial_status: 'queued',
      }),
    })
  })

  await page.route(`**/api/v1/investigations/${runId}/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
      body: buildSseBody(runId),
    })
  })

  await page.route(`**/api/v1/investigations/${runId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(result),
    })
  })
}

test('program flow triggers review gate and my workspace replay', async ({ page }) => {
  const runId = 'run_ui_e2e_1'
  await installProgramUiMocks(page, runId)

  await page.goto('/')
  await page.getByTestId('claim-input').fill('这是一条待核查主张')
  await page.getByTestId('start-run').click()
  await expect(page.getByText('预分析确认')).toBeVisible()
  await page.locator('.confirm-check input[type="checkbox"]').check()
  await page.getByRole('button', { name: '确认并继续' }).click()

  await page.getByRole('button', { name: '任务管理' }).click()
  await expect(page.getByText('需人工复核')).toBeVisible({ timeout: 10000 })
  await expect(page.getByRole('heading', { name: '结论阶段' })).toBeVisible()

  await page.getByRole('button', { name: '历史档案' }).click()
  await expect(page.getByRole('heading', { name: '我的待办' })).toBeVisible()
  await expect(page.getByText('历史报告-测试')).toBeVisible()
  await expect(page.getByText('运行结论：UNCERTAIN')).toBeVisible()

  await page.getByRole('button', { name: '历史报告-测试' }).click()
  await expect(page.getByText('已完成预分析')).toBeVisible()
})
