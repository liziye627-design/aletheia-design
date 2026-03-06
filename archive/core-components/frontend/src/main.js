const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const HEALTH_URL = (() => {
  try {
    return `${new URL(API_BASE).origin}/health`;
  } catch (_error) {
    return "http://localhost:8000/health";
  }
})();

const claimInput = document.getElementById("claimInput");
const keywordInput = document.getElementById("keywordInput");
const sourceUrlInput = document.getElementById("sourceUrlInput");
const platformSelect = document.getElementById("platformSelect");
const runButton = document.getElementById("runButton");
const previewPanel = document.getElementById("previewPanel");
const previewStatusBadge = document.getElementById("previewStatusBadge");
const previewIntentSummary = document.getElementById("previewIntentSummary");
const previewFallbackReason = document.getElementById("previewFallbackReason");
const previewClaimsEditor = document.getElementById("previewClaimsEditor");
const previewPlatformsEditor = document.getElementById("previewPlatformsEditor");
const previewRiskList = document.getElementById("previewRiskList");
const previewRefreshButton = document.getElementById("previewRefreshButton");
const previewConfirmButton = document.getElementById("previewConfirmButton");
const runStatus = document.getElementById("runStatus");
const backendStatus = document.getElementById("backendStatus");
const streamPanel = document.getElementById("streamPanel");
const toolsMenu = document.getElementById("toolsMenu");
const toggleTools = document.getElementById("toggleTools");
const selectedMode = document.getElementById("selectedMode");
const modeBadge = document.getElementById("modeBadge");
const modeButtons = Array.from(document.querySelectorAll(".menu-item"));
const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
const tabPanes = Array.from(document.querySelectorAll(".tab-pane"));
const stepTimeline = document.getElementById("stepTimeline");
const workflowTree = document.getElementById("workflowTree");
const workflowTreeDetail = document.getElementById("workflowTreeDetail");
const reportContent = document.getElementById("reportContent");
const reportList = document.getElementById("reportList");
const myTodoPanel = document.getElementById("myTodoPanel");
const myArticleSuggestionPanel = document.getElementById("myArticleSuggestionPanel");
const sourcePlanPanel = document.getElementById("sourcePlanPanel");
const failureImpactPanel = document.getElementById("failureImpactPanel");
const railSearchPanel = document.getElementById("railSearchPanel");
const railMetricsPanel = document.getElementById("railMetricsPanel");
const noDataPanel = document.getElementById("noDataPanel");
const evidenceCards = document.getElementById("evidenceCards");
const claimReasoningPanel = document.getElementById("claimReasoningPanel");
const opinionRiskPanel = document.getElementById("opinionRiskPanel");
const claimGraphPanel = document.getElementById("claimGraphPanel");
const evidenceTracePanel = document.getElementById("evidenceTracePanel");
const reviewQueuePanel = document.getElementById("reviewQueuePanel");
const stepSummaryPanel = document.getElementById("stepSummaryPanel");
const evidencePlatformFilter = document.getElementById("evidencePlatformFilter");
const evidenceStanceFilter = document.getElementById("evidenceStanceFilter");
const evidenceTierFilter = document.getElementById("evidenceTierFilter");
const evidenceOriginFilter = document.getElementById("evidenceOriginFilter");
const evidenceClassFilter = document.getElementById("evidenceClassFilter");
const feedList = document.getElementById("feedList");
const agentSummary = document.getElementById("agentSummary");
const agentPanel = document.getElementById("agentPanel");
const mermaidBox = document.getElementById("mermaidBox");
const scoreCanvas = document.getElementById("scoreCanvas");
const breakdownBox = document.getElementById("breakdownBox");
const anomalySummary = document.getElementById("anomalySummary");
const exportMd = document.getElementById("exportMd");
const exportJson = document.getElementById("exportJson");
const toggleDebug = document.getElementById("toggleDebug");
const debugDrawer = document.getElementById("debugDrawer");
const debugLog = document.getElementById("debugLog");

let currentMode = "dual";
let currentRun = null;
let currentNarrative = "";
let currentReportPayload = null;
let mermaidLoaded = false;
let activeEventSource = null;
let currentVotes = [];
let currentStepState = {};
let currentEvidenceRegistry = [];
let currentEvidenceEventCount = 0;
let currentSegmentCard = null;
let currentSegmentState = null;
let currentRenderedExtract = null;
let currentStepSummaries = [];
let currentReportItems = [];
let activeReportId = "";
let currentSourcePlan = {
  event_type: "generic_claim",
  domain: "general_news",
  domain_keywords: [],
  plan_version: "manual_default",
  selection_confidence: 0,
  must_have_platforms: [],
  candidate_platforms: [],
  excluded_platforms: [],
  selected_platforms: [],
  official_floor_platforms: [],
  official_selected_platforms: [],
  official_selected_count: 0,
  selection_reasons: [],
  risk_notes: [],
};
let currentAcquisitionReport = null;
let currentPlatformStatusMap = {};
let currentMediaCrawlerStatus = {
  enabled: false,
  enabled_by_request: null,
  ack: false,
  platforms: [],
  timeout_sec: 120,
};
let currentMediaCrawlerPlatformMap = {};
let currentPreview = null;
let currentPreviewState = {
  status: "pending",
  detail: "等待预分析",
};
let pendingExecutionContext = null;
let currentOpinionMonitoring = {
  status: "NOT_RUN",
  discovery_mode: "reuse_search_results",
  synthetic_comment_mode: false,
  comment_target: 120,
  total_comments: 0,
  real_comment_count: 0,
  synthetic_comment_count: 0,
  sidecar_comment_count: 0,
  sidecar_failures: [],
  real_comment_ratio: 0,
  real_comment_target_reached: false,
  unique_accounts_count: 0,
  suspicious_accounts_count: 0,
  suspicious_ratio: 0,
  risk_level: "unknown",
  risk_flags: [],
  comment_target_reached: false,
  top_suspicious_accounts: [],
  sample_comments: [],
  summary_text: "评论监测尚未执行。",
};
let runInProgress = false;
let previewInProgress = false;
let healthPollTimer = null;
let reportsPollTimer = null;
let currentClaimAnalysis = {
  claims: [],
  review_queue: [],
  claim_reasoning: [],
  matrix_summary: { tier1_count: 0, tier2_count: 0, tier3_count: 0, tier4_count: 0 },
  run_verdict: "UNCERTAIN",
  summary: {},
};
let selectedClaimId = null;
let selectedWorkflowNodeId = "root";
let collapsedWorkflowNodeIds = new Set();
let workflowTreeNodes = {};
let workflowEventSeq = 0;
let debugLines = [];

const DEFAULT_RENDER_SCHEMA = {
  h1: { selector: "h1", mode: "text" },
  h2_list: { selector: "h2", mode: "text", many: true },
  links: { selector: "a[href]", mode: "attr", attr: "href", many: true },
};

const DEFAULT_STEPS = [
  "intent_preview",
  "source_planning",
  "enhanced_reasoning",
  "multiplatform_search",
  "cross_platform_credibility",
  "multi_agent",
  "external_sources",
  "claim_analysis",
  "opinion_monitoring",
  "report_template_render",
];

const EMPTY_CLAIM_ANALYSIS = {
  claims: [],
  review_queue: [],
  claim_reasoning: [],
  matrix_summary: { tier1_count: 0, tier2_count: 0, tier3_count: 0, tier4_count: 0 },
  run_verdict: "UNCERTAIN",
  summary: {},
};

const EMPTY_OPINION_MONITORING = {
  status: "NOT_RUN",
  discovery_mode: "reuse_search_results",
  synthetic_comment_mode: false,
  comment_target: 120,
  total_comments: 0,
  real_comment_count: 0,
  synthetic_comment_count: 0,
  sidecar_comment_count: 0,
  sidecar_failures: [],
  real_comment_ratio: 0,
  real_comment_target_reached: false,
  unique_accounts_count: 0,
  suspicious_accounts_count: 0,
  suspicious_ratio: 0,
  risk_level: "unknown",
  risk_flags: [],
  comment_target_reached: false,
  top_suspicious_accounts: [],
  sample_comments: [],
  summary_text: "评论监测尚未执行。",
};

const STEP_TITLE_MAP = {
  intent_preview: "输入意图预分析",
  source_planning: "自动选源规划",
  network_precheck: "网络预检",
  enhanced_reasoning: "增强推理",
  multiplatform_search: "多平台检索与过滤",
  cross_platform_credibility: "跨平台可信度评估",
  multi_agent: "多 Agent 综合",
  external_sources: "外部权威源校验",
  claim_analysis: "主张级判定",
  opinion_monitoring: "评论与水军风险监测",
  report_template_render: "报告模板渲染",
};

const WORKFLOW_CORE_NODE_IDS = ["root", "preview", "source", "search", "claim", "opinion", "report"];

function escapeHtml(input) {
  return String(input || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function inferEventRole(source, level) {
  if (source === "user" || level === "user") return "user";
  if (["system", "scheduler", "warning", "stream", "ui"].includes(source)) return "system";
  return "assistant";
}

function addEvent(source, message, level = "info", role = null) {
  if (!streamPanel) return;
  const wrapper = document.createElement("div");
  wrapper.className = `event role-${role || inferEventRole(source, level)}`;
  wrapper.dataset.level = level;
  wrapper.innerHTML = `
    <div class="meta">
      <span>${escapeHtml(source)}</span>
      <span>${new Date().toLocaleTimeString("zh-CN")}</span>
    </div>
    <div class="msg">${escapeHtml(message)}</div>
  `;
  streamPanel.appendChild(wrapper);
  streamPanel.scrollTop = streamPanel.scrollHeight;
}

function setStatus(text) {
  if (runStatus) runStatus.textContent = text;
}

function setBackendStatus(text) {
  if (backendStatus) backendStatus.textContent = text;
}

function getPlatforms() {
  if (platformSelect?.value === "all") {
    return [
      "xinhua",
      "news",
      "who",
      "cdc",
      "nhc",
      "un_news",
      "sec",
      "samr",
      "csrc",
      "fca_uk",
      "mem",
      "mps",
      "bbc",
      "guardian",
      "reuters",
      "ap_news",
      "bilibili",
      "zhihu",
      "douyin",
      "xiaohongshu",
      "weibo",
      "reddit",
    ];
  }
  // 稳定免费信源优先：官方源保底 + 主流媒体
  return [
    "xinhua",
    "news",
    "who",
    "un_news",
    "sec",
    "samr",
    "csrc",
    "nhc",
    "fca_uk",
    "mem",
    "mps",
    "bbc",
    "guardian",
    "reuters",
    "ap_news",
  ];
}

function deriveKeyword(content) {
  const normalized = content.trim().replace(/\s+/g, " ");
  if (!normalized) return "";
  if (normalized.length <= 24) return normalized;
  return normalized.slice(0, 24);
}

function isBroadKeyword(keyword) {
  const normalized = String(keyword || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
  if (!normalized) return true;
  if (normalized.length <= 14) return true;
  const tokens = normalized.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  return tokens.length <= 2;
}

function buildInvestigationTuning(keyword, platforms, sourceUrl) {
  const platformCount = Array.isArray(platforms) ? platforms.length : 0;
  const broad = isBroadKeyword(keyword);
  const hasUrl = Boolean(sourceUrl);

  const targetValidEvidenceMin = broad ? 60 : hasUrl ? 70 : 80;
  const liveEvidenceTarget = broad ? 20 : 25;
  const phase1Target = Math.max(30, Math.floor(targetValidEvidenceMin * 0.5));
  const minPlatformsWithData = Math.max(2, Math.min(6, Math.ceil(platformCount * 0.35)));

  return {
    target_valid_evidence_min: targetValidEvidenceMin,
    live_evidence_target: liveEvidenceTarget,
    phase1_target_valid_evidence: phase1Target,
    min_platforms_with_data: minPlatformsWithData,
    max_runtime_sec: broad ? 100 : 120,
    phase1_deadline_sec: broad ? 55 : 70,
    max_concurrent_platforms_fast: broad ? 8 : 6,
    max_concurrent_platforms_fill: broad ? 5 : 4,
  };
}

function normalizePreviewPayload(raw) {
  const sourcePlanRaw = raw?.source_plan && typeof raw.source_plan === "object" ? raw.source_plan : {};
  return {
    preview_id: String(raw?.preview_id || ""),
    status: String(raw?.status || "degraded"),
    intent_summary: String(raw?.intent_summary || ""),
    event_type: String(raw?.event_type || "generic_claim"),
    domain: String(raw?.domain || "general_news"),
    claims_draft: Array.isArray(raw?.claims_draft)
      ? raw.claims_draft.map((row, idx) => ({
          claim_id: String(row?.claim_id || `clm_${idx + 1}`),
          text: String(row?.text || ""),
          type: String(row?.type || "generic_claim"),
          confidence: Number(row?.confidence || 0),
          editable: row?.editable !== false,
        }))
      : [],
    source_plan: normalizeSourcePlan(sourcePlanRaw),
    risk_notes: Array.isArray(raw?.risk_notes) ? raw.risk_notes.map((x) => String(x)) : [],
    fallback_reason: raw?.fallback_reason ? String(raw.fallback_reason) : "",
    expires_at: String(raw?.expires_at || ""),
  };
}

function setPreviewStatus(status, detail = "") {
  const normalized = String(status || "pending");
  currentPreviewState = {
    status: normalized,
    detail: detail || currentPreviewState?.detail || "",
  };
  currentStepState.intent_preview = {
    ...(currentStepState.intent_preview || {}),
    status: normalizeWorkflowStatus(normalized),
  };
  renderStepTimeline();
  renderWorkflowTree();
}

function resetPreviewPanel() {
  if (previewPanel) previewPanel.classList.add("hidden");
  if (previewStatusBadge) {
    previewStatusBadge.textContent = "待开始";
    previewStatusBadge.classList.remove("ready", "degraded", "running");
  }
  if (previewIntentSummary) previewIntentSummary.textContent = "提交主张后将生成执行意图预览。";
  if (previewFallbackReason) {
    previewFallbackReason.classList.add("hidden");
    previewFallbackReason.textContent = "";
  }
  if (previewClaimsEditor) previewClaimsEditor.innerHTML = "";
  if (previewPlatformsEditor) previewPlatformsEditor.innerHTML = "";
  if (previewRiskList) previewRiskList.innerHTML = "<li>等待预分析...</li>";
  if (previewConfirmButton) previewConfirmButton.disabled = true;
}

function renderPreviewPanel(preview) {
  if (!previewPanel) return;
  previewPanel.classList.remove("hidden");
  if (previewStatusBadge) {
    previewStatusBadge.classList.remove("ready", "degraded", "running");
    const status = String(preview.status || "degraded");
    previewStatusBadge.classList.add(status === "ready" ? "ready" : status === "degraded" ? "degraded" : "running");
    previewStatusBadge.textContent = status === "ready" ? "预分析完成" : status === "degraded" ? "降级可执行" : "预分析中";
  }
  if (previewIntentSummary) {
    previewIntentSummary.textContent = preview.intent_summary || "预分析未返回摘要。";
  }
  if (previewFallbackReason) {
    if (preview.fallback_reason) {
      previewFallbackReason.classList.remove("hidden");
      previewFallbackReason.textContent = `降级原因：${preview.fallback_reason}`;
    } else {
      previewFallbackReason.classList.add("hidden");
      previewFallbackReason.textContent = "";
    }
  }

  if (previewClaimsEditor) {
    const claims = Array.isArray(preview.claims_draft) ? preview.claims_draft : [];
    if (!claims.length) {
      previewClaimsEditor.innerHTML = '<div class="empty-block">未生成主张草案，执行时将直接使用输入主张。</div>';
    } else {
      previewClaimsEditor.innerHTML = claims
        .map(
          (row, idx) => `
          <article class="preview-claim-item">
            <div class="preview-claim-meta">
              <span>${escapeHtml(row.claim_id || `clm_${idx + 1}`)} · ${escapeHtml(row.type || "generic_claim")}</span>
              <span>conf=${Math.round(Number(row.confidence || 0) * 100)}%</span>
            </div>
            <textarea class="preview-claim-textarea" data-claim-id="${escapeHtml(row.claim_id || "")}">${escapeHtml(row.text || "")}</textarea>
          </article>
        `
        )
        .join("");
    }
  }

  if (previewPlatformsEditor) {
    const sourcePlan = normalizeSourcePlan(preview.source_plan || {});
    const must = new Set(sourcePlan.must_have_platforms || []);
    const selected = new Set(sourcePlan.selected_platforms || []);
    const candidate = new Set(sourcePlan.candidate_platforms || []);
    const excluded = new Set(sourcePlan.excluded_platforms || []);
    const ordered = [];
    [sourcePlan.selected_platforms, sourcePlan.must_have_platforms, sourcePlan.candidate_platforms, sourcePlan.excluded_platforms].forEach((bucket) => {
      (bucket || []).forEach((p) => {
        const platform = String(p || "").trim();
        if (platform && !ordered.includes(platform)) ordered.push(platform);
      });
    });
    if (!ordered.length) {
      previewPlatformsEditor.innerHTML = '<div class="empty-block">未生成平台计划，将按默认平台组执行。</div>';
    } else {
      previewPlatformsEditor.innerHTML = `
        <div class="preview-platform-grid">
          ${ordered
            .map((platform) => {
              const role = must.has(platform)
                ? "must"
                : excluded.has(platform)
                  ? "excluded"
                  : candidate.has(platform)
                    ? "candidate"
                    : "selected";
              const checked = selected.has(platform) && !excluded.has(platform);
              return `
                <label class="preview-platform-chip ${escapeHtml(role)} ${checked ? "selected" : ""}">
                  <input type="checkbox" data-preview-platform="${escapeHtml(platform)}" ${checked ? "checked" : ""} ${excluded.has(platform) ? "disabled" : ""} />
                  <span>${escapeHtml(platform)}</span>
                  <span class="preview-chip-role">${escapeHtml(role)}</span>
                </label>
              `;
            })
            .join("")}
        </div>
      `;
    }
  }

  if (previewRiskList) {
    const risks = Array.isArray(preview.risk_notes) ? preview.risk_notes : [];
    previewRiskList.innerHTML = risks.length
      ? risks.map((risk) => `<li>${escapeHtml(risk)}</li>`).join("")
      : "<li>未检测到明显风险。</li>";
  }
  if (previewConfirmButton) {
    previewConfirmButton.disabled = false;
  }
}

function getConfirmedClaimsFromPreview() {
  if (!previewClaimsEditor) return [];
  const textareas = Array.from(previewClaimsEditor.querySelectorAll(".preview-claim-textarea"));
  const values = textareas
    .map((el) => (el instanceof HTMLTextAreaElement ? el.value.trim() : ""))
    .filter((text) => Boolean(text));
  return values;
}

function getConfirmedPlatformsFromPreview() {
  if (!previewPlatformsEditor) return [];
  const checkboxes = Array.from(previewPlatformsEditor.querySelectorAll("input[data-preview-platform]"));
  const selected = checkboxes
    .filter((el) => el instanceof HTMLInputElement && el.checked)
    .map((el) => (el instanceof HTMLInputElement ? String(el.dataset.previewPlatform || "").trim() : ""))
    .filter((x) => Boolean(x));
  const sourcePlan = normalizeSourcePlan(currentPreview?.source_plan || currentSourcePlan || {});
  const mustHave = Array.isArray(sourcePlan.must_have_platforms)
    ? sourcePlan.must_have_platforms.map((x) => String(x || "").trim()).filter(Boolean)
    : [];
  const officialFloor = Array.isArray(sourcePlan.official_floor_platforms)
    ? sourcePlan.official_floor_platforms.map((x) => String(x || "").trim()).filter(Boolean)
    : [];
  // 默认强制保留 must + 官方保底前两项，避免用户误操作把官方源全部取消。
  return [...new Set([...selected, ...mustHave, ...officialFloor.slice(0, 2)])];
}

function normalizeRenderedExtract(payload) {
  if (!payload || typeof payload !== "object") return null;
  if ("url" in payload && "visible_text" in payload) return payload;
  if ("data" in payload && payload.data && typeof payload.data === "object") return payload.data;
  return null;
}

function compactInlineText(text, maxLen = 220) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLen) return normalized;
  return `${normalized.slice(0, maxLen)}...`;
}

function summarizeRenderedFields(fields) {
  const entries = Object.entries(fields || {});
  if (!entries.length) return "未配置字段";
  return entries
    .slice(0, 6)
    .map(([name, value]) => {
      if (Array.isArray(value)) {
        const sample = value
          .slice(0, 3)
          .map((item) => compactInlineText(item, 48))
          .join(" | ");
        return `${name}(${value.length})=${sample || "[]"}${value.length > 3 ? " ..." : ""}`;
      }
      if (value && typeof value === "object") {
        return `${name}=${compactInlineText(JSON.stringify(value), 72)}`;
      }
      return `${name}=${compactInlineText(value, 72)}`;
    })
    .join("；");
}

function normalizeWorkflowStatus(status) {
  const key = String(status || "pending").toLowerCase();
  if (["success", "completed", "done", "ready"].includes(key)) return "success";
  if (["failed", "error", "timeout"].includes(key)) return "failed";
  if (["degraded", "blocked", "warning", "review_required", "uncertain", "partial", "insufficient_evidence"].includes(key))
    return "partial";
  if (["running", "in_progress"].includes(key)) return "running";
  return key || "pending";
}

function ensureWorkflowNode(nodeId, defaults = {}) {
  const id = String(nodeId || "").trim();
  if (!id) return null;
  if (!workflowTreeNodes[id]) {
    workflowTreeNodes[id] = {
      id,
      parentId: defaults.parentId ?? null,
      label: defaults.label || id,
      status: normalizeWorkflowStatus(defaults.status || "pending"),
      detail: String(defaults.detail || ""),
      children: [],
      payload: defaults.payload ?? null,
      nodeType: defaults.nodeType || "event",
      updatedAt: Date.now(),
    };
  }
  return workflowTreeNodes[id];
}

function linkWorkflowNode(parentId, childId) {
  const parent = ensureWorkflowNode(parentId, { nodeType: "container", status: "pending" });
  const child = ensureWorkflowNode(childId, { parentId, status: "pending" });
  if (!parent || !child || parent.id === child.id) return;

  if (child.parentId && workflowTreeNodes[child.parentId] && child.parentId !== parent.id) {
    workflowTreeNodes[child.parentId].children = workflowTreeNodes[child.parentId].children.filter((id) => id !== child.id);
  }
  child.parentId = parent.id;
  if (!parent.children.includes(child.id)) {
    parent.children.push(child.id);
  }
}

function upsertWorkflowNode(nodeId, patch = {}) {
  const node = ensureWorkflowNode(nodeId, patch);
  if (!node) return null;
  if (patch.label !== undefined) node.label = String(patch.label || node.label);
  if (patch.detail !== undefined) node.detail = String(patch.detail || "");
  if (patch.status !== undefined) node.status = normalizeWorkflowStatus(patch.status);
  if (patch.payload !== undefined) node.payload = patch.payload;
  if (patch.nodeType !== undefined) node.nodeType = patch.nodeType;
  node.updatedAt = Date.now();

  if (patch.parentId !== undefined) {
    if (patch.parentId) linkWorkflowNode(String(patch.parentId), node.id);
    else node.parentId = null;
  }
  return node;
}

function setWorkflowChildren(parentId, childIds) {
  const parent = ensureWorkflowNode(parentId, { status: "pending" });
  if (!parent) return;
  const next = [];
  (childIds || []).forEach((id) => {
    const childId = String(id || "").trim();
    if (!childId) return;
    linkWorkflowNode(parent.id, childId);
    if (!next.includes(childId)) next.push(childId);
  });
  parent.children = next;
}

function initWorkflowTreeState() {
  workflowTreeNodes = {};
  workflowEventSeq = 0;
  collapsedWorkflowNodeIds = new Set();
  upsertWorkflowNode("root", { label: "核验任务", status: "pending", detail: "等待任务创建...", nodeType: "core", parentId: null });
  upsertWorkflowNode("preview", { label: "输入意图预分析", status: "pending", detail: "等待预分析", nodeType: "core", parentId: "root" });
  upsertWorkflowNode("source", { label: "自动选源", status: "pending", detail: "等待选源", nodeType: "core", parentId: "root" });
  upsertWorkflowNode("search", { label: "证据获取", status: "pending", detail: "等待检索", nodeType: "core", parentId: "root" });
  upsertWorkflowNode("claim", { label: "主张分析", status: "pending", detail: "等待主张拆解", nodeType: "core", parentId: "root" });
  upsertWorkflowNode("opinion", { label: "舆情评论风险", status: "pending", detail: "等待评论链路", nodeType: "core", parentId: "root" });
  upsertWorkflowNode("report", { label: "报告渲染", status: "pending", detail: "等待报告生成", nodeType: "core", parentId: "root" });
  setWorkflowChildren("root", WORKFLOW_CORE_NODE_IDS.slice(1));
}

function syncWorkflowCoreNodes() {
  const previewStep = currentStepState.intent_preview || { status: "pending" };
  const sourceStep = currentStepState.source_planning || { status: "pending" };
  const searchStep = currentStepState.multiplatform_search || { status: "pending" };
  const claimStep = currentStepState.claim_analysis || { status: "pending" };
  const opinionStep = currentStepState.opinion_monitoring || { status: "pending" };
  const reportStep = currentStepState.report_template_render || { status: "pending" };
  const claims = currentClaimAnalysis.claims || [];
  const review = currentClaimAnalysis.review_queue || [];
  const opinion = normalizeOpinionMonitoring(currentOpinionMonitoring || {});
  const acquisition = normalizeAcquisitionReport(currentAcquisitionReport || {});
  const sidecarEnabled = Boolean(currentMediaCrawlerStatus?.enabled);

  upsertWorkflowNode("root", {
    label: "核验任务",
    status: currentRun?.status || (previewInProgress || currentPreview ? "running" : "pending"),
    detail: `run=${currentRun?.run_id || "pending"} · 结论=${currentClaimAnalysis.run_verdict || "UNCERTAIN"}`,
    parentId: null,
    nodeType: "core",
  });
  upsertWorkflowNode("preview", {
    label: "输入意图预分析",
    status: previewStep.status || currentPreviewState.status || "pending",
    detail: currentPreviewState.detail || "等待预分析",
    parentId: "root",
    nodeType: "core",
  });
  upsertWorkflowNode("source", {
    label: "自动选源",
    status: sourceStep.status || "pending",
    detail: `domain=${currentSourcePlan.domain} · 选源=${(currentSourcePlan.selected_platforms || []).length} · sidecar=${sidecarEnabled ? "on" : "off"}`,
    parentId: "root",
    nodeType: "core",
  });
  upsertWorkflowNode("search", {
    label: "证据获取",
    status: searchStep.status || "pending",
    detail: `external=${acquisition.external_evidence_count} · signal=${acquisition.external_primary_count + acquisition.external_background_count} · derived=${acquisition.derived_evidence_count} · native=${acquisition.native_live_count} · sidecar=${acquisition.mediacrawler_live_count}`,
    parentId: "root",
    nodeType: "core",
  });
  upsertWorkflowNode("claim", {
    label: "主张分析",
    status: claimStep.status || "pending",
    detail: `claims=${claims.length} · review=${review.length}`,
    parentId: "root",
    nodeType: "core",
  });
  upsertWorkflowNode("opinion", {
    label: "舆情评论风险",
    status: opinionStep.status || "pending",
    detail: `comments=${opinion.total_comments} · suspicious=${Math.round(opinion.suspicious_ratio * 100)}% · ${String(opinion.risk_level || "unknown").toUpperCase()}`,
    parentId: "root",
    nodeType: "core",
  });
  upsertWorkflowNode("report", {
    label: "报告渲染",
    status: reportStep.status || "pending",
    detail: `step summaries=${(currentStepSummaries || []).length}`,
    parentId: "root",
    nodeType: "core",
  });
  setWorkflowChildren("root", WORKFLOW_CORE_NODE_IDS.slice(1));
}

function getWorkflowStageForStep(stepId) {
  const key = String(stepId || "");
  if (!key) return "search";
  if (key === "intent_preview") return "preview";
  if (key === "source_planning") return "source";
  if (key === "claim_analysis") return "claim";
  if (key === "opinion_monitoring") return "opinion";
  if (key === "report_template_render") return "report";
  return "search";
}

function upsertWorkflowStepNode(stepId, status, elapsedMs = 0) {
  if (!stepId) return;
  const parentId = getWorkflowStageForStep(stepId);
  const title = STEP_TITLE_MAP[stepId] || stepId.replaceAll("_", " ");
  const elapsedSec = Number(elapsedMs || 0) > 0 ? ` · ${(Number(elapsedMs) / 1000).toFixed(1)}s` : "";
  upsertWorkflowNode(`step-${stepId}`, {
    parentId,
    label: title,
    status: status || "running",
    detail: `${status || "running"}${elapsedSec}`,
    payload: { step_id: stepId, elapsed_ms: Number(elapsedMs || 0) },
    nodeType: "step",
  });
}

function flattenWorkflowNodes(rootId = "root") {
  const rows = [];
  const seen = new Set();

  const visit = (nodeId, depth) => {
    const node = workflowTreeNodes[nodeId];
    if (!node || seen.has(nodeId)) return;
    seen.add(nodeId);
    rows.push({ ...node, depth });
    const children = Array.isArray(node.children) ? node.children : [];
    children.forEach((childId) => visit(childId, depth + 1));
  };

  visit(rootId, 0);
  return rows;
}

function resetStateForRun() {
  initWorkflowTreeState();
  currentRun = null;
  currentPreview = null;
  currentPreviewState = { status: "pending", detail: "等待预分析" };
  pendingExecutionContext = null;
  currentNarrative = "";
  currentReportPayload = null;
  currentVotes = [];
  currentStepState = {};
  currentEvidenceRegistry = [];
  currentEvidenceEventCount = 0;
  currentRenderedExtract = null;
  currentStepSummaries = [];
  currentSourcePlan = {
    event_type: "generic_claim",
    domain: "general_news",
    domain_keywords: [],
    plan_version: "manual_default",
    selection_confidence: 0,
    must_have_platforms: [],
    candidate_platforms: [],
    excluded_platforms: [],
    selected_platforms: [],
    official_floor_platforms: [],
    official_selected_platforms: [],
    official_selected_count: 0,
    selection_reasons: [],
    risk_notes: [],
  };
  currentAcquisitionReport = null;
  currentPlatformStatusMap = {};
  currentMediaCrawlerStatus = {
    enabled: false,
    enabled_by_request: null,
    ack: false,
    platforms: [],
    timeout_sec: 120,
  };
  currentMediaCrawlerPlatformMap = {};
  currentOpinionMonitoring = { ...EMPTY_OPINION_MONITORING };
  currentClaimAnalysis = { ...EMPTY_CLAIM_ANALYSIS, claims: [], review_queue: [] };
  selectedClaimId = null;
  selectedWorkflowNodeId = "root";
  workflowEventSeq = 0;
  currentSegmentCard = null;
  currentSegmentState = {
    conclusion: "等待结论...",
    evidence: [],
    reasoning: [],
    recommendation: [],
  };
  debugLines = [];
  renderDebugLog();
  DEFAULT_STEPS.forEach((id) => {
    currentStepState[id] = { status: "pending" };
  });
  renderStepTimeline();
  if (streamPanel) streamPanel.innerHTML = "";
  if (noDataPanel) {
    noDataPanel.classList.remove("show");
    noDataPanel.innerHTML = "";
  }
  if (evidenceCards) evidenceCards.innerHTML = "";
  if (sourcePlanPanel) sourcePlanPanel.innerHTML = '<div class="empty-block">等待自动选源结果...</div>';
  if (failureImpactPanel) {
    failureImpactPanel.classList.remove("show");
    failureImpactPanel.innerHTML = "";
  }
  if (claimReasoningPanel) claimReasoningPanel.innerHTML = '<div class="empty-block">等待主张级深度分析...</div>';
  if (opinionRiskPanel) opinionRiskPanel.innerHTML = '<div class="empty-block">等待评论与水军风险监测...</div>';
  if (claimGraphPanel) claimGraphPanel.innerHTML = '<div class="empty-block">等待主张级分析...</div>';
  if (evidenceTracePanel) evidenceTracePanel.innerHTML = '<div class="empty-block">选择主张后查看证据链。</div>';
  if (reviewQueuePanel) reviewQueuePanel.innerHTML = '<div class="empty-block">暂无复核任务。</div>';
  if (stepSummaryPanel) stepSummaryPanel.innerHTML = '<div class="empty-block">等待环节总结...</div>';
  resetPreviewPanel();
  if (myTodoPanel) myTodoPanel.innerHTML = '<div class="empty-block">等待任务数据生成待办。</div>';
  activeReportId = "";
  renderMyArticleSuggestionPanel(null);
  if (agentPanel) agentPanel.innerHTML = "";
  if (agentSummary) agentSummary.innerHTML = "";
  if (anomalySummary) anomalySummary.innerHTML = "";
  renderRailSearchPanel();
  renderRailMetricsPanel();
  renderWorkflowTree();
  resetEvidenceFilters();
}

function renderDebugLog() {
  if (!debugLog) return;
  debugLog.textContent = debugLines.join("\n");
}

function appendDebugLine(eventType, payload) {
  const stamp = new Date().toLocaleTimeString("zh-CN");
  let body = "";
  try {
    body = JSON.stringify(payload || {});
  } catch {
    body = String(payload || "");
  }
  debugLines.push(`[${stamp}] ${eventType}: ${body}`);
  if (debugLines.length > 150) {
    debugLines = debugLines.slice(debugLines.length - 150);
  }
  renderDebugLog();
}

function buildList(items) {
  return items && items.length ? items.map((item) => `<li>${escapeHtml(item)}</li>`).join("") : "<li>暂无</li>";
}

function ensureSegmentCard() {
  if (!streamPanel) return null;
  if (currentSegmentCard) return currentSegmentCard;
  const wrapper = document.createElement("div");
  wrapper.className = "event role-assistant event-segment-batch";
  wrapper.dataset.level = "info";
  wrapper.innerHTML = `
    <div class="meta">
      <span>Aletheia</span>
      <span class="segment-time">${new Date().toLocaleTimeString("zh-CN")}</span>
    </div>
    <div class="msg">
      <div class="segment-grid">
        <section class="segment-card">
          <h4>结论</h4>
          <p data-segment="conclusion">等待结论...</p>
        </section>
        <section class="segment-card">
          <h4>证据</h4>
          <ul data-segment="evidence"><li>等待检索...</li></ul>
        </section>
        <section class="segment-card">
          <h4>推理</h4>
          <ul data-segment="reasoning"><li>等待步骤更新...</li></ul>
        </section>
        <section class="segment-card">
          <h4>建议</h4>
          <ul data-segment="recommendation"><li>等待多 Agent 结论...</li></ul>
        </section>
      </div>
    </div>
  `;
  streamPanel.appendChild(wrapper);
  streamPanel.scrollTop = streamPanel.scrollHeight;
  currentSegmentCard = wrapper;
  return wrapper;
}

function trimUnique(items, nextItem, limit = 6) {
  if (!nextItem) return items.slice(0, limit);
  const merged = [nextItem, ...items.filter((x) => x !== nextItem)];
  return merged.slice(0, limit);
}

function updateSegmentCard(patch) {
  const wrapper = ensureSegmentCard();
  if (!wrapper) return;
  if (!currentSegmentState) {
    currentSegmentState = { conclusion: "等待结论...", evidence: [], reasoning: [], recommendation: [] };
  }
  if (patch.conclusion) currentSegmentState.conclusion = patch.conclusion;
  if (patch.evidence) currentSegmentState.evidence = patch.evidence;
  if (patch.reasoning) currentSegmentState.reasoning = patch.reasoning;
  if (patch.recommendation) currentSegmentState.recommendation = patch.recommendation;

  const conclusionEl = wrapper.querySelector('[data-segment="conclusion"]');
  const evidenceEl = wrapper.querySelector('[data-segment="evidence"]');
  const reasoningEl = wrapper.querySelector('[data-segment="reasoning"]');
  const recommendationEl = wrapper.querySelector('[data-segment="recommendation"]');
  if (conclusionEl) conclusionEl.textContent = currentSegmentState.conclusion;
  if (evidenceEl) evidenceEl.innerHTML = buildList(currentSegmentState.evidence);
  if (reasoningEl) reasoningEl.innerHTML = buildList(currentSegmentState.reasoning);
  if (recommendationEl) recommendationEl.innerHTML = buildList(currentSegmentState.recommendation);
}

function pushRunSummaryToChat(result) {
  const chain = result?.enhanced?.reasoning_chain || {};
  const claimAnalysis = normalizeClaimAnalysis(result?.claim_analysis || currentClaimAnalysis);
  const score = Number(chain.final_score || 0).toFixed(2);
  const level = chain.final_level || "UNKNOWN";
  const riskFlags = (chain.risk_flags || []).join("、") || "无";
  const recommendation = result?.agent_outputs?.recommendation || "建议人工复核";
  const evidenceItems = (result?.evidence_registry || [])
    .slice(0, 4)
    .map((ev) => `${ev.source_name || "source"}：${String(ev.snippet || "").slice(0, 72)}`);
  const reasoningItems = (chain.steps || [])
    .slice(0, 4)
    .map((step) => `${step.stage || "step"}：${step.conclusion || step.reasoning || "暂无"}`);
  const adviceItems = [
    `主张结论：${claimAnalysis.run_verdict || "UNCERTAIN"}（复核队列 ${Number((claimAnalysis.review_queue || []).length)}）`,
    recommendation,
    ...((result?.no_data_explainer?.next_queries || []).slice(0, 2).map((q) => `补证检索：${q}`)),
    "结果已同步到：证据报告 / 信息流 / 可视化",
  ];
  updateSegmentCard({
    conclusion: `${level} · 可信度 ${score} · 风险 ${riskFlags}`,
    evidence: evidenceItems,
    reasoning: reasoningItems,
    recommendation: adviceItems,
  });
  if (currentSegmentCard) currentSegmentCard.dataset.level = "success";
  if (streamPanel) {
    streamPanel.scrollTop = streamPanel.scrollHeight;
  }
}

async function postJson(path, payload, signal) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || data.message || detail;
    } catch {
      detail = await res.text();
    }
    throw new Error(detail);
  }
  return res.json();
}

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      detail = await res.text();
    }
    throw new Error(`GET ${path} failed: ${detail}`);
  }
  return res.json();
}

function renderStepTimeline() {
  if (!stepTimeline) return;
  const entries = Object.entries(currentStepState);
  if (!entries.length) {
    stepTimeline.innerHTML = "";
    return;
  }
  stepTimeline.innerHTML = entries
    .map(([id, info]) => {
      const status = info?.status || "pending";
      const elapsed = Number(info?.elapsed_ms || 0);
      const pretty = id.replaceAll("_", " ");
      const elapsedText = elapsed > 0 ? ` · ${(elapsed / 1000).toFixed(1)}s` : "";
      return `<div class="timeline-step" data-status="${escapeHtml(status)}"><div class="name">${escapeHtml(pretty)}</div><div>${escapeHtml(status)}${escapeHtml(elapsedText)}</div></div>`;
    })
    .join("");
}

function updateStepStatus(stepId, status, extra = {}) {
  if (!stepId) return;
  currentStepState[stepId] = { ...(currentStepState[stepId] || {}), status, ...extra };
  renderStepTimeline();
  renderWorkflowTree();
}

function normalizeSourcePlan(sourcePlanInput) {
  const raw = sourcePlanInput && typeof sourcePlanInput === "object" ? sourcePlanInput : {};
  return {
    event_type: String(raw.event_type || "generic_claim"),
    domain: String(raw.domain || "general_news"),
    domain_keywords: Array.isArray(raw.domain_keywords) ? raw.domain_keywords.map((x) => String(x)) : [],
    plan_version: String(raw.plan_version || "manual_default"),
    selection_confidence: Number(raw.selection_confidence || 0),
    must_have_platforms: Array.isArray(raw.must_have_platforms) ? raw.must_have_platforms.map((x) => String(x)) : [],
    candidate_platforms: Array.isArray(raw.candidate_platforms) ? raw.candidate_platforms.map((x) => String(x)) : [],
    excluded_platforms: Array.isArray(raw.excluded_platforms) ? raw.excluded_platforms.map((x) => String(x)) : [],
    selected_platforms: Array.isArray(raw.selected_platforms) ? raw.selected_platforms.map((x) => String(x)) : [],
    official_floor_platforms: Array.isArray(raw.official_floor_platforms)
      ? raw.official_floor_platforms.map((x) => String(x))
      : [],
    official_selected_platforms: Array.isArray(raw.official_selected_platforms)
      ? raw.official_selected_platforms.map((x) => String(x))
      : [],
    official_selected_count: Number(raw.official_selected_count || 0),
    selection_reasons: Array.isArray(raw.selection_reasons) ? raw.selection_reasons.map((x) => String(x)) : [],
    risk_notes: Array.isArray(raw.risk_notes) ? raw.risk_notes.map((x) => String(x)) : [],
  };
}

function renderSourcePlanPanel(sourcePlanInput) {
  if (!sourcePlanPanel) return;
  const sourcePlan = normalizeSourcePlan(sourcePlanInput);
  currentSourcePlan = sourcePlan;
  const must = sourcePlan.must_have_platforms || [];
  const selected = sourcePlan.selected_platforms || [];
  const excluded = sourcePlan.excluded_platforms || [];
  const officialFloor = sourcePlan.official_floor_platforms || [];
  const officialSelected = sourcePlan.official_selected_platforms || [];
  const risks = sourcePlan.risk_notes || [];
  const confidencePct = Math.round(Number(sourcePlan.selection_confidence || 0) * 100);
  const domainKeywords = sourcePlan.domain_keywords || [];
  const sidecarPlatforms = Array.isArray(currentMediaCrawlerStatus?.platforms)
    ? currentMediaCrawlerStatus.platforms
    : [];
  const sidecarEnabled = Boolean(currentMediaCrawlerStatus?.enabled);
  const sidecarAck = Boolean(currentMediaCrawlerStatus?.ack);
  sourcePlanPanel.innerHTML = `
    <article class="source-plan-card">
      <div class="source-plan-head">
        <span>event=${escapeHtml(sourcePlan.event_type)}</span>
        <span>domain=${escapeHtml(sourcePlan.domain)} · conf=${confidencePct}%</span>
      </div>
      <div class="source-plan-line">MediaCrawler：${sidecarEnabled ? "enabled" : "disabled"} · ack=${sidecarAck ? "yes" : "no"} · 平台=${escapeHtml(sidecarPlatforms.join("、") || "无")}</div>
      <div class="source-plan-line">计划版本：${escapeHtml(sourcePlan.plan_version || "manual_default")}</div>
      <div class="source-plan-line">领域关键词：${escapeHtml(domainKeywords.join("、") || "无")}</div>
      <div class="source-plan-line">必选源：${escapeHtml(must.join("、") || "无")}</div>
      <div class="source-plan-line">实际选源：${escapeHtml(selected.join("、") || "无")}</div>
      <div class="source-plan-line">官方保底：${escapeHtml(officialFloor.join("、") || "无")}</div>
      <div class="source-plan-line">官方命中：${escapeHtml(officialSelected.join("、") || "无")}（${Number(
        sourcePlan.official_selected_count || 0
      )}）</div>
      <div class="source-plan-line">排除源：${escapeHtml(excluded.join("、") || "无")}</div>
      <div class="source-plan-line">风险备注：${escapeHtml(risks.join("；") || "无")}</div>
    </article>
  `;
  renderFailureImpactPanel();
  renderRailSearchPanel();
  renderRailMetricsPanel();
  renderWorkflowTree();
}

function normalizeAcquisitionReport(acquisitionInput) {
  const raw = acquisitionInput && typeof acquisitionInput === "object" ? acquisitionInput : {};
  return {
    external_evidence_count: Number(raw.external_evidence_count || raw.valid_evidence_count || 0),
    derived_evidence_count: Number(raw.derived_evidence_count || 0),
    synthetic_context_count: Number(raw.synthetic_context_count || 0),
    primary_count: Number(raw.primary_count || 0),
    background_count: Number(raw.background_count || 0),
    noise_count: Number(raw.noise_count || 0),
    external_primary_count: Number(raw.external_primary_count || raw.primary_count || 0),
    external_background_count: Number(raw.external_background_count || raw.background_count || 0),
    external_noise_count: Number(raw.external_noise_count || raw.noise_count || 0),
    hot_fallback_count: Number(raw.hot_fallback_count || 0),
    mediacrawler_live_count: Number(raw.mediacrawler_live_count || 0),
    native_live_count: Number(raw.native_live_count || 0),
    mediacrawler_platforms_hit: Array.isArray(raw.mediacrawler_platforms_hit)
      ? raw.mediacrawler_platforms_hit.map((x) => String(x))
      : [],
    mediacrawler_failures: Array.isArray(raw.mediacrawler_failures) ? raw.mediacrawler_failures : [],
    must_have_platform_count: Number(raw.must_have_platform_count || 0),
    must_have_platform_with_data_count: Number(raw.must_have_platform_with_data_count || 0),
    must_have_platform_fail_count: Number(raw.must_have_platform_fail_count || 0),
    must_have_hit_ratio: Number(raw.must_have_hit_ratio || 0),
    platform_reason_stats: raw.platform_reason_stats && typeof raw.platform_reason_stats === "object" ? raw.platform_reason_stats : {},
  };
}

function normalizeOpinionMonitoring(input) {
  const raw = input && typeof input === "object" ? input : {};
  return {
    status: String(raw.status || "NOT_RUN"),
    keyword: String(raw.keyword || ""),
    discovery_mode: String(raw.discovery_mode || "reuse_search_results"),
    synthetic_comment_mode: Boolean(raw.synthetic_comment_mode),
    comment_target: Number(raw.comment_target || 120),
    total_comments: Number(raw.total_comments || 0),
    real_comment_count: Number(raw.real_comment_count || 0),
    synthetic_comment_count: Number(raw.synthetic_comment_count || 0),
    sidecar_comment_count: Number(raw.sidecar_comment_count || 0),
    real_comment_ratio: Number(raw.real_comment_ratio || 0),
    real_comment_target_reached: Boolean(raw.real_comment_target_reached),
    unique_accounts_count: Number(raw.unique_accounts_count || 0),
    suspicious_accounts_count: Number(raw.suspicious_accounts_count || 0),
    suspicious_ratio: Number(raw.suspicious_ratio || 0),
    template_repeat_ratio: Number(raw.template_repeat_ratio || 0),
    risk_level: String(raw.risk_level || "unknown"),
    risk_flags: Array.isArray(raw.risk_flags) ? raw.risk_flags.map((x) => String(x)) : [],
    comment_target_reached: Boolean(raw.comment_target_reached),
    top_suspicious_accounts: Array.isArray(raw.top_suspicious_accounts) ? raw.top_suspicious_accounts : [],
    failed_platforms: Array.isArray(raw.failed_platforms) ? raw.failed_platforms : [],
    sidecar_failures: Array.isArray(raw.sidecar_failures) ? raw.sidecar_failures : [],
    sample_comments: Array.isArray(raw.sample_comments) ? raw.sample_comments : [],
    summary_text: String(raw.summary_text || "评论监测尚未执行。"),
  };
}

function getPlatformGroupLabel() {
  if (!platformSelect || !(platformSelect instanceof HTMLSelectElement)) return "未知";
  const selected = platformSelect.options[platformSelect.selectedIndex];
  return selected?.textContent?.trim() || platformSelect.value || "未知";
}

function renderRailSearchPanel() {
  if (!railSearchPanel) return;
  const claimText = String(claimInput?.value || currentRun?.claim || "").trim();
  const keywordText = String(keywordInput?.value || currentRun?.search?.keyword || "").trim();
  const sourceUrl = String(sourceUrlInput?.value || currentReportPayload?.source_url || "").trim();
  const runId = String(currentRun?.run_id || "-");
  const selectedPlatforms = Array.isArray(currentSourcePlan?.selected_platforms)
    ? currentSourcePlan.selected_platforms.map((x) => String(x))
    : [];
  const modeText = selectedMode?.textContent?.trim() || String(currentMode || "dual");
  const strategyText = String(currentSourcePlan?.plan_version || "manual_default");
  const sidecarText = currentMediaCrawlerStatus?.enabled ? "enabled" : "disabled";
  const platformGroup = getPlatformGroupLabel();

  const chips = selectedPlatforms.slice(0, 8);
  const chipsHtml = chips.length
    ? chips.map((p) => `<span class="rail-chip">${escapeHtml(p)}</span>`).join("")
    : '<span class="rail-chip muted">待选源</span>';
  const overflow = selectedPlatforms.length > 8 ? `+${selectedPlatforms.length - 8}` : "";

  railSearchPanel.innerHTML = `
    <div class="rail-query-grid">
      <div class="rail-query-item"><span>Run</span><strong>${escapeHtml(runId)}</strong></div>
      <div class="rail-query-item"><span>Mode</span><strong>${escapeHtml(modeText)}</strong></div>
      <div class="rail-query-item"><span>平台组</span><strong>${escapeHtml(platformGroup)}</strong></div>
      <div class="rail-query-item"><span>策略</span><strong>${escapeHtml(strategyText)}</strong></div>
      <div class="rail-query-item"><span>Sidecar</span><strong>${escapeHtml(sidecarText)}</strong></div>
      <div class="rail-query-item"><span>Keyword</span><strong>${escapeHtml(keywordText || "未设置")}</strong></div>
    </div>
    <div class="rail-query-text">
      <label>主张</label>
      <p>${escapeHtml(compactInlineText(claimText || "等待输入主张...", 180))}</p>
    </div>
    <div class="rail-query-text">
      <label>URL</label>
      <p>${sourceUrl ? `<a class="trace-url" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer noopener">${escapeHtml(compactInlineText(sourceUrl, 120))}</a>` : "未提供"}</p>
    </div>
    <div class="rail-chip-list">${chipsHtml}${overflow ? `<span class="rail-chip muted">${escapeHtml(overflow)}</span>` : ""}</div>
  `;
}

function renderRailMetricsPanel() {
  if (!railMetricsPanel) return;
  const acq = normalizeAcquisitionReport(currentAcquisitionReport || {});
  const opinion = normalizeOpinionMonitoring(currentOpinionMonitoring || {});
  const claims = Array.isArray(currentClaimAnalysis?.claims) ? currentClaimAnalysis.claims : [];
  const reviewCount = Array.isArray(currentClaimAnalysis?.review_queue) ? currentClaimAnalysis.review_queue.length : 0;
  const primaryRatio = acq.external_evidence_count > 0 ? acq.external_primary_count / acq.external_evidence_count : 0;
  const fallbackRatio = acq.external_evidence_count > 0 ? acq.hot_fallback_count / acq.external_evidence_count : 0;

  railMetricsPanel.innerHTML = `
    <div class="rail-metrics-grid">
      <article class="rail-metric-card"><span>外部证据</span><strong>${acq.external_evidence_count}</strong></article>
      <article class="rail-metric-card"><span>主证据</span><strong>${acq.external_primary_count}</strong></article>
      <article class="rail-metric-card"><span>背景证据</span><strong>${acq.external_background_count}</strong></article>
      <article class="rail-metric-card"><span>噪声证据</span><strong>${acq.external_noise_count}</strong></article>
      <article class="rail-metric-card"><span>主张数</span><strong>${claims.length}</strong></article>
      <article class="rail-metric-card"><span>复核队列</span><strong>${reviewCount}</strong></article>
      <article class="rail-metric-card"><span>真实评论</span><strong>${opinion.real_comment_count}</strong></article>
      <article class="rail-metric-card"><span>可疑比</span><strong>${Math.round(opinion.suspicious_ratio * 100)}%</strong></article>
    </div>
    <div class="rail-metrics-line">主证据占比：${Math.round(primaryRatio * 100)}% · hot fallback 比例：${Math.round(fallbackRatio * 100)}%</div>
    <div class="rail-metrics-line">native=${acq.native_live_count} · sidecar=${acq.mediacrawler_live_count} · 评论覆盖=${opinion.total_comments}/${opinion.comment_target}</div>
  `;
}

function buildFailureImpactSnapshot() {
  const sourcePlan = normalizeSourcePlan(currentSourcePlan || {});
  const acquisition = normalizeAcquisitionReport(currentAcquisitionReport || {});
  const opinion = normalizeOpinionMonitoring(currentOpinionMonitoring || {});
  const opinionActive = String(opinion.status || "NOT_RUN").toUpperCase() !== "NOT_RUN";
  const statuses = Object.values(currentPlatformStatusMap || {}).filter((x) => x && typeof x === "object");
  const failedStatuses = statuses.filter((row) => {
    const status = String(row.status || "").toLowerCase();
    const errorLike = ["failed", "timeout", "circuit_open", "error", "blocked"].includes(status);
    const noData = Number(row.items_collected || 0) <= 0 && status !== "success";
    return errorLike || noData;
  });
  const highImpactFailures = failedStatuses.filter(
    (row) => String(row.impact_on_verdict || "").toLowerCase() === "high"
  );

  const mustHave = sourcePlan.must_have_platforms || [];
  const hasData = new Set(
    statuses
      .filter((row) => Number(row.items_collected || 0) > 0)
      .map((row) => String(row.platform || ""))
      .filter(Boolean)
  );
  const missingMustHave = mustHave.filter((p) => !hasData.has(String(p || "")));

  const runVerdict = String(currentClaimAnalysis?.run_verdict || "UNCERTAIN");
  const reviewCount = Number((currentClaimAnalysis?.review_queue || []).length || 0);
  let impactSummary = "结论影响可控";
  if (highImpactFailures.length > 0 || missingMustHave.length > 0) {
    impactSummary = `高影响缺口，结论倾向需降级（当前 ${runVerdict}）`;
  } else if (opinionActive && !opinion.comment_target_reached && opinion.total_comments > 0) {
    impactSummary = `评论覆盖不足（${opinion.total_comments}/${opinion.comment_target}），需继续补采`;
  } else if (opinionActive && String(opinion.risk_level).toLowerCase() === "high") {
    impactSummary = "检测到高风险水军信号，结论必须人工复核";
  } else if (reviewCount > 0) {
    impactSummary = `存在复核任务（${reviewCount} 条），结论待补证`;
  }

  return {
    failedStatuses,
    highImpactFailures,
    missingMustHave,
    acquisition,
    opinion,
    opinionActive,
    impactSummary,
    runVerdict,
    reviewCount,
  };
}

function renderFailureImpactPanel() {
  if (!failureImpactPanel) return;
  const snapshot = buildFailureImpactSnapshot();
  const { failedStatuses, highImpactFailures, missingMustHave, acquisition, opinion, opinionActive, impactSummary, runVerdict, reviewCount } =
    snapshot;

  const hasImpact =
    failedStatuses.length > 0 ||
    missingMustHave.length > 0 ||
    Number(acquisition.hot_fallback_count || 0) > 0 ||
    Number(acquisition.mediacrawler_failures?.length || 0) > 0 ||
    Number(opinion.sidecar_failures?.length || 0) > 0 ||
    Number(acquisition.must_have_platform_fail_count || 0) > 0 ||
    (opinionActive && !opinion.comment_target_reached) ||
    (opinionActive && String(opinion.risk_level || "unknown").toLowerCase() !== "low") ||
    reviewCount > 0;

  if (!hasImpact) {
    failureImpactPanel.classList.add("show", "safe");
    failureImpactPanel.innerHTML = `
      <div><strong>当前无高影响失败</strong></div>
      <div>平台缺口、sidecar降级、复核队列暂未触发关键告警。</div>
    `;
    renderRailMetricsPanel();
    return;
  }

  const failedRows = failedStatuses
    .slice(0, 8)
    .map((row) => {
      const platform = String(row.platform || "unknown");
      const status = String(row.status || "unknown");
      const reason = String(row.reason_code || "N/A");
      const impact = String(row.impact_on_verdict || "unknown");
      const items = Number(row.items_collected || 0);
      return `<li>${escapeHtml(platform)}: ${escapeHtml(status)} / ${escapeHtml(reason)} / impact=${escapeHtml(impact)} / items=${items}</li>`;
    })
    .join("");

  const reasonStats = acquisition.platform_reason_stats?.by_reason || {};
  const reasonSummary = Object.entries(reasonStats)
    .slice(0, 6)
    .map(([k, v]) => `${k}:${v}`)
    .join("，");
  const allSidecarFailures = []
    .concat(Array.isArray(acquisition.mediacrawler_failures) ? acquisition.mediacrawler_failures : [])
    .concat(Array.isArray(opinion.sidecar_failures) ? opinion.sidecar_failures : []);
  const sidecarFailureSummary = allSidecarFailures
    .slice(0, 6)
    .map((row) => {
      const stage = String(row.stage || "search");
      const postId = String(row.post_id || "");
      const suffix = postId ? `#${postId}` : "";
      return `${row.platform}:${row.reason || "unknown"}(${stage}${suffix})`;
    })
    .join("、");

  failureImpactPanel.classList.add("show");
  failureImpactPanel.classList.remove("safe");
  failureImpactPanel.innerHTML = `
    <div><strong>失败影响范围</strong> · verdict=${escapeHtml(runVerdict)} · review=${reviewCount}</div>
    <div>影响判断：${escapeHtml(impactSummary)}</div>
    <div>平台失败：${failedStatuses.length}（高影响 ${highImpactFailures.length}）</div>
    <div>必选源缺口：${escapeHtml(missingMustHave.join("、") || "无")}</div>
    <div>证据分层：external=${acquisition.external_evidence_count}（primary=${acquisition.external_primary_count} / background=${acquisition.external_background_count} / noise=${acquisition.external_noise_count}） · derived=${acquisition.derived_evidence_count} · synthetic=${acquisition.synthetic_context_count}</div>
    <div>数据来源：native=${acquisition.native_live_count} · mediacrawler=${acquisition.mediacrawler_live_count} · sidecar命中平台=${escapeHtml((acquisition.mediacrawler_platforms_hit || []).join("、") || "无")}</div>
    <div>回退计数：hot_fallback=${acquisition.hot_fallback_count} · must_hit=${Math.round(Number(acquisition.must_have_hit_ratio || 0) * 100)}%</div>
    <div>评论监测：${opinion.total_comments}/${opinion.comment_target} · 真实 ${opinion.real_comment_count} (${Math.round(Number(opinion.real_comment_ratio || 0) * 100)}%) · sidecar评论 ${opinion.sidecar_comment_count} · 可疑比 ${Math.round(Number(opinion.suspicious_ratio || 0) * 100)}% · 风险 ${escapeHtml(String(opinion.risk_level || "unknown").toUpperCase())}</div>
    <div>sidecar降级：${escapeHtml(sidecarFailureSummary || "无")}</div>
    <div>原因分布：${escapeHtml(reasonSummary || "无")}</div>
    ${failedRows ? `<ul>${failedRows}</ul>` : ""}
  `;
  renderRailMetricsPanel();
}

function getWorkflowTreeNodes() {
  syncWorkflowCoreNodes();
  return flattenWorkflowNodes("root");
}

function renderWorkflowPayload(payload) {
  if (!payload || typeof payload !== "object") return "";
  const entries = Object.entries(payload)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .slice(0, 10);
  if (!entries.length) return "";
  return `
    <div class="workflow-kv">
      ${entries
        .map(([key, value]) => {
          let text = "";
          if (Array.isArray(value)) text = value.slice(0, 5).join("、");
          else if (typeof value === "object") text = JSON.stringify(value);
          else text = String(value);
          return `<div class="workflow-kv-row"><span>${escapeHtml(key)}</span><span>${escapeHtml(compactInlineText(text, 120))}</span></div>`;
        })
        .join("")}
    </div>
  `;
}

function renderWorkflowTreeDetail(nodes) {
  if (!workflowTreeDetail) return;
  const active = nodes.find((n) => n.id === selectedWorkflowNodeId) || nodes[0];
  if (!active) {
    workflowTreeDetail.innerHTML = '<div class="empty-block">等待任务启动...</div>';
    return;
  }
  if (active.id === "preview") {
    const preview = currentPreview || {};
    const claimCount = Array.isArray(preview.claims_draft) ? preview.claims_draft.length : 0;
    const selectedCount = Array.isArray(preview?.source_plan?.selected_platforms)
      ? preview.source_plan.selected_platforms.length
      : 0;
    const risks = Array.isArray(preview.risk_notes) ? preview.risk_notes : [];
    workflowTreeDetail.innerHTML = `
      <div class="workflow-detail-card">
        <h4>${escapeHtml(active.label)}</h4>
        <p>${escapeHtml(active.detail)}</p>
        <p>状态：${escapeHtml(currentPreviewState.status || "pending")} · preview_id=${escapeHtml(preview.preview_id || "-")}</p>
        <p>主张草案：${claimCount} · 计划平台：${selectedCount}</p>
        <p>风险提示：${escapeHtml(risks.join("、") || "无")}</p>
        <p>摘要：${escapeHtml(compactInlineText(preview.intent_summary || "等待预分析完成...", 260))}</p>
      </div>
    `;
    return;
  }
  if (active.id === "source") {
    const confidencePct = Math.round(Number(currentSourcePlan.selection_confidence || 0) * 100);
    const mc = currentMediaCrawlerStatus || {};
    workflowTreeDetail.innerHTML = `
      <div class="workflow-detail-card">
        <h4>${escapeHtml(active.label)}</h4>
        <p>${escapeHtml(active.detail)}</p>
        <p>计划版本：${escapeHtml(currentSourcePlan.plan_version || "manual_default")} · conf=${confidencePct}%</p>
        <p>MediaCrawler：${mc.enabled ? "enabled" : "disabled"} · ack=${mc.ack ? "yes" : "no"} · timeout=${Number(mc.timeout_sec || 120)}s</p>
        <p>MediaCrawler平台：${escapeHtml((mc.platforms || []).join("、") || "无")}</p>
        <p>领域关键词：${escapeHtml((currentSourcePlan.domain_keywords || []).join("、") || "无")}</p>
        <p>必选源：${escapeHtml((currentSourcePlan.must_have_platforms || []).join("、") || "无")}</p>
        <p>候选源：${escapeHtml((currentSourcePlan.candidate_platforms || []).join("、") || "无")}</p>
        <p>官方保底：${escapeHtml((currentSourcePlan.official_floor_platforms || []).join("、") || "无")}</p>
        <p>官方命中：${escapeHtml((currentSourcePlan.official_selected_platforms || []).join("、") || "无")}（${
          Number(currentSourcePlan.official_selected_count || 0)
        }）</p>
        <p>排除源：${escapeHtml((currentSourcePlan.excluded_platforms || []).join("、") || "无")}</p>
      </div>
    `;
    return;
  }
  if (active.id === "opinion") {
    const opinion = normalizeOpinionMonitoring(currentOpinionMonitoring || {});
    workflowTreeDetail.innerHTML = `
      <div class="workflow-detail-card">
        <h4>${escapeHtml(active.label)}</h4>
        <p>${escapeHtml(active.detail)}</p>
        <p>状态：${escapeHtml(opinion.status || "NOT_RUN")} · 覆盖 ${opinion.total_comments}/${opinion.comment_target}</p>
        <p>真实评论：${opinion.real_comment_count} (${Math.round(opinion.real_comment_ratio * 100)}%) · 目标达成=${opinion.real_comment_target_reached ? "yes" : "no"}</p>
        <p>可疑账号：${opinion.suspicious_accounts_count}/${opinion.unique_accounts_count} · 比例 ${Math.round(opinion.suspicious_ratio * 100)}%</p>
        <p>风险标记：${escapeHtml((opinion.risk_flags || []).join("、") || "无")}</p>
      </div>
    `;
    return;
  }

  const updatedAt = active.updatedAt ? new Date(active.updatedAt).toLocaleTimeString("zh-CN") : "";
  const payloadHtml = renderWorkflowPayload(active.payload);
  const link = active?.payload?.url || active?.payload?.original_url || "";
  const linkHtml = link
    ? `<p><a class="trace-url" href="${escapeHtml(link)}" target="_blank" rel="noreferrer noopener">${escapeHtml(link)}</a></p>`
    : "";

  workflowTreeDetail.innerHTML = `
    <div class="workflow-detail-card">
      <h4>${escapeHtml(active.label)}</h4>
      <p>${escapeHtml(active.detail || "")}</p>
      <p>状态：${escapeHtml(active.status || "pending")} · 更新时间：${escapeHtml(updatedAt || "-")}</p>
      ${linkHtml}
      ${payloadHtml}
    </div>
  `;
}

function renderWorkflowTree() {
  if (!workflowTree) return;
  const nodes = getWorkflowTreeNodes();
  if (!selectedWorkflowNodeId) selectedWorkflowNodeId = "root";
  const hasSelected = nodes.some((node) => node.id === selectedWorkflowNodeId);
  if (!hasSelected) selectedWorkflowNodeId = "root";
  const walk = (nodeId, depth = 0, seen = new Set()) => {
    if (!nodeId || seen.has(nodeId)) return "";
    const node = workflowTreeNodes[nodeId];
    if (!node) return "";
    seen.add(nodeId);
    const children = Array.isArray(node.children) ? node.children : [];
    const hasChildren = children.length > 0;
    const collapsed = hasChildren && collapsedWorkflowNodeIds.has(node.id);
    const active = node.id === selectedWorkflowNodeId ? "active" : "";
    const childrenHtml = hasChildren && !collapsed ? children.map((childId) => walk(childId, depth + 1, seen)).join("") : "";
    const detailText = node.detail ? compactInlineText(node.detail, 96) : "";
    return `
      <li class="workflow-branch-item depth-${depth}">
        <div class="workflow-node-wrap">
          <button type="button" class="workflow-node ${active}" data-node-id="${escapeHtml(node.id)}" data-status="${escapeHtml(node.status || "pending")}" style="--tree-depth:${depth}">
            <span class="workflow-node-title">${escapeHtml(node.label)}</span>
            <span class="workflow-node-meta">${escapeHtml(node.status || "pending")}</span>
          </button>
          ${hasChildren ? `<button type="button" class="workflow-toggle" data-node-id="${escapeHtml(node.id)}" aria-label="toggle">${collapsed ? "+" : "-"}</button>` : '<span class="workflow-toggle workflow-toggle-placeholder"></span>'}
        </div>
        ${detailText ? `<div class="workflow-node-detail" style="--tree-depth:${depth}">${escapeHtml(detailText)}</div>` : ""}
        ${childrenHtml ? `<ul class="workflow-branch">${childrenHtml}</ul>` : ""}
      </li>
    `;
  };
  workflowTree.innerHTML = `<ul class="workflow-branch workflow-root">${walk("root")}</ul>`;
  renderWorkflowTreeDetail(nodes);
}

function renderNoDataPanel(explainer) {
  if (!noDataPanel) return;
  if (!explainer) {
    noDataPanel.classList.remove("show");
    noDataPanel.innerHTML = "";
    return;
  }
  const nextQueries = explainer.next_queries || [];
  const attempted = explainer.attempted_platforms || [];
  const scope = explainer.retrieval_scope || {};
  const platformErrors = explainer.platform_errors || {};
  const formatPlatformError = (value) => {
    if (Array.isArray(value)) return value.join(", ");
    if (value && typeof value === "object") {
      return Object.entries(value)
        .map(([k, v]) => `${k}:${v}`)
        .join(", ");
    }
    return String(value || "unknown");
  };
  const errorLines = Object.entries(platformErrors)
    .slice(0, 8)
    .map(([platform, errs]) => `${platform}: ${formatPlatformError(errs)}`);
  noDataPanel.classList.add("show");
  noDataPanel.innerHTML = `
    <strong>证据不足（${escapeHtml(explainer.reason_code || "INSUFFICIENT_EVIDENCE")}）</strong>
    <div>检索平台：${escapeHtml(attempted.join("、") || "无")}</div>
    <div>命中条目：${escapeHtml(String(scope.total_items || 0))}，可回溯条目：${escapeHtml(String(scope.specific_items || 0))}</div>
    <div>有效覆盖率：${escapeHtml(String(Math.round(Number(explainer.coverage_ratio || 0) * 100)))}%</div>
    <div>失败原因：${escapeHtml(errorLines.join("；") || "无")}</div>
    <ul>${nextQueries.map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ul>
  `;
}

function resetEvidenceFilters() {
  if (evidencePlatformFilter) evidencePlatformFilter.innerHTML = '<option value="all">全部平台</option>';
  if (evidenceStanceFilter) evidenceStanceFilter.value = "all";
  if (evidenceTierFilter) evidenceTierFilter.value = "all";
  if (evidenceOriginFilter) evidenceOriginFilter.value = "all";
  if (evidenceClassFilter) evidenceClassFilter.value = "all";
}

function populateEvidenceFilters(cards) {
  if (!evidencePlatformFilter) return;
  const platforms = [...new Set((cards || []).map((c) => c.source_name).filter(Boolean))];
  evidencePlatformFilter.innerHTML = ['<option value="all">全部平台</option>']
    .concat(platforms.map((p) => `<option value="${escapeHtml(String(p))}">${escapeHtml(String(p))}</option>`))
    .join("");
}

function getEvidenceFilters() {
  return {
    platform: evidencePlatformFilter?.value || "all",
    stance: evidenceStanceFilter?.value || "all",
    tier: evidenceTierFilter?.value || "all",
    origin: evidenceOriginFilter?.value || "all",
    evidenceClass: evidenceClassFilter?.value || "all",
  };
}

function renderEvidenceCards(cards) {
  if (!evidenceCards) return;
  const filters = getEvidenceFilters();
  const filtered = (cards || []).filter((item) => {
    const platformOk = filters.platform === "all" || String(item.source_name || "") === filters.platform;
    const stanceOk = filters.stance === "all" || String(item.stance || "unknown") === filters.stance;
    const tierOk = filters.tier === "all" || String(item.source_tier || 3) === filters.tier;
    const origin = String(item.evidence_origin || "external");
    const originOk = filters.origin === "all" || origin === filters.origin;
    const className = String(item.evidence_class || "background");
    let classOk = filters.evidenceClass === "all" || className === filters.evidenceClass;
    if (filters.evidenceClass === "signal") {
      classOk = className === "primary" || className === "background";
    }
    return platformOk && stanceOk && tierOk && originOk && classOk;
  });

  if (!filtered.length) {
    evidenceCards.innerHTML = '<div class="evidence-card">暂无证据卡片</div>';
    return;
  }
  evidenceCards.innerHTML = filtered
    .slice(0, 300)
    .map(
      (item) => `
      <article class="evidence-card">
        <div class="meta">
          <span>${escapeHtml(item.source_name || "unknown")} · T${escapeHtml(String(item.source_tier || 3))}</span>
          <span>${escapeHtml(item.validation_status || "raw")} · ${escapeHtml(item.evidence_class || "background")} · ${escapeHtml(item.evidence_origin || "external")}</span>
        </div>
        <div>${escapeHtml(item.snippet || "")}</div>
        <div class="meta">
          <span>${escapeHtml(item.stance || "unknown")} · domain=${Math.round(Number(item.domain_match_score || 0) * 100)}%</span>
          <span>${Math.round(Number(item.confidence || 0) * 100)}% · ${escapeHtml(item.selection_reason || "n/a")}</span>
        </div>
      </article>
    `
    )
    .join("");
}

function normalizeClaimAnalysis(claimAnalysis) {
  if (!claimAnalysis || typeof claimAnalysis !== "object") {
    return { ...EMPTY_CLAIM_ANALYSIS, claims: [], review_queue: [] };
  }
  return {
    claims: Array.isArray(claimAnalysis.claims) ? claimAnalysis.claims : [],
    review_queue: Array.isArray(claimAnalysis.review_queue) ? claimAnalysis.review_queue : [],
    claim_reasoning: Array.isArray(claimAnalysis.claim_reasoning) ? claimAnalysis.claim_reasoning : [],
    matrix_summary: claimAnalysis.matrix_summary || { tier1_count: 0, tier2_count: 0, tier3_count: 0, tier4_count: 0 },
    run_verdict: claimAnalysis.run_verdict || "UNCERTAIN",
    summary: claimAnalysis.summary || {},
    factcheck: claimAnalysis.factcheck || {},
  };
}

function verdictClass(verdict) {
  const low = String(verdict || "").toLowerCase();
  if (low === "supported") return "verdict-supported";
  if (low === "refuted") return "verdict-refuted";
  if (low === "review_required") return "verdict-review_required";
  return "verdict-uncertain";
}

function renderClaimGraphPanel(claimAnalysis) {
  if (!claimGraphPanel) return;
  const claims = claimAnalysis.claims || [];
  const matrix = claimAnalysis.matrix_summary || {};
  if (!claims.length) {
    claimGraphPanel.innerHTML = '<div class="empty-block">尚未生成主张级分析。</div>';
    return;
  }
  const matrixLine = `
    <div class="matrix-summary">
      Tier1: ${Number(matrix.tier1_count || 0)} · Tier2: ${Number(matrix.tier2_count || 0)} · Tier3: ${Number(matrix.tier3_count || 0)}
      · 运行结论: ${escapeHtml(claimAnalysis.run_verdict || "UNCERTAIN")}
    </div>
  `;
  const cards = claims
    .map((item) => {
      const claimId = item.claim_id || "";
      const active = claimId === selectedClaimId;
      const stance = item.stance_summary || {};
      const score = Math.round(Number(item.score || 0) * 100);
      const reasons = (item.gate_reasons || []).slice(0, 3).join("、") || "无";
      const gateText = item.gate_passed ? "gate:pass" : "gate:blocked";
      const conflict = Number(stance.support || 0) > 0 && Number(stance.refute || 0) > 0 ? "冲突" : "单向";
      return `
        <article class="claim-card ${active ? "active" : ""}" data-claim-id="${escapeHtml(claimId)}">
          <div class="claim-title">${escapeHtml(item.text || "")}</div>
          <div class="claim-meta">
            <span class="verdict-pill ${verdictClass(item.verdict)}">${escapeHtml(item.verdict || "UNCERTAIN")}</span>
            <span>${score}% · ${escapeHtml(gateText)} · ${escapeHtml(conflict)}</span>
          </div>
          <div class="claim-meta">
            <span>S:${Number(stance.support || 0)} / R:${Number(stance.refute || 0)} / U:${Number(stance.unclear || 0)}</span>
            <span>${escapeHtml(item.type || "generic")}</span>
          </div>
          <div class="claim-reasons">门槛理由: ${escapeHtml(reasons)}</div>
        </article>
      `;
    })
    .join("");
  claimGraphPanel.innerHTML = `${matrixLine}${cards}`;
}

function pickClaim(claimAnalysis, claimId) {
  return (claimAnalysis.claims || []).find((row) => String(row.claim_id || "") === String(claimId || ""));
}

function renderEvidenceTracePanel(claimAnalysis) {
  if (!evidenceTracePanel) return;
  const claims = claimAnalysis.claims || [];
  if (!claims.length) {
    evidenceTracePanel.innerHTML = '<div class="empty-block">暂无可追踪主张。</div>';
    return;
  }
  if (!selectedClaimId) {
    selectedClaimId = claims[0].claim_id;
  }
  const claim = pickClaim(claimAnalysis, selectedClaimId);
  if (!claim) {
    evidenceTracePanel.innerHTML = '<div class="empty-block">请选择主张查看证据链。</div>';
    return;
  }
  const linked = claim.linked_evidence || [];
  if (!linked.length) {
    evidenceTracePanel.innerHTML = `
      <div class="empty-block">
        当前主张暂无线索明细。claim_id=${escapeHtml(claim.claim_id || "")}
      </div>
    `;
    return;
  }
  evidenceTracePanel.innerHTML = linked
    .slice(0, 120)
    .map((ev) => {
      const tier = Number(ev.source_tier || 4);
      const stance = String(ev.stance || "unclear");
      const conflictClass = stance === "refute" ? " conflict" : "";
      const score = Math.round(Number(ev.quality_score || 0) * 100);
      const publishedAt = ev.published_at ? String(ev.published_at) : "unknown_time";
      return `
        <article class="trace-item${conflictClass}">
          <div class="trace-top">
            <span>${escapeHtml(ev.source_name || "source")} · Tier${tier} · ${escapeHtml(stance)}</span>
            <span>${escapeHtml(publishedAt)} · q=${score}%</span>
          </div>
          <div class="trace-snippet">${escapeHtml(String(ev.snippet || "").slice(0, 260) || "无摘要")}</div>
          ${
            ev.url
              ? `<a class="trace-url" href="${escapeHtml(ev.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(ev.url)}</a>`
              : '<span class="trace-url">no-url</span>'
          }
          <div class="trace-top">
            <span>${escapeHtml(ev.validation_status || "unknown")}</span>
            <span>conf=${Math.round(Number(ev.confidence || 0) * 100)}%</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderReviewQueuePanel(claimAnalysis) {
  if (!reviewQueuePanel) return;
  const queue = claimAnalysis.review_queue || [];
  if (!queue.length) {
    reviewQueuePanel.innerHTML = '<div class="empty-block">当前无复核队列，或门槛已满足。</div>';
    return;
  }
  reviewQueuePanel.innerHTML = queue
    .map((item) => {
      const priority = String(item.priority || "medium");
      const reasons = (item.reasons || []).join("、") || "REVIEW_REQUIRED";
      const action =
        priority === "high"
          ? "建议动作：优先补 Tier1/Tier2 证据 + 人工快速复核。"
          : "建议动作：补充实体消歧或更多跨平台证据。";
      return `
        <article class="review-item ${escapeHtml(priority)}">
          <div class="review-title">claim=${escapeHtml(item.claim_id || "unknown")} · ${escapeHtml(priority)}</div>
          <div class="review-reasons">原因码：${escapeHtml(reasons)}</div>
          <div class="review-reasons">${escapeHtml(action)}</div>
        </article>
      `;
    })
    .join("");
}

function renderClaimReasoningPanel(claimAnalysis) {
  if (!claimReasoningPanel) return;
  const rows = claimAnalysis.claim_reasoning || [];
  if (!rows.length) {
    claimReasoningPanel.innerHTML = '<div class="empty-block">暂无主张级深度分析。</div>';
    return;
  }
  claimReasoningPanel.innerHTML = rows
    .map((row) => {
      const citations = Array.isArray(row.citations) ? row.citations : [];
      const citationHtml = citations.length
        ? citations
            .slice(0, 6)
            .map((c) => {
              const url = String(c.url || "");
              const meta = `${c.source_name || "source"} · Tier${Number(c.source_tier || 4)} · ${c.stance || "unclear"}`;
              return `
                <li>
                  ${
                    url
                      ? `<a class="trace-url" href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(meta)}</a>`
                      : `<span class="trace-url">${escapeHtml(meta)}</span>`
                  }
                  <div class="reasoning-citation-quote">${escapeHtml(String(c.snippet_quote || "").slice(0, 160) || "无引用文本")}</div>
                </li>
              `;
            })
            .join("")
        : "<li>无可追溯引用</li>";
      return `
        <article class="reasoning-card">
          <div class="reasoning-head">
            <span>claim=${escapeHtml(row.claim_id || "unknown")}</span>
            <span>${row.fallback ? "fallback" : "llm"}</span>
          </div>
          <p class="reasoning-line">${escapeHtml(row.conclusion_text || "无结论文本")}</p>
          <p class="reasoning-line">${escapeHtml(row.risk_text || "无风险文本")}</p>
          <div class="reasoning-steps">
            ${(Array.isArray(row.reasoning_steps) ? row.reasoning_steps : [])
              .slice(0, 6)
              .map((s) => `<code class="step-code-chip">${escapeHtml(String(s))}</code>`)
              .join("")}
          </div>
          <ul class="reasoning-citation-list">${citationHtml}</ul>
        </article>
      `;
    })
    .join("");
}

function renderOpinionRiskPanel(opinionInput) {
  if (!opinionRiskPanel) return;
  const opinion = normalizeOpinionMonitoring(opinionInput);
  currentOpinionMonitoring = opinion;
  const riskLevel = String(opinion.risk_level || "unknown").toLowerCase();
  const topAccounts = opinion.top_suspicious_accounts || [];
  const topComments = opinion.sample_comments || [];
  const failedPlatforms = opinion.failed_platforms || [];

  const accountsHtml = topAccounts.length
    ? topAccounts
        .slice(0, 8)
        .map((row) => {
          const scorePct = Math.round(Number(row.risk_score || 0) * 100);
          const features = Array.isArray(row.detected_features) ? row.detected_features.slice(0, 4).join("、") : "无";
          return `
            <article class="review-item ${escapeHtml(String(row.risk_level || "medium"))}">
              <div class="review-title">${escapeHtml(row.platform || "unknown")} · ${escapeHtml(row.nickname || row.user_id || "anon")} · ${scorePct}%</div>
              <div class="review-reasons">特征：${escapeHtml(features)}</div>
              <div class="review-reasons">样本：${escapeHtml((row.sample_comments || []).slice(0, 1).join(" ") || "无")}</div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty-block">暂无高风险账号样本。</div>';

  const commentsHtml = topComments.length
    ? topComments
        .slice(0, 10)
        .map((row) => {
          const url = String(row.url || "");
          const meta = `${row.platform || "platform"} · ${row.author_name || row.author_id || "anon"} · likes=${Number(row.likes || 0)}`;
          return `
            <li>
              ${
                url
                  ? `<a class="trace-url" href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(meta)}</a>`
                  : `<span class="trace-url">${escapeHtml(meta)}</span>`
              }
              <div class="reasoning-citation-quote">${escapeHtml(String(row.text || "").slice(0, 180))}</div>
            </li>
          `;
        })
        .join("")
    : "<li>暂无评论样本</li>";

  const failedHtml = failedPlatforms.length
    ? `<div class="review-reasons">失败平台：${escapeHtml(
        failedPlatforms
          .slice(0, 8)
          .map((row) => `${row.platform}:${row.reason || "EMPTY_COMMENTS"}`)
          .join("、")
      )}</div>`
    : "";

  opinionRiskPanel.innerHTML = `
    <article class="reasoning-card">
      <div class="reasoning-head">
        <span>status=${escapeHtml(opinion.status)}</span>
        <span class="step-summary-status ${escapeHtml(riskLevel)}">${escapeHtml(riskLevel.toUpperCase())}</span>
      </div>
      <p class="reasoning-line">${escapeHtml(opinion.summary_text || "评论监测尚未执行。")}</p>
      <p class="reasoning-line">发现模式：${escapeHtml(opinion.discovery_mode || "reuse_search_results")} ${opinion.synthetic_comment_mode ? "· fallback=posts" : ""}</p>
      <p class="reasoning-line">评论覆盖：${opinion.total_comments}/${opinion.comment_target} · 账号：${opinion.unique_accounts_count} · 可疑：${opinion.suspicious_accounts_count} (${Math.round(opinion.suspicious_ratio * 100)}%)</p>
      <p class="reasoning-line">真实评论：${opinion.real_comment_count} (${Math.round(opinion.real_comment_ratio * 100)}%) · 回退样本：${opinion.synthetic_comment_count} · sidecar评论：${opinion.sidecar_comment_count}</p>
      <p class="reasoning-line">真实评论目标达成：${opinion.real_comment_target_reached ? "是" : "否"}</p>
      <div class="reasoning-steps">
        ${(opinion.risk_flags || [])
          .slice(0, 8)
          .map((code) => `<code class="step-code-chip">${escapeHtml(String(code))}</code>`)
          .join("")}
      </div>
      ${failedHtml}
      <h4>高风险账号样本</h4>
      ${accountsHtml}
      <h4>评论样本（含链接）</h4>
      <ul class="reasoning-citation-list">${commentsHtml}</ul>
    </article>
  `;
  renderRailMetricsPanel();
}

function renderClaimAnalysisPanels(claimAnalysisInput, opinionInput = currentOpinionMonitoring) {
  const normalized = normalizeClaimAnalysis(claimAnalysisInput);
  currentClaimAnalysis = normalized;
  const claims = normalized.claims || [];
  if ((!selectedClaimId || !claims.some((row) => row.claim_id === selectedClaimId)) && claims.length) {
    selectedClaimId = claims[0].claim_id;
  }
  renderClaimGraphPanel(normalized);
  renderEvidenceTracePanel(normalized);
  renderReviewQueuePanel(normalized);
  renderClaimReasoningPanel(normalized);
  renderOpinionRiskPanel(opinionInput);
  renderFailureImpactPanel();
  renderWorkflowTree();
}

function recomputeLiveRunVerdict() {
  const claims = currentClaimAnalysis.claims || [];
  if (!claims.length) {
    currentClaimAnalysis.run_verdict = "UNCERTAIN";
    return;
  }
  const counts = claims.reduce((acc, row) => {
    const verdict = String(row.verdict || "UNCERTAIN");
    acc[verdict] = Number(acc[verdict] || 0) + 1;
    return acc;
  }, {});
  if (counts.REVIEW_REQUIRED) currentClaimAnalysis.run_verdict = "REVIEW_REQUIRED";
  else if (counts.UNCERTAIN) currentClaimAnalysis.run_verdict = "UNCERTAIN";
  else if ((counts.REFUTED || 0) > (counts.SUPPORTED || 0)) currentClaimAnalysis.run_verdict = "REFUTED";
  else if (counts.SUPPORTED) currentClaimAnalysis.run_verdict = "SUPPORTED";
  else currentClaimAnalysis.run_verdict = "UNCERTAIN";
  currentClaimAnalysis.summary = counts;
}

function ensureLiveClaimRow(claimId) {
  const list = currentClaimAnalysis.claims || [];
  let row = list.find((item) => String(item.claim_id || "") === String(claimId || ""));
  if (!row) {
    row = {
      claim_id: claimId,
      text: "",
      type: "generic_claim",
      verdict: "UNCERTAIN",
      score: 0,
      gate_passed: false,
      gate_reasons: [],
      stance_summary: { support: 0, refute: 0, unclear: 0 },
      linked_evidence: [],
    };
    list.push(row);
    currentClaimAnalysis.claims = list;
  }
  return row;
}

function normalizeStepSummaries(stepSummariesInput, result = null) {
  const fromResult = Array.isArray(stepSummariesInput) ? stepSummariesInput : [];
  let base = fromResult;
  if (!base.length && result?.steps) {
    base = (result.steps || []).map((step, idx) => ({
      step_index: idx + 1,
      step_id: step.id || `step_${idx + 1}`,
      title: STEP_TITLE_MAP[step.id] || String(step.id || `step_${idx + 1}`),
      status: step.status || "unknown",
      summary_text: `${STEP_TITLE_MAP[step.id] || step.id || "步骤"} 执行状态：${step.status || "unknown"}。`,
      links: [],
      codes: [step.status === "success" ? "OK" : `STEP_${String(step.status || "unknown").toUpperCase()}`],
      metrics: {},
    }));
  }
  return base.map((item, idx) => {
    const stepId = String(item?.step_id || item?.id || `step_${idx + 1}`);
    const title = String(item?.title || STEP_TITLE_MAP[stepId] || stepId.replaceAll("_", " "));
    const status = String(item?.status || currentStepState?.[stepId]?.status || "unknown");
    const summaryText = String(item?.summary_text || item?.summary || `${title} 执行状态：${status}。`);
    const links = Array.isArray(item?.links)
      ? item.links
          .map((row) => ({
            label: String(row?.label || row?.url || ""),
            url: String(row?.url || ""),
          }))
          .filter((row) => row.url)
      : [];
    const codes = Array.isArray(item?.codes) ? item.codes.map((x) => String(x || "")).filter(Boolean) : [];
    const metrics = item?.metrics && typeof item.metrics === "object" ? item.metrics : {};
    return {
      step_index: Number(item?.step_index || idx + 1),
      step_id: stepId,
      title,
      status,
      summary_text: summaryText,
      links,
      codes,
      metrics,
    };
  });
}

function renderStepSummaryPanel(stepSummariesInput, result = null) {
  const summaries = normalizeStepSummaries(stepSummariesInput, result);
  currentStepSummaries = summaries;
  if (!stepSummaryPanel) return;
  if (!summaries.length) {
    stepSummaryPanel.innerHTML = '<div class="empty-block">暂无环节文本总结。</div>';
    return;
  }
  stepSummaryPanel.innerHTML = summaries
    .map((row) => {
      const links = row.links || [];
      const codes = row.codes || [];
      const metricsText = Object.keys(row.metrics || {}).length
        ? compactInlineText(JSON.stringify(row.metrics), 220)
        : "";
      const linksHtml = links.length
        ? links
            .slice(0, 6)
            .map(
              (link) =>
                `<a class="step-summary-link" href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(link.label || link.url)}</a>`
            )
            .join("")
        : '<span class="trace-url">无链接</span>';
      const codesHtml = codes.length
        ? codes
            .slice(0, 12)
            .map((code) => `<code class="step-code-chip">${escapeHtml(code)}</code>`)
            .join("")
        : '<code class="step-code-chip">NO_CODE</code>';
      return `
        <article class="step-summary-card">
          <div class="step-summary-head">
            <span>${Number(row.step_index)}. ${escapeHtml(row.title)}</span>
            <span class="step-summary-status ${escapeHtml(row.status)}">${escapeHtml(row.status)}</span>
          </div>
          <p class="step-summary-text">${escapeHtml(row.summary_text)}</p>
          <div class="step-summary-links">${linksHtml}</div>
          <div class="step-summary-codes">${codesHtml}</div>
          ${metricsText ? `<div class="claim-meta"><span>metrics</span><span>${escapeHtml(metricsText)}</span></div>` : ""}
        </article>
      `;
    })
    .join("");
}

function buildArticleRevisionSuggestions(resultInput) {
  const result = resultInput && typeof resultInput === "object" ? resultInput : currentRun || {};
  const claimAnalysis = normalizeClaimAnalysis(result.claim_analysis || currentClaimAnalysis);
  const acquisition = normalizeAcquisitionReport(result.acquisition_report || currentAcquisitionReport);
  const opinion = normalizeOpinionMonitoring(result.opinion_monitoring || currentOpinionMonitoring);
  const suggestionRows = [];
  const links = new Set();

  const addLink = (url) => {
    const text = String(url || "").trim();
    if (!text || !/^https?:\/\//i.test(text)) return;
    links.add(text);
  };

  (claimAnalysis.claim_reasoning || []).forEach((row) => {
    (row.citations || []).forEach((c) => addLink(c.url));
  });
  (claimAnalysis.claims || []).forEach((claim) => {
    (claim.linked_evidence || []).forEach((ev) => addLink(ev.url));
  });
  (opinion.sample_comments || []).forEach((row) => addLink(row.url));
  addLink(currentReportPayload?.source_url || "");

  const allClaims = claimAnalysis.claims || [];
  const blockedClaims = allClaims.filter((c) => !c.gate_passed);
  const totalClaims = allClaims.length;
  const reviewCount = (claimAnalysis.review_queue || []).length;

  if (totalClaims > 0 && blockedClaims.length > 0) {
    suggestionRows.push({
      title: "先修复主张门槛不足",
      text: `当前 ${blockedClaims.length}/${totalClaims} 条主张未通过门槛。建议先补充每条主张至少 2 条 Tier1/Tier2 且可追溯的外部证据，再输出最终倾向结论。`,
    });
  }

  if (Number(acquisition.external_primary_count || 0) < 8) {
    suggestionRows.push({
      title: "提升主证据密度",
      text: `当前主证据仅 ${Number(acquisition.external_primary_count || 0)} 条。建议把检索词从整句改为“实体名 + 事件动作 + 时间范围”，并优先官方/权威媒体源，目标至少提升到 8~15 条主证据。`,
    });
  }

  if (Number(acquisition.hot_fallback_count || 0) > 0) {
    suggestionRows.push({
      title: "降低热点回退污染",
      text: `检测到 hot_fallback=${Number(acquisition.hot_fallback_count || 0)}。建议把 fallback 内容仅作为背景，不参与结论；同时扩展同义词与实体别名检索，减少非相关热点混入。`,
    });
  }

  if (reviewCount > 0) {
    const reasonCodes = [...new Set((claimAnalysis.review_queue || []).flatMap((x) => (x.reasons || []).map((r) => String(r))))];
    suggestionRows.push({
      title: "按复核原因码分批补证",
      text: `复核队列 ${reviewCount} 条，优先处理原因码：${reasonCodes.slice(0, 5).join("、") || "REVIEW_REQUIRED"}。建议每个原因码单独开补证任务，避免混合检索造成噪声。`,
    });
  }

  if (Number(opinion.real_comment_ratio || 0) < 0.3) {
    suggestionRows.push({
      title: "提高真实评论占比",
      text: `真实评论占比仅 ${Math.round(Number(opinion.real_comment_ratio || 0) * 100)}%。建议优先采集带 post_id 的帖子评论，未拿到 post_id 时只做缺口标注，不用 synthetic 评论替代。`,
    });
  }

  if (String(opinion.risk_level || "unknown").toLowerCase() === "high") {
    suggestionRows.push({
      title: "增加舆情风控段落",
      text: "当前评论风险为 HIGH。建议在文章中单列“舆情操纵风险”章节，明确可疑账号样本、重复模板特征和传播链异常，避免读者误把异常热度当作事实共识。",
    });
  }

  if (!suggestionRows.length) {
    suggestionRows.push({
      title: "当前结构可用，建议做表达优化",
      text: "建议将结论段拆成“结论-证据-不确定性-下一步补证”四段式，并在每段后附 1~2 个证据链接，提升可读性与可审计性。",
    });
  }

  return {
    suggestions: suggestionRows.slice(0, 8),
    links: Array.from(links).slice(0, 12),
  };
}

function renderMyArticleSuggestionPanel(resultInput = null) {
  if (!myArticleSuggestionPanel) return;
  const { suggestions, links } = buildArticleRevisionSuggestions(resultInput);
  const linkHtml = links.length
    ? links
        .map(
          (url) =>
            `<li><a class="trace-url" href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(compactInlineText(url, 110))}</a></li>`
        )
        .join("")
    : "<li>当前无可引用链接，请先运行一次核验。</li>";
  const suggestionHtml = suggestions
    .map(
      (row) => `
      <article class="my-suggestion-item">
        <div class="my-suggestion-title">${escapeHtml(row.title)}</div>
        <p class="my-suggestion-text">${escapeHtml(row.text)}</p>
      </article>
    `
    )
    .join("");
  myArticleSuggestionPanel.innerHTML = `
    ${suggestionHtml}
    <article class="my-suggestion-item">
      <div class="my-suggestion-title">建议引用链接（来自当前文章证据链）</div>
      <ul class="my-suggestion-links">${linkHtml}</ul>
    </article>
  `;
}

function renderMyTodoPanel(resultInput = null) {
  if (!myTodoPanel) return;
  const result = resultInput && typeof resultInput === "object" ? resultInput : currentRun || {};
  const claimAnalysis = normalizeClaimAnalysis(result.claim_analysis || currentClaimAnalysis);
  const acquisition = normalizeAcquisitionReport(result.acquisition_report || currentAcquisitionReport);
  const opinion = normalizeOpinionMonitoring(result.opinion_monitoring || currentOpinionMonitoring);
  const claimCount = (claimAnalysis.claims || []).length;
  const reviewCount = (claimAnalysis.review_queue || []).length;
  const primaryCount = Number(acquisition.external_primary_count || 0);
  const realRatio = Math.round(Number(opinion.real_comment_ratio || 0) * 100);
  const verdict = String(claimAnalysis.run_verdict || result.status || "UNCERTAIN").toUpperCase();

  const notes = [];
  if (reviewCount > 0) notes.push(`复核队列 ${reviewCount} 条，建议优先处理 high priority。`);
  if (primaryCount < 8) notes.push(`主证据仅 ${primaryCount} 条，需补充官方/权威来源。`);
  if (realRatio < 30) notes.push(`真实评论占比 ${realRatio}%，评论链路可信度不足。`);
  if (!notes.length) notes.push("当前待办压力较低，可进入文稿精修阶段。");

  myTodoPanel.innerHTML = `
    <div class="my-todo-grid">
      <article class="my-todo-item">
        <span class="my-todo-label">运行结论</span>
        <span class="my-todo-value">${escapeHtml(verdict)}</span>
      </article>
      <article class="my-todo-item">
        <span class="my-todo-label">主张 / 复核</span>
        <span class="my-todo-value">${claimCount} / ${reviewCount}</span>
      </article>
      <article class="my-todo-item">
        <span class="my-todo-label">主证据 / 真实评论比</span>
        <span class="my-todo-value">${primaryCount} / ${realRatio}%</span>
      </article>
    </div>
    ${notes.map((note) => `<p class="my-todo-note">- ${escapeHtml(note)}</p>`).join("")}
  `;
}

function extractRunIdFromReportItem(item) {
  const tags = Array.isArray(item?.tags) ? item.tags : [];
  const matched = tags.find((tag) => String(tag).startsWith("run_"));
  if (!matched) return "";
  return String(matched).replace(/^run_/, "");
}

async function openReportFromHistory(reportId) {
  if (!reportId) return;
  activeReportId = reportId;
  renderReportList({ items: currentReportItems });
  try {
    const report = await getJson(`/reports/${encodeURIComponent(reportId)}`);
    const runId = extractRunIdFromReportItem(report);
    let hydratedRun = null;
    if (runId) {
      try {
        hydratedRun = await getJson(`/investigations/${encodeURIComponent(runId)}`);
      } catch {
        hydratedRun = null;
      }
    }

    if (hydratedRun?.result) {
      const result = hydratedRun.result;
      currentRun = result;
      currentEvidenceRegistry = result.evidence_registry || [];
      currentSourcePlan = normalizeSourcePlan(result.source_plan || currentSourcePlan);
      currentAcquisitionReport = normalizeAcquisitionReport(result.acquisition_report || currentAcquisitionReport);
      currentOpinionMonitoring = normalizeOpinionMonitoring(result.opinion_monitoring || currentOpinionMonitoring);
      renderSourcePlanPanel(currentSourcePlan);
      renderNoDataPanel(result.no_data_explainer);
      populateEvidenceFilters(currentEvidenceRegistry);
      renderEvidenceCards(currentEvidenceRegistry);
      renderClaimAnalysisPanels(result.claim_analysis || EMPTY_CLAIM_ANALYSIS, currentOpinionMonitoring);
      renderStepSummaryPanel(result.step_summaries || [], result);
      renderAgentPanel(result);
      renderReport(result, currentRenderedExtract);
      renderScoreCanvas(result);
      renderBreakdown(result);
      renderAnomalySummary(result);
      renderMyTodoPanel(result);
      renderMyArticleSuggestionPanel(result);
      addEvent("ui", `已回放历史报告 ${reportId}（run=${runId}）`, "info", "system");
      switchTab("report");
      return;
    }

    currentRun = {
      run_id: runId || "",
      status: report.status || "complete",
      claim_analysis: currentClaimAnalysis,
      acquisition_report: currentAcquisitionReport,
      opinion_monitoring: currentOpinionMonitoring,
    };
    if (reportContent) {
      reportContent.innerHTML = `<h2>${escapeHtml(report.title || report.id)}</h2>${report.content_html || "<p>暂无报告正文</p>"}`;
    }
    renderMyTodoPanel(currentRun);
    renderMyArticleSuggestionPanel(currentRun);
    addEvent("ui", `已加载历史报告 ${reportId}（仅报告内容）`, "info", "system");
    switchTab("report");
  } catch (e) {
    addEvent("系统提示", `加载历史报告失败：${e instanceof Error ? e.message : "unknown"}`, "error", "system");
  }
}

function renderAgentPanel(result) {
  if (!agentPanel) return;
  const platformResults = result?.agent_outputs?.platform_results || {};
  const rows = Object.entries(platformResults).map(([platform, data]) => {
    const analysis = data.small_model_analysis || {};
    const score = Math.round(Number(analysis.credibility_score || 0) * 100);
    const risks = (analysis.risk_flags || []).join(", ") || "none";
    return { platform, score, risks };
  });

  const voteRows = currentVotes.map((v) => ({
    platform: v.platform,
    score: Math.round(Number(v.score || 0) * 100),
    risks: (v.risk_flags || []).join(", ") || "none",
  }));

  const merged = voteRows.length ? voteRows : rows;
  if (!merged.length) {
    agentPanel.innerHTML = '<div class="agent-row"><span>多Agent</span><span>暂无投票</span></div>';
  } else {
    agentPanel.innerHTML = merged
      .slice(0, 12)
      .map(
        (row) => `<div class="agent-row"><span>${escapeHtml(row.platform)}</span><span>${escapeHtml(String(row.score))}% · ${escapeHtml(row.risks)}</span></div>`
      )
      .join("");
  }

  if (agentSummary) {
    const consensus = result?.agent_outputs?.consensus_points || [];
    const conflicts = result?.agent_outputs?.conflicts || [];
    agentSummary.innerHTML = `
      <div><strong>共识点：</strong>${escapeHtml(consensus.join("；") || "无")}</div>
      <div><strong>冲突点：</strong>${escapeHtml(conflicts.join("；") || "无")}</div>
      <div><strong>建议：</strong>${escapeHtml(result?.agent_outputs?.recommendation || "待补证")}</div>
    `;
  }
}

function renderFeed(search, renderedExtract = null) {
  if (!feedList) return;
  feedList.innerHTML = "";
  if (currentRun?.run_id) {
    const source = document.createElement("div");
    source.className = "view-source";
    source.textContent = `来源：当前会话 ${currentRun.run_id} 生成内容`;
    feedList.appendChild(source);
  }
  const officialEvidence = (currentEvidenceRegistry || [])
    .filter((row) => {
      const origin = String(row?.evidence_origin || "external");
      const tier = Number(row?.source_tier || 4);
      const sourceType = String(row?.source_type || "").toLowerCase();
      return (
        origin === "external" &&
        (tier <= 2 || sourceType === "official" || sourceType === "authority_media")
      );
    })
    .slice(0, 40);
  if (officialEvidence.length) {
    const officialHeader = document.createElement("div");
    officialHeader.className = "view-source";
    officialHeader.textContent = `官方/权威源证据 ${officialEvidence.length} 条（同步用于信息流展示）`;
    feedList.appendChild(officialHeader);
    officialEvidence.forEach((row, idx) => {
      const card = document.createElement("article");
      card.className = "feed-card";
      card.innerHTML = `
        <div class="title">${escapeHtml(row.source_name || `official_${idx + 1}`)} · Tier${escapeHtml(String(row.source_tier || 2))}</div>
        <div class="meta">${escapeHtml(row.validation_status || "raw")} · ${escapeHtml(row.evidence_class || "background")}</div>
        <div class="body">${escapeHtml(String(row.snippet || "").slice(0, 220) || "无摘要")}</div>
        <div class="meta">${row.url ? `<a class="trace-url" href="${escapeHtml(row.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(row.url)}</a>` : "无链接"}</div>
      `;
      feedList.appendChild(card);
    });
  }
  const data = search?.data || {};
  const rows = [];
  Object.entries(data).forEach(([platform, items]) => {
    (items || []).forEach((item, index) => rows.push({ platform, item, index }));
  });
  if (renderedExtract) {
    const diagnostics = renderedExtract.diagnostics || {};
    const renderedCard = document.createElement("article");
    renderedCard.className = "feed-card";
    renderedCard.innerHTML = `
      <div class="title">Playwright 渲染抽取</div>
      <div class="meta">${escapeHtml(renderedExtract.url || "unknown")} · 请求 ${Number(diagnostics.requests_seen || 0)} · API ${Array.isArray(renderedExtract.api_responses) ? renderedExtract.api_responses.length : 0}</div>
      <div class="body">${escapeHtml(compactInlineText(renderedExtract.visible_text || "无可见文本", 260))}</div>
      <div class="meta">${escapeHtml(summarizeRenderedFields(renderedExtract.fields || {}))}</div>
    `;
    feedList.appendChild(renderedCard);
  }
  if (!rows.length) {
    if (!renderedExtract) {
      feedList.innerHTML = "<p>暂无检索数据（后端搜索未返回内容）。</p>";
    }
    return;
  }
  rows.slice(0, 180).forEach(({ platform, item, index }) => {
    const title = item.title || item.headline || `${platform} #${index + 1}`;
    const body = item.content || item.text || item.summary || "";
    const author = item.author || item.username || "unknown";
    const card = document.createElement("article");
    card.className = "feed-card";
    card.innerHTML = `
      <div class="title">${escapeHtml(title)}</div>
      <div class="meta">${escapeHtml(platform)} · ${escapeHtml(author)}</div>
      <div class="body">${escapeHtml(String(body).slice(0, 220))}</div>
    `;
    feedList.appendChild(card);
  });
}

function renderReport(result, renderedExtract = null) {
  if (!reportContent) return;
  if (!result?.enhanced?.reasoning_chain) {
    reportContent.innerHTML = "<h2>报告详情</h2><p>暂无报告，请先发起核验。</p>";
    return;
  }

  const chain = result.enhanced.reasoning_chain || {};
  const steps = chain.steps || [];
  const riskFlags = (chain.risk_flags || []).join("、") || "无";
  const scoreBreakdown = result.score_breakdown || {};
  const dual = result.dual_profile_result || {};
  const article = result.agent_outputs?.generated_article || {};
  const sections = result.report_sections || [];
  const renderData = renderedExtract || currentRenderedExtract;
  const claimAnalysis = normalizeClaimAnalysis(result.claim_analysis || currentClaimAnalysis);
  const sourcePlan = normalizeSourcePlan(result.source_plan || currentSourcePlan);
  const acquisition = normalizeAcquisitionReport(result.acquisition_report || currentAcquisitionReport);
  const opinion = normalizeOpinionMonitoring(result.opinion_monitoring || currentOpinionMonitoring);
  currentOpinionMonitoring = opinion;
  currentAcquisitionReport = acquisition;
  const stepSummaries = normalizeStepSummaries(result.step_summaries, result);
  const claimCount = Number((claimAnalysis.claims || []).length);
  const reviewCount = Number((claimAnalysis.review_queue || []).length);
  const claimSummaryHtml = `
    <p>主张级结论：${escapeHtml(claimAnalysis.run_verdict || "UNCERTAIN")} · 主张数 ${claimCount} · 复核队列 ${reviewCount}</p>
    <p>门槛统计：${escapeHtml(JSON.stringify(claimAnalysis.summary || {}))}</p>
  `;
  const sourcePlanHtml = `
    <p>选源域：${escapeHtml(sourcePlan.domain || "general_news")} · 事件类型：${escapeHtml(sourcePlan.event_type || "generic_claim")}</p>
    <p>计划版本：${escapeHtml(sourcePlan.plan_version || "manual_default")} · 选源置信度：${Math.round(Number(sourcePlan.selection_confidence || 0) * 100)}%</p>
    <p>领域关键词：${escapeHtml((sourcePlan.domain_keywords || []).join("、") || "无")}</p>
    <p>必选源：${escapeHtml((sourcePlan.must_have_platforms || []).join("、") || "无")}</p>
    <p>实际选源：${escapeHtml((sourcePlan.selected_platforms || []).join("、") || "无")}</p>
    <p>排除源：${escapeHtml((sourcePlan.excluded_platforms || []).join("、") || "无")}</p>
    <p>证据分层：external=${acquisition.external_evidence_count}（primary=${acquisition.external_primary_count} / background=${acquisition.external_background_count} / noise=${acquisition.external_noise_count}） · derived=${acquisition.derived_evidence_count} · synthetic=${acquisition.synthetic_context_count}</p>
    <p>来源计数：native=${acquisition.native_live_count} / mediacrawler=${acquisition.mediacrawler_live_count} · 命中平台=${escapeHtml((acquisition.mediacrawler_platforms_hit || []).join("、") || "无")}</p>
    <p>sidecar降级：${escapeHtml((acquisition.mediacrawler_failures || []).slice(0, 4).map((x) => `${x.platform}:${x.reason || "unknown"}`).join("、") || "无")}</p>
    <p>回退信息：hot_fallback=${acquisition.hot_fallback_count} · must_hit=${Math.round(Number(acquisition.must_have_hit_ratio || 0) * 100)}%</p>
  `;
  const claimReasoningHtml = (claimAnalysis.claim_reasoning || [])
    .map((row) => {
      const refs = (row.citations || [])
        .slice(0, 6)
        .map((c) => `<li>${escapeHtml(c.source_name || "source")} (${escapeHtml(c.url || "no-url")})</li>`)
        .join("");
      return `
        <section class="report-step">
          <h4>Claim ${escapeHtml(row.claim_id || "unknown")} ${row.fallback ? '<code class="step-code-chip">fallback</code>' : ""}</h4>
          <p>${escapeHtml(row.conclusion_text || "")}</p>
          <p>${escapeHtml(row.risk_text || "")}</p>
          <p><strong>推理步骤：</strong>${escapeHtml((row.reasoning_steps || []).join("；") || "无")}</p>
          <p><strong>引用：</strong></p>
          <ul>${refs || "<li>无</li>"}</ul>
        </section>
      `;
    })
    .join("");
  const opinionSummaryHtml = `
    <p>状态：${escapeHtml(opinion.status || "NOT_RUN")} · 风险等级：${escapeHtml(String(opinion.risk_level || "unknown").toUpperCase())}</p>
    <p>评论覆盖：${opinion.total_comments}/${opinion.comment_target} · 账号：${opinion.unique_accounts_count} · 可疑：${opinion.suspicious_accounts_count} (${Math.round(opinion.suspicious_ratio * 100)}%)</p>
    <p>真实评论：${opinion.real_comment_count} (${Math.round(opinion.real_comment_ratio * 100)}%) · 回退样本：${opinion.synthetic_comment_count} · sidecar评论：${opinion.sidecar_comment_count}</p>
    <p>风险码：${escapeHtml((opinion.risk_flags || []).join("、") || "无")}</p>
    <p>说明：${escapeHtml(opinion.summary_text || "")}</p>
  `;
  const opinionCommentHtml = (opinion.sample_comments || [])
    .slice(0, 12)
    .map((row) => {
      const url = String(row.url || "");
      const label = `${row.platform || "platform"} · ${row.author_name || row.author_id || "anon"}`;
      return `<li>${url ? `<a class="trace-url" href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(label)}</a>` : escapeHtml(label)}：${escapeHtml(String(row.text || "").slice(0, 120))}</li>`;
    })
    .join("");

  const stepSummaryHtml = stepSummaries
    .map((row) => {
      const links = (row.links || [])
        .slice(0, 5)
        .map(
          (link) =>
            `<li><a class="trace-url" href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(link.label || link.url)}</a></li>`
        )
        .join("");
      const codes = (row.codes || [])
        .slice(0, 8)
        .map((code) => `<code class="step-code-chip">${escapeHtml(code)}</code>`)
        .join(" ");
      return `
        <section class="report-step">
          <h4>${Number(row.step_index)} · ${escapeHtml(row.title)} <span class="step-summary-status ${escapeHtml(row.status)}">${escapeHtml(row.status)}</span></h4>
          <p>${escapeHtml(row.summary_text)}</p>
          <p><strong>代码：</strong>${codes || "<code class=\"step-code-chip\">NO_CODE</code>"}</p>
          <p><strong>链接：</strong></p>
          <ul>${links || "<li>无</li>"}</ul>
        </section>
      `;
    })
    .join("");

  const stepHtml = steps
    .map(
      (step, i) => `
      <details class="report-step step-detail" data-step-index="${i + 1}">
        <summary>Step ${i + 1} · ${escapeHtml(step.stage)}</summary>
        <p><strong>推理：</strong>${escapeHtml(step.reasoning || "")}</p>
        <p><strong>结论：</strong>${escapeHtml(step.conclusion || "")}</p>
        <p><strong>证据：</strong>${escapeHtml((step.evidence || []).join("；") || "无")}</p>
        <p><strong>疑点：</strong>${escapeHtml((step.concerns || []).join("；") || "无")}</p>
      </details>
    `
    )
    .join("");

  const sectionHtml = sections
    .slice(0, 8)
    .map(
      (sec) => `
      <section class="report-step">
        <h4>${escapeHtml(sec.title || "章节")}</h4>
        <p>${escapeHtml(sec.content_markdown || "")}</p>
        <p><strong>证据引用：</strong>${escapeHtml((sec.evidence_ids || []).join("、") || "无")}</p>
      </section>
    `
    )
    .join("");

  const renderedSectionHtml = renderData
    ? `
    <hr />
    <h3>网页渲染抽取</h3>
    <p>URL：${escapeHtml(renderData.url || "")}</p>
    <p>抓取时间：${escapeHtml(renderData.captured_at || "")}</p>
    <p>DOM稳定：${renderData?.diagnostics?.dom_stable ? "是" : "否"} · 请求数：${Number(renderData?.diagnostics?.requests_seen || 0)} · API JSON：${Array.isArray(renderData?.api_responses) ? renderData.api_responses.length : 0}</p>
    <p>字段摘要：${escapeHtml(summarizeRenderedFields(renderData.fields || {}))}</p>
    <p>可见文本预览：${escapeHtml(compactInlineText(renderData.visible_text || "", 520))}</p>
  `
    : "";

  reportContent.innerHTML = `
    <h2>动态证据报告</h2>
    <p>来源会话：${escapeHtml(result.run_id || "unknown")}（与急救核验界面同步）</p>
    <p>关键词：${escapeHtml(result.search?.keyword || result.request?.keyword || "")}</p>
    <p>最终可信度：${Number(chain.final_score || 0).toFixed(2)} · 等级：${escapeHtml(chain.final_level || "UNKNOWN")}</p>
    <p>风险标记：${escapeHtml(riskFlags)}</p>
    <p>运行状态：${escapeHtml(result.status || "unknown")}</p>
    <p>双配置评分：TOB ${Math.round(Number(dual?.tob_result?.score || 0) * 100)}% / TOG ${Math.round(Number(dual?.tog_result?.score || 0) * 100)}%</p>
    <hr />
    <h3>自动选源规划</h3>
    ${sourcePlanHtml}
    ${claimSummaryHtml}
    ${renderedSectionHtml}
    <hr />
    <h3>环节文本总结</h3>
    ${stepSummaryHtml || "<p>暂无环节文本总结</p>"}
    <hr />
    ${stepHtml}
    <hr />
    <h3>多 Agent 综合</h3>
    <p>${escapeHtml(result.agent_outputs?.recommendation || "暂无")}</p>
    <p>共识：${escapeHtml((result.agent_outputs?.consensus_points || []).join("；") || "无")}</p>
    <p>冲突：${escapeHtml((result.agent_outputs?.conflicts || []).join("；") || "无")}</p>
    <hr />
    <h3>成文摘要</h3>
    <p><strong>${escapeHtml(article.title || "")}</strong></p>
    <p>${escapeHtml(article.lead || "")}</p>
    <p>${escapeHtml(article.body_markdown || "")}</p>
    <hr />
    <h3>模板章节</h3>
    ${sectionHtml}
    <hr />
    <h3>主张级深度分析</h3>
    ${claimReasoningHtml || "<p>暂无主张级深度分析。</p>"}
    <hr />
    <h3>评论与水军风险</h3>
    ${opinionSummaryHtml}
    <p><strong>评论样本链接：</strong></p>
    <ul>${opinionCommentHtml || "<li>无</li>"}</ul>
    <hr />
    <h3>评分拆解</h3>
    <p>${escapeHtml(JSON.stringify(scoreBreakdown, null, 2))}</p>
  `;
  renderFailureImpactPanel();
}

function buildNarrative(result, renderedExtract = null) {
  const chain = result?.enhanced?.reasoning_chain || {};
  const claimAnalysis = normalizeClaimAnalysis(result?.claim_analysis || currentClaimAnalysis);
  const sourcePlan = normalizeSourcePlan(result?.source_plan || currentSourcePlan);
  const acquisition = normalizeAcquisitionReport(result?.acquisition_report || currentAcquisitionReport);
  const opinion = normalizeOpinionMonitoring(result?.opinion_monitoring || currentOpinionMonitoring);
  const stepSummaries = normalizeStepSummaries(result?.step_summaries, result);
  const lines = [
    "# Aletheia 核验报告",
    "",
    `- Run ID: ${result?.run_id || ""}`,
    `- 关键词: ${result?.search?.keyword || ""}`,
    `- 可信度: ${Number(chain.final_score || 0).toFixed(2)}`,
    `- 可信等级: ${chain.final_level || "UNKNOWN"}`,
    `- 运行状态: ${result?.status || "unknown"}`,
    `- 主张级结论: ${claimAnalysis.run_verdict || "UNCERTAIN"}`,
    `- 主张数量: ${(claimAnalysis.claims || []).length}`,
    `- 复核队列: ${(claimAnalysis.review_queue || []).length}`,
    "",
  ];

  if (renderedExtract) {
    lines.push("## 网页渲染抽取");
    lines.push(`- URL: ${renderedExtract.url || ""}`);
    lines.push(`- 抓取时间: ${renderedExtract.captured_at || ""}`);
    lines.push(`- DOM稳定: ${renderedExtract?.diagnostics?.dom_stable ? "是" : "否"}`);
    lines.push(`- 请求数: ${Number(renderedExtract?.diagnostics?.requests_seen || 0)}`);
    lines.push(`- API JSON 数量: ${Array.isArray(renderedExtract?.api_responses) ? renderedExtract.api_responses.length : 0}`);
    lines.push(`- 字段摘要: ${summarizeRenderedFields(renderedExtract.fields || {})}`);
    lines.push(`- 可见文本预览: ${compactInlineText(renderedExtract.visible_text || "", 360)}`);
    lines.push("");
  }

  (result?.report_sections || []).forEach((sec) => {
    lines.push(`## ${sec.title || "章节"}`);
    lines.push(sec.content_markdown || "");
    lines.push("");
  });

  lines.push("## 环节文本总结");
  stepSummaries.forEach((row) => {
    lines.push(`### ${Number(row.step_index)}. ${row.title}`);
    lines.push(`- status: ${row.status}`);
    lines.push(`- summary: ${row.summary_text || ""}`);
    lines.push(`- codes: ${(row.codes || []).join(" | ") || "none"}`);
    const links = (row.links || []).map((link) => `${link.label || link.url}: ${link.url}`);
    lines.push(`- links: ${links.join(" | ") || "none"}`);
    lines.push("");
  });

  lines.push("## 主张级分析");
  (claimAnalysis.claims || []).forEach((row, idx) => {
    lines.push(`### Claim ${idx + 1} (${row.claim_id || ""})`);
    lines.push(`- text: ${row.text || ""}`);
    lines.push(`- verdict: ${row.verdict || "UNCERTAIN"}`);
    lines.push(`- score: ${Number(row.score || 0).toFixed(4)}`);
    lines.push(`- gate_passed: ${Boolean(row.gate_passed)}`);
    lines.push(`- gate_reasons: ${(row.gate_reasons || []).join(" | ") || "none"}`);
    lines.push(`- evidence_ids: ${(row.evidence_ids || []).join(" | ") || "none"}`);
    lines.push("");
  });

  lines.push("## 自动选源规划");
  lines.push(`- event_type: ${sourcePlan.event_type || "generic_claim"}`);
  lines.push(`- domain: ${sourcePlan.domain || "general_news"}`);
  lines.push(`- plan_version: ${sourcePlan.plan_version || "manual_default"}`);
  lines.push(`- selection_confidence: ${Math.round(Number(sourcePlan.selection_confidence || 0) * 100)}%`);
  lines.push(`- domain_keywords: ${(sourcePlan.domain_keywords || []).join(" | ") || "none"}`);
  lines.push(`- must_have_platforms: ${(sourcePlan.must_have_platforms || []).join(" | ") || "none"}`);
  lines.push(`- selected_platforms: ${(sourcePlan.selected_platforms || []).join(" | ") || "none"}`);
  lines.push(`- excluded_platforms: ${(sourcePlan.excluded_platforms || []).join(" | ") || "none"}`);
  lines.push(`- risk_notes: ${(sourcePlan.risk_notes || []).join(" | ") || "none"}`);
  lines.push("");

  lines.push("## 采集质量统计");
  lines.push(`- external_evidence_count: ${acquisition.external_evidence_count}`);
  lines.push(`- derived_evidence_count: ${acquisition.derived_evidence_count}`);
  lines.push(`- synthetic_context_count: ${acquisition.synthetic_context_count}`);
  lines.push(`- external_primary_count: ${acquisition.external_primary_count}`);
  lines.push(`- external_background_count: ${acquisition.external_background_count}`);
  lines.push(`- external_noise_count: ${acquisition.external_noise_count}`);
  lines.push(`- native_live_count: ${acquisition.native_live_count}`);
  lines.push(`- mediacrawler_live_count: ${acquisition.mediacrawler_live_count}`);
  lines.push(`- mediacrawler_platforms_hit: ${(acquisition.mediacrawler_platforms_hit || []).join(" | ") || "none"}`);
  lines.push(
    `- mediacrawler_failures: ${(acquisition.mediacrawler_failures || [])
      .slice(0, 8)
      .map((row) => `${row.platform}:${row.reason || "unknown"}`)
      .join(" | ") || "none"}`
  );
  lines.push(`- hot_fallback_count: ${acquisition.hot_fallback_count}`);
  lines.push(`- must_have_hit_ratio: ${Math.round(Number(acquisition.must_have_hit_ratio || 0) * 100)}%`);
  lines.push("");

  lines.push("## 评论与水军风险");
  lines.push(`- status: ${opinion.status}`);
  lines.push(`- risk_level: ${String(opinion.risk_level || "unknown").toUpperCase()}`);
  lines.push(`- comment_coverage: ${opinion.total_comments}/${opinion.comment_target}`);
  lines.push(`- real_comment_count: ${opinion.real_comment_count}`);
  lines.push(`- real_comment_ratio: ${Math.round(Number(opinion.real_comment_ratio || 0) * 100)}%`);
  lines.push(`- real_comment_target_reached: ${Boolean(opinion.real_comment_target_reached)}`);
  lines.push(`- synthetic_comment_count: ${opinion.synthetic_comment_count}`);
  lines.push(`- sidecar_comment_count: ${opinion.sidecar_comment_count}`);
  lines.push(`- unique_accounts: ${opinion.unique_accounts_count}`);
  lines.push(`- suspicious_accounts: ${opinion.suspicious_accounts_count}`);
  lines.push(`- suspicious_ratio: ${Math.round(Number(opinion.suspicious_ratio || 0) * 100)}%`);
  lines.push(`- risk_flags: ${(opinion.risk_flags || []).join(" | ") || "none"}`);
  lines.push(`- summary: ${opinion.summary_text || ""}`);
  (opinion.sample_comments || []).slice(0, 10).forEach((row, idx) => {
    lines.push(`- sample_${idx + 1}: ${row.platform || "platform"} | ${row.author_name || row.author_id || "anon"} | ${row.url || "no-url"} | ${compactInlineText(row.text || "", 120)}`);
  });
  lines.push("");

  lines.push("## 主张级深度分析");
  (claimAnalysis.claim_reasoning || []).forEach((row) => {
    lines.push(`### Claim ${row.claim_id || "unknown"}${row.fallback ? " (fallback)" : ""}`);
    lines.push(`- conclusion: ${row.conclusion_text || ""}`);
    lines.push(`- risk: ${row.risk_text || ""}`);
    lines.push(`- reasoning_steps: ${(row.reasoning_steps || []).join(" | ") || "none"}`);
    const refs = (row.citations || [])
      .map((c) => `${c.source_name || "source"}:${c.url || "no-url"}`)
      .join(" | ");
    lines.push(`- citations: ${refs || "none"}`);
    lines.push("");
  });

  if ((claimAnalysis.review_queue || []).length) {
    lines.push("## 复核队列");
    (claimAnalysis.review_queue || []).forEach((item) => {
      lines.push(`- ${item.claim_id || "unknown"} [${item.priority || "medium"}]: ${(item.reasons || []).join(" | ")}`);
    });
    lines.push("");
  }

  lines.push("## 推理步骤");
  (chain.steps || []).forEach((step, i) => {
    lines.push(`### Step ${i + 1} ${step.stage}`);
    lines.push(`推理: ${step.reasoning || ""}`);
    lines.push(`结论: ${step.conclusion || ""}`);
    lines.push(`证据: ${(step.evidence || []).join("；") || "无"}`);
    lines.push("");
  });

  lines.push("## 证据卡片");
  (result?.evidence_registry || []).slice(0, 100).forEach((ev) => {
    lines.push(
      `- [${ev.source_name}] (${ev.evidence_class || "background"}) ${ev.snippet} (${ev.url || "no-url"})`
    );
  });

  return lines.join("\n");
}

async function ensureMermaid() {
  if (mermaidLoaded) return window.mermaid;
  const mermaidModule = await import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs");
  mermaidModule.default.initialize({ startOnLoad: false, theme: "dark" });
  mermaidLoaded = true;
  window.mermaid = mermaidModule.default;
  return mermaidModule.default;
}

async function renderMermaid(result) {
  if (!mermaidBox) return;
  const steps = result?.steps || [];
  if (!steps.length) {
    mermaidBox.textContent = "暂无步骤数据";
    return;
  }
  const nodes = steps.map((s, i) => `S${i}["${String(s.id || `step${i + 1}`).replaceAll('"', "")}"]`);
  const links = steps.slice(0, -1).map((_, i) => `S${i} --> S${i + 1}`);
  const code = `flowchart LR\n${nodes.join("\n")}\n${links.join("\n")}`;

  try {
    const mermaid = await ensureMermaid();
    const { svg } = await mermaid.render(`chart_${Date.now()}`, code);
    mermaidBox.innerHTML = svg;
  } catch (e) {
    mermaidBox.textContent = `Mermaid 渲染失败: ${e instanceof Error ? e.message : "unknown"}`;
  }
}

function renderScoreCanvas(result) {
  if (!scoreCanvas) return;
  const ctx = scoreCanvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, scoreCanvas.width, scoreCanvas.height);

  const enhanced = Number(result?.enhanced?.reasoning_chain?.final_score || 0);
  const cross = Number(result?.credibility?.credibility_score || 0);
  const agent = Number(result?.agent_outputs?.overall_credibility || 0);
  const tob = Number(result?.dual_profile_result?.tob_result?.score || 0);
  const tog = Number(result?.dual_profile_result?.tog_result?.score || 0);
  const values = [enhanced, cross, agent, tob, tog];
  const labels = ["8步", "跨平台", "多Agent", "TOB", "TOG"];
  const colors = ["#60a5fa", "#34d399", "#f59e0b", "#f472b6", "#a78bfa"];

  const baseY = scoreCanvas.height - 28;
  const barW = 68;
  const gap = 24;
  const startX = 26;

  ctx.fillStyle = "#9db4d4";
  ctx.font = "12px Inter";
  ctx.fillText("可信度对比", 12, 18);

  values.forEach((v, i) => {
    const bh = Math.max(2, Math.round(v * 165));
    const x = startX + i * (barW + gap);
    const y = baseY - bh;
    ctx.fillStyle = colors[i];
    ctx.fillRect(x, y, barW, bh);
    ctx.fillStyle = "#dbeafe";
    ctx.fillText(`${Math.round(v * 100)}%`, x + 14, y - 8);
    ctx.fillStyle = "#a9c2df";
    ctx.fillText(labels[i], x + 16, baseY + 14);
  });
}

function renderBreakdown(result) {
  if (!breakdownBox) return;
  const scoreBreakdown = result?.score_breakdown || {};
  const noData = result?.no_data_explainer;
  const lines = [
    `platform_coverage_score: ${Number(scoreBreakdown.platform_coverage_score || 0).toFixed(4)}`,
    `evidence_specificity_score: ${Number(scoreBreakdown.evidence_specificity_score || 0).toFixed(4)}`,
    `model_consensus_score: ${Number(scoreBreakdown.model_consensus_score || 0).toFixed(4)}`,
    `synthesis_score: ${Number(scoreBreakdown.synthesis_score || 0).toFixed(4)}`,
    `evidence_count: ${Number(scoreBreakdown.evidence_count || 0)}`,
  ];
  if (noData) {
    lines.push("---");
    lines.push(`reason_code: ${noData.reason_code}`);
    lines.push(`coverage_ratio: ${Math.round(Number(noData.coverage_ratio || 0) * 100)}%`);
  }
  breakdownBox.textContent = lines.join("\n");
}

function renderAnomalySummary(result) {
  if (!anomalySummary) return;
  const sourceLine = `来源会话：${result?.run_id || "unknown"}`;
  const opinion = normalizeOpinionMonitoring(result?.opinion_monitoring || currentOpinionMonitoring);
  const anomalies = result?.credibility?.anomalies || [];
  if (!anomalies.length && String(opinion.risk_level || "unknown").toLowerCase() === "low") {
    anomalySummary.textContent = `${sourceLine}\n传播异常摘要：暂无明显异常。\n评论风险：LOW（${opinion.total_comments}/${opinion.comment_target}）`;
    return;
  }
  const lines = anomalies.slice(0, 6).map((a, i) => {
    const type = a.type || a.name || `anomaly_${i + 1}`;
    const desc = a.description || a.detail || JSON.stringify(a);
    return `- ${type}: ${String(desc).slice(0, 120)}`;
  });
  lines.push(
    `- opinion_risk: ${String(opinion.risk_level || "unknown").toUpperCase()} | comments=${opinion.total_comments}/${opinion.comment_target} | suspicious=${Math.round(Number(opinion.suspicious_ratio || 0) * 100)}%`
  );
  anomalySummary.textContent = `${sourceLine}\n传播异常摘要：\n${lines.join("\n")}`;
}

function switchTab(tab) {
  if (!tab) return;
  tabButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tab));
  tabPanes.forEach((pane) => pane.classList.toggle("active", pane.id === `tab-${tab}`));
  if (tab === "my") {
    renderMyTodoPanel(currentRun);
    renderMyArticleSuggestionPanel(currentRun);
  }
  addEvent("ui", `切换到 ${tab} 视图`, "info", "system");
}

function switchTabAndFocus(tab, targetEl) {
  switchTab(tab);
  if (!targetEl) return;
  window.requestAnimationFrame(() => {
    targetEl.scrollIntoView({ behavior: "smooth", block: "start", inline: "nearest" });
  });
}

function jumpToPreviewStage() {
  switchTabAndFocus("verify", previewPanel || claimInput);
}

function jumpToExecutionStage() {
  switchTabAndFocus("verify", stepTimeline || workflowTree || streamPanel || claimInput);
}

function renderReportList(listResponse) {
  if (!reportList) return;
  const items = listResponse?.items || [];
  currentReportItems = items;
  if (!items.length) {
    reportList.innerHTML = '<div class="report-item"><span>暂无报告</span><span>--</span></div>';
    return;
  }
  reportList.innerHTML = "";
  items.slice(0, 8).forEach((item) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `report-item-btn${activeReportId && activeReportId === item.id ? " active" : ""}`;
    row.dataset.reportId = String(item.id || "");
    const runId = extractRunIdFromReportItem(item);
    row.dataset.runId = runId;
    row.innerHTML = `<span>${escapeHtml(item.title || item.id)}</span><span>${Math.round(Number(item.credibility_score || 0) * 100)}% · ${escapeHtml(item.status || "complete")}</span>`;
    reportList.appendChild(row);
  });
}

async function loadRecentReports() {
  try {
    const list = await getJson("/reports/?page=1&page_size=10");
    renderReportList(list);
    renderMyTodoPanel(currentRun);
    renderMyArticleSuggestionPanel(currentRun);
  } catch (e) {
    addEvent("reports.list", `拉取失败：${e instanceof Error ? e.message : "unknown"}`, "error");
  }
}

async function checkBackend() {
  try {
    const health = await fetch(HEALTH_URL).then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    });
    setBackendStatus(`后端在线 v${health.version}`);
  } catch {
    setBackendStatus("后端离线");
  }
}

function getHealthPollIntervalMs() {
  return document.visibilityState === "hidden" ? 22000 : 8000;
}

function getReportsPollIntervalMs() {
  if (runInProgress) return 45000;
  return document.visibilityState === "hidden" ? 60000 : 25000;
}

function stopBackgroundPolling() {
  if (healthPollTimer) {
    window.clearTimeout(healthPollTimer);
    healthPollTimer = null;
  }
  if (reportsPollTimer) {
    window.clearTimeout(reportsPollTimer);
    reportsPollTimer = null;
  }
}

function startBackgroundPolling() {
  stopBackgroundPolling();

  const healthTick = async () => {
    await checkBackend();
    healthPollTimer = window.setTimeout(healthTick, getHealthPollIntervalMs());
  };
  const reportsTick = async () => {
    if (!runInProgress) {
      await loadRecentReports();
    }
    reportsPollTimer = window.setTimeout(reportsTick, getReportsPollIntervalMs());
  };

  healthPollTimer = window.setTimeout(healthTick, getHealthPollIntervalMs());
  reportsPollTimer = window.setTimeout(reportsTick, getReportsPollIntervalMs());
}

function closeActiveEventSource() {
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }
}

function consumeRunStream(runId) {
  return new Promise((resolve, reject) => {
    closeActiveEventSource();
    const source = new EventSource(`${API_BASE}/investigations/${runId}/stream`);
    activeEventSource = source;
    let done = false;
    let lastHeartbeatLogAt = 0;

    const finish = (ok, error) => {
      if (done) return;
      done = true;
      source.close();
      if (activeEventSource === source) activeEventSource = null;
      if (ok) resolve();
      else reject(error || new Error("stream failed"));
    };

    source.addEventListener("heartbeat", (event) => {
      let data = {};
      try {
        data = JSON.parse(event.data || "{}");
      } catch {
        data = {};
      }
      appendDebugLine("heartbeat", data);
      const status = data.status || currentRun?.status || "running";
      setStatus(`运行中 · ${status} · 心跳`);
      const now = Date.now();
      if (now - lastHeartbeatLogAt > 20000) {
        addEvent("stream", `INFO: 运行心跳 (${status})`, "info", "system");
        lastHeartbeatLogAt = now;
      }
    });

    source.addEventListener("run_started", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("run_started", data);
      currentRun = { ...(currentRun || {}), run_id: data.run_id || runId, status: "running" };
      upsertWorkflowNode("root", {
        status: "running",
        detail: `run=${data.run_id || runId} · 结论=${currentClaimAnalysis.run_verdict || "UNCERTAIN"}`,
        payload: data,
      });
      addEvent("Aletheia", `任务已启动：${data.run_id || runId}`, "info", "assistant");
      updateSegmentCard({
        conclusion: `任务 ${data.run_id || runId} 已启动，正在拉取证据...`,
      });
      renderWorkflowTree();
    });

    source.addEventListener("step_update", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("step_update", data);
      updateStepStatus(data.step_id, data.status || "running", {
        elapsed_ms: Number(data.elapsed_ms || 0),
      });
      upsertWorkflowStepNode(data.step_id, data.status || "running", Number(data.elapsed_ms || 0));
      const nextReasoning = trimUnique(
        currentSegmentState?.reasoning || [],
        `${data.step_id || "step"}：${data.status || "running"}${data.elapsed_ms ? `（${(Number(data.elapsed_ms) / 1000).toFixed(1)}s）` : ""}`
      );
      updateSegmentCard({ reasoning: nextReasoning });
      setStatus(`运行中 · ${data.step_id || "step"} · ${data.status || "running"}`);
      addEvent(
        "Aletheia",
        `步骤 ${data.step_id || "unknown"}：${data.status || "running"}${data.elapsed_ms ? `（${(Number(data.elapsed_ms) / 1000).toFixed(1)}s）` : ""}`,
        data.status === "success" ? "success" : "info",
        "assistant"
      );
      renderWorkflowTree();
    });

    source.addEventListener("evidence_found", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("evidence_found", data);
      const card = data.evidence_card || {};
      const nextEvidence = trimUnique(
        currentSegmentState?.evidence || [],
        `${card.source_name || "source"}：${String(card.snippet || "").slice(0, 80)}`
      );
      updateSegmentCard({ evidence: nextEvidence });
      currentEvidenceEventCount += 1;
      upsertWorkflowNode("search-evidence-stream", {
        parentId: "search",
        label: "实时证据流",
        status: "running",
        detail: `累计 ${currentEvidenceEventCount} · 最新 ${card.source_name || "source"} · ${String(card.stance || "unknown")}`,
        payload: {
          count: currentEvidenceEventCount,
          source_name: card.source_name || "",
          stance: card.stance || "unknown",
          url: card.url || card.original_url || "",
        },
        nodeType: "stream",
      });
      if (currentEvidenceEventCount <= 12) {
        upsertWorkflowNode(`search-evidence-${currentEvidenceEventCount}`, {
          parentId: "search-evidence-stream",
          label: `${card.source_name || "source"} #${currentEvidenceEventCount}`,
          status: "partial",
          detail: compactInlineText(card.snippet || card.title || "无摘要", 100),
          payload: {
            url: card.url || card.original_url || "",
            evidence_origin: card.evidence_origin || "external",
            evidence_class: card.evidence_class || "background",
            source_tier: card.source_tier || "",
          },
          nodeType: "evidence",
        });
      }
      if (currentEvidenceEventCount <= 6) {
        addEvent(
          "Aletheia",
          `证据命中 #${currentEvidenceEventCount} · ${card.source_name || "source"}\n${String(card.snippet || "").slice(0, 120)}`,
          "success",
          "assistant"
        );
      } else if (currentEvidenceEventCount === 7) {
        addEvent("Aletheia", "更多证据已收录到证据卡片区域，可在证据报告页筛选查看。", "info", "assistant");
      }
      renderWorkflowTree();
    });

    source.addEventListener("platform_fallback_applied", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("platform_fallback_applied", data);
      const added = (data.added_platforms || []).join("、") || "none";
      const reason = data.reason || "coverage_low";
      const tip = `已触发平台回退：${added}（${reason}）`;
      const nextAdvice = trimUnique(currentSegmentState?.recommendation || [], tip);
      updateSegmentCard({ recommendation: nextAdvice });
      addEvent("系统提示", tip, "warning", "system");
      upsertWorkflowNode(`search-fallback-${workflowEventSeq++}`, {
        parentId: "search",
        label: "平台回退",
        status: "partial",
        detail: tip,
        payload: data,
        nodeType: "fallback",
      });
      renderWorkflowTree();
    });

    source.addEventListener("agent_vote", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("agent_vote", data);
      currentVotes.push(data);
      renderAgentPanel({ agent_outputs: { platform_results: {} } });
      const voteText = `${data.platform || "agent"}：${Math.round(Number(data.score || 0) * 100)}%`;
      const nextAdvice = trimUnique(currentSegmentState?.recommendation || [], `投票结果 ${voteText}`);
      updateSegmentCard({ recommendation: nextAdvice });
      addEvent(
        "Aletheia",
        `Agent投票 · ${data.platform || "agent"}：${Math.round(Number(data.score || 0) * 100)}%`,
        "info",
        "assistant"
      );
    });

    source.addEventListener("warning", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("warning", data);
      if (data.code === "MANUAL_TAKEOVER_WAITING") {
        const tip = data.platform
          ? `${data.platform} 触发验证墙，等待人工接管...`
          : "触发验证墙，等待人工接管...";
        const nextReasoning = trimUnique(currentSegmentState?.reasoning || [], tip);
        updateSegmentCard({ reasoning: nextReasoning });
      }
      const nextAdvice = trimUnique(currentSegmentState?.recommendation || [], `警告：${data.message || data.code || "warning"}`);
      updateSegmentCard({ recommendation: nextAdvice });
      addEvent("系统提示", data.message || data.code || "warning", "warning", "system");
      upsertWorkflowNode(`report-warning-${workflowEventSeq++}`, {
        parentId: "report",
        label: "系统警告",
        status: "partial",
        detail: String(data.message || data.code || "warning"),
        payload: data,
        nodeType: "warning",
      });
      renderWorkflowTree();
    });

    source.addEventListener("manual_takeover_waiting", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("manual_takeover_waiting", data);
      const msg = data.message || `${data.platform || "平台"} 需要人工接管`;
      const nextReasoning = trimUnique(currentSegmentState?.reasoning || [], msg);
      updateSegmentCard({ reasoning: nextReasoning });
      addEvent("系统提示", msg, "warning", "system");
      upsertWorkflowNode(`search-manual-${String(data.platform || "platform")}`, {
        parentId: "search",
        label: `${String(data.platform || "platform")} 人工接管`,
        status: "partial",
        detail: msg,
        payload: data,
        nodeType: "manual",
      });
      renderWorkflowTree();
    });

    source.addEventListener("platform_status", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("platform_status", data);
      const platform = data.platform || "unknown";
      currentPlatformStatusMap[platform] = {
        platform,
        status: data.status || "unknown",
        reason_code: data.reason_code || "N/A",
        items_collected: Number(data.items_collected || 0),
        impact_on_verdict: data.impact_on_verdict || "unknown",
      };
      const statusText = `${platform}: ${data.status || "unknown"} · ${data.reason_code || "N/A"} · ${data.items_collected || 0}条 · impact=${data.impact_on_verdict || "unknown"}`;
      const nextReasoning = trimUnique(currentSegmentState?.reasoning || [], statusText);
      updateSegmentCard({ reasoning: nextReasoning });
      renderFailureImpactPanel();
      if (data.status === "circuit_open") {
        addEvent("系统提示", `平台短路：${statusText}`, "warning", "system");
      }
      upsertWorkflowNode("search-platform-status", {
        parentId: "search",
        label: "平台采集状态",
        status: "running",
        detail: `已回传 ${Object.keys(currentPlatformStatusMap || {}).length} 个平台`,
        payload: { count: Object.keys(currentPlatformStatusMap || {}).length },
        nodeType: "summary",
      });
      upsertWorkflowNode(`search-platform-${platform}`, {
        parentId: "search-platform-status",
        label: platform,
        status: data.status || "unknown",
        detail: `${data.reason_code || "N/A"} · items=${data.items_collected || 0} · impact=${data.impact_on_verdict || "unknown"}`,
        payload: currentPlatformStatusMap[platform],
        nodeType: "platform",
      });
      renderWorkflowTree();
    });

    source.addEventListener("data_progress", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("data_progress", data);
      const valid = Number(data.valid_evidence_count || 0);
      const target = Number(data.target_valid_evidence_min || 0);
      const platformsWithData = Number(data.platforms_with_data || 0);
      const liveEvidence = Number(data.live_evidence_count || 0);
      const cachedEvidence = Number(data.cached_evidence_count || 0);
      const elapsedSec = Number(data.elapsed_ms || 0) / 1000;
      setStatus(
        `采集中 · 证据 ${valid}/${target} · 实时 ${liveEvidence} · 缓存 ${cachedEvidence} · 平台 ${platformsWithData} · ${elapsedSec.toFixed(1)}s`
      );
      const nextEvidence = trimUnique(
        currentSegmentState?.evidence || [],
        `有效证据 ${valid}/${target}（实时 ${liveEvidence} / 缓存 ${cachedEvidence}），已覆盖平台 ${platformsWithData}`
      );
      updateSegmentCard({ evidence: nextEvidence });
      upsertWorkflowNode("search-progress", {
        parentId: "search",
        label: "采集进度",
        status: "running",
        detail: `valid ${valid}/${target} · live ${liveEvidence} · cached ${cachedEvidence} · platforms ${platformsWithData} · ${(elapsedSec || 0).toFixed(1)}s`,
        payload: data,
        nodeType: "progress",
      });
      renderWorkflowTree();
    });

    source.addEventListener("source_plan_ready", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("source_plan_ready", data);
      currentSourcePlan = normalizeSourcePlan(data);
      renderSourcePlanPanel(currentSourcePlan);
      upsertWorkflowNode("source-plan-summary", {
        parentId: "source",
        label: "选源计划",
        status: "success",
        detail: `${currentSourcePlan.domain} · selected ${(currentSourcePlan.selected_platforms || []).length} · conf=${Math.round(Number(currentSourcePlan.selection_confidence || 0) * 100)}%`,
        payload: currentSourcePlan,
        nodeType: "summary",
      });
      (currentSourcePlan.selected_platforms || []).forEach((platform) => {
        upsertWorkflowNode(`source-platform-${platform}`, {
          parentId: "source-plan-summary",
          label: String(platform),
          status: "success",
          detail: "selected",
          payload: { platform, source: "source_plan", class: "selected" },
          nodeType: "platform",
        });
      });
      (currentSourcePlan.excluded_platforms || []).slice(0, 8).forEach((platform) => {
        upsertWorkflowNode(`source-excluded-${platform}`, {
          parentId: "source-plan-summary",
          label: String(platform),
          status: "partial",
          detail: "excluded",
          payload: { platform, source: "source_plan", class: "excluded" },
          nodeType: "platform",
        });
      });
      (currentSourcePlan.official_selected_platforms || []).forEach((platform) => {
        upsertWorkflowNode(`source-official-${platform}`, {
          parentId: "source-plan-summary",
          label: `${String(platform)} (official)`,
          status: "success",
          detail: "official_floor_selected",
          payload: { platform, source: "source_plan", class: "official" },
          nodeType: "platform",
        });
      });
      const conf = Math.round(Number(currentSourcePlan.selection_confidence || 0) * 100);
      addEvent(
        "Aletheia",
        `自动选源完成：${currentSourcePlan.domain}（选中 ${(currentSourcePlan.selected_platforms || []).length} 平台，conf=${conf}%）`,
        "info",
        "assistant"
      );
      renderWorkflowTree();
    });

    source.addEventListener("mediacrawler_status", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("mediacrawler_status", data);
      currentMediaCrawlerStatus = {
        ...currentMediaCrawlerStatus,
        enabled: Boolean(data.enabled),
        enabled_by_request:
          data.enabled_by_request === undefined ? null : Boolean(data.enabled_by_request),
        ack: Boolean(data.ack),
        platforms: Array.isArray(data.platforms) ? data.platforms.map((x) => String(x)) : [],
        timeout_sec: Number(data.timeout_sec || 120),
      };
      renderSourcePlanPanel(currentSourcePlan);
      upsertWorkflowNode("search-sidecar-status", {
        parentId: "search",
        label: "MediaCrawler 状态",
        status: currentMediaCrawlerStatus.enabled ? "running" : "partial",
        detail: `${currentMediaCrawlerStatus.enabled ? "enabled" : "disabled"} · ack=${currentMediaCrawlerStatus.ack ? "yes" : "no"} · platforms=${(currentMediaCrawlerStatus.platforms || []).length}`,
        payload: currentMediaCrawlerStatus,
        nodeType: "sidecar",
      });
      addEvent(
        "Aletheia",
        `MediaCrawler ${currentMediaCrawlerStatus.enabled ? "启用" : "关闭"} · ack=${currentMediaCrawlerStatus.ack ? "yes" : "no"} · platforms=${(currentMediaCrawlerStatus.platforms || []).join("、") || "无"}`,
        currentMediaCrawlerStatus.enabled ? "info" : "warning",
        "assistant"
      );
      renderWorkflowTree();
    });

    source.addEventListener("mediacrawler_platform_done", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("mediacrawler_platform_done", data);
      const platform = String(data.platform || "unknown");
      currentMediaCrawlerPlatformMap[platform] = {
        platform,
        triggered: Boolean(data.triggered),
        trigger_reason: String(data.trigger_reason || ""),
        native_count: Number(data.native_count || 0),
        mediacrawler_count: Number(data.mediacrawler_count || 0),
        merged_count: Number(data.merged_count || 0),
        task_id: String(data.task_id || ""),
      };
      if (Number(data.mediacrawler_count || 0) > 0) {
        addEvent(
          "Aletheia",
          `${platform} sidecar增强：native ${Number(data.native_count || 0)} + sidecar ${Number(data.mediacrawler_count || 0)} -> merged ${Number(data.merged_count || 0)}`,
          "success",
          "assistant"
        );
      }
      upsertWorkflowNode("search-sidecar-status", {
        parentId: "search",
        label: "MediaCrawler 状态",
        status: "running",
        detail: `平台回执 ${(Object.keys(currentMediaCrawlerPlatformMap || {}).length || 0)} 个`,
        payload: currentMediaCrawlerStatus,
        nodeType: "sidecar",
      });
      upsertWorkflowNode(`search-sidecar-${platform}`, {
        parentId: "search-sidecar-status",
        label: platform,
        status: Number(data.mediacrawler_count || 0) > 0 ? "success" : "partial",
        detail: `native ${Number(data.native_count || 0)} + sidecar ${Number(data.mediacrawler_count || 0)} -> ${Number(data.merged_count || 0)}`,
        payload: currentMediaCrawlerPlatformMap[platform],
        nodeType: "platform",
      });
      renderWorkflowTree();
    });

    source.addEventListener("mediacrawler_degraded", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("mediacrawler_degraded", data);
      const stage = String(data.stage || "search");
      const impact = data.impact_scope && typeof data.impact_scope === "object" ? data.impact_scope : {};
      const lostPosts = Number(impact.lost_posts || 0);
      const lostComments = Number(impact.lost_comments || 0);
      const msg = `sidecar降级 ${data.platform || "unknown"}(${stage}): ${data.reason || "MEDIACRAWLER_DEGRADED"} · lost_posts=${lostPosts} · lost_comments=${lostComments}`;
      const nextAdvice = trimUnique(currentSegmentState?.recommendation || [], msg);
      updateSegmentCard({ recommendation: nextAdvice });
      addEvent("系统提示", msg, "warning", "system");
      upsertWorkflowNode(`search-sidecar-degraded-${String(data.platform || "unknown")}-${stage}`, {
        parentId: "search-sidecar-status",
        label: `${String(data.platform || "unknown")} degraded`,
        status: "failed",
        detail: `${data.reason || "MEDIACRAWLER_DEGRADED"} · lost_posts=${lostPosts} · lost_comments=${lostComments}`,
        payload: data,
        nodeType: "degrade",
      });
      renderWorkflowTree();
    });

    source.addEventListener("claim_extracted", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("claim_extracted", data);
      const row = ensureLiveClaimRow(data.claim_id || "");
      row.text = data.text || row.text;
      row.type = data.type || row.type;
      upsertWorkflowNode(`claim-${row.claim_id || "unknown"}`, {
        parentId: "claim",
        label: `主张 ${row.claim_id || "unknown"}`,
        status: "running",
        detail: compactInlineText(row.text || "待补全", 90),
        payload: row,
        nodeType: "claim",
      });
      recomputeLiveRunVerdict();
      renderClaimAnalysisPanels(currentClaimAnalysis);
      addEvent("Aletheia", `主张拆解：${String(row.text || "").slice(0, 72)}`, "info", "assistant");
      renderWorkflowTree();
    });

    source.addEventListener("claim_evidence_linked", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("claim_evidence_linked", data);
      const row = ensureLiveClaimRow(data.claim_id || "");
      row.stance_summary = {
        support: Number(data.support_count || 0),
        refute: Number(data.refute_count || 0),
        unclear: Number(data.evidence_count || 0) - Number(data.support_count || 0) - Number(data.refute_count || 0),
      };
      row.evidence_count = Number(data.evidence_count || 0);
      upsertWorkflowNode(`claim-${row.claim_id || "unknown"}`, {
        parentId: "claim",
        label: `主张 ${row.claim_id || "unknown"}`,
        status: "running",
        detail: `support=${row.stance_summary.support} · refute=${row.stance_summary.refute} · linked=${row.evidence_count}`,
        payload: row,
        nodeType: "claim",
      });
      recomputeLiveRunVerdict();
      renderClaimAnalysisPanels(currentClaimAnalysis);
      renderWorkflowTree();
    });

    source.addEventListener("claim_verdict_ready", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("claim_verdict_ready", data);
      const row = ensureLiveClaimRow(data.claim_id || "");
      row.verdict = data.verdict || "UNCERTAIN";
      row.gate_passed = Boolean(data.gate_passed);
      row.score = Number(data.score || 0);
      row.gate_reasons = Array.isArray(data.gate_reasons) ? data.gate_reasons : [];
      upsertWorkflowNode(`claim-${row.claim_id || "unknown"}`, {
        parentId: "claim",
        label: `主张 ${row.claim_id || "unknown"}`,
        status: row.gate_passed ? "success" : "partial",
        detail: `${row.verdict} · score=${Math.round(row.score * 100)}% · gate=${row.gate_passed ? "pass" : "blocked"}`,
        payload: row,
        nodeType: "claim",
      });
      recomputeLiveRunVerdict();
      renderClaimAnalysisPanels(currentClaimAnalysis);
      const nextReasoning = trimUnique(
        currentSegmentState?.reasoning || [],
        `claim ${row.claim_id}: ${row.verdict} · gate=${row.gate_passed ? "pass" : "blocked"}`
      );
      updateSegmentCard({ reasoning: nextReasoning });
      renderWorkflowTree();
    });

    source.addEventListener("review_queue_updated", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("review_queue_updated", data);
      currentClaimAnalysis.review_queue = Array.isArray(data.items) ? data.items : [];
      renderClaimAnalysisPanels(currentClaimAnalysis);
      const qCount = Number(data.queue_count || 0);
      const nextAdvice = trimUnique(
        currentSegmentState?.recommendation || [],
        qCount > 0 ? `复核队列更新：${qCount} 条` : "复核队列清空"
      );
      updateSegmentCard({ recommendation: nextAdvice });
      upsertWorkflowNode("claim-review-queue", {
        parentId: "claim",
        label: "复核队列",
        status: qCount > 0 ? "partial" : "success",
        detail: qCount > 0 ? `${qCount} 条待复核` : "队列为空",
        payload: { queue_count: qCount, items: currentClaimAnalysis.review_queue.slice(0, 10) },
        nodeType: "queue",
      });
      renderWorkflowTree();
    });

    source.addEventListener("claim_reasoning_ready", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("claim_reasoning_ready", data);
      const nextReasoning = trimUnique(
        currentSegmentState?.reasoning || [],
        `claim reasoning ready: ${data.claim_id || "unknown"} (refs=${Number(data.citation_count || 0)})`
      );
      updateSegmentCard({ reasoning: nextReasoning });
      const claimId = String(data.claim_id || "unknown");
      upsertWorkflowNode(`claim-reasoning-${claimId}`, {
        parentId: `claim-${claimId}`,
        label: "推理文本",
        status: Number(data.citation_count || 0) > 0 ? "success" : "partial",
        detail: `citations=${Number(data.citation_count || 0)}${data.fallback ? " · fallback" : ""}`,
        payload: data,
        nodeType: "reasoning",
      });
      renderWorkflowTree();
    });

    source.addEventListener("opinion_monitoring_ready", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("opinion_monitoring_ready", data);
      currentOpinionMonitoring = normalizeOpinionMonitoring({
        ...currentOpinionMonitoring,
        ...data,
      });
      renderOpinionRiskPanel(currentOpinionMonitoring);
      renderFailureImpactPanel();
      const message = `评论监测：${Number(data.total_comments || 0)}/${Number(data.comment_target || 0)} · suspicious=${Math.round(Number(data.suspicious_ratio || 0) * 100)}% · ${String(data.risk_level || "unknown").toUpperCase()}`;
      const nextReasoning = trimUnique(currentSegmentState?.reasoning || [], message);
      updateSegmentCard({ reasoning: nextReasoning });
      addEvent("Aletheia", message, "info", "assistant");
      upsertWorkflowNode("opinion-summary", {
        parentId: "opinion",
        label: "评论监测结果",
        status: String(data.risk_level || "unknown").toLowerCase() === "high" ? "partial" : "success",
        detail: `${Number(data.total_comments || 0)}/${Number(data.comment_target || 0)} · real=${Number(data.real_comment_count || 0)} · suspicious=${Math.round(Number(data.suspicious_ratio || 0) * 100)}%`,
        payload: data,
        nodeType: "summary",
      });
      renderWorkflowTree();
    });

    source.addEventListener("run_completed", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("run_completed", data);
      if (currentRun && typeof currentRun === "object") currentRun.status = data.status || "completed";
      upsertWorkflowNode("root", {
        status: "success",
        detail: `run=${currentRun?.run_id || runId} · 结论=${currentClaimAnalysis.run_verdict || "UNCERTAIN"}`,
      });
      upsertWorkflowNode("report-final", {
        parentId: "report",
        label: "执行完成",
        status: "success",
        detail: `status=${data.status || "complete"}`,
        payload: data,
        nodeType: "result",
      });
      renderWorkflowTree();
      addEvent("Aletheia", `任务完成，状态=${data.status || "complete"}`, "success", "assistant");
      finish(true);
    });

    source.addEventListener("run_failed", (event) => {
      const data = JSON.parse(event.data || "{}");
      appendDebugLine("run_failed", data);
      if (currentRun && typeof currentRun === "object") currentRun.status = "failed";
      upsertWorkflowNode("root", {
        status: "failed",
        detail: `run=${currentRun?.run_id || runId} · error=${data.error || "unknown"}`,
      });
      upsertWorkflowNode("report-final", {
        parentId: "report",
        label: "执行失败",
        status: "failed",
        detail: String(data.error || "unknown"),
        payload: data,
        nodeType: "result",
      });
      renderWorkflowTree();
      updateSegmentCard({
        conclusion: `任务失败：${data.error || "unknown"}`,
      });
      if (currentSegmentCard) currentSegmentCard.dataset.level = "error";
      addEvent("系统提示", `任务失败：${data.error || "unknown"}`, "error", "system");
      finish(false, new Error(data.error || "run_failed"));
    });

    source.onerror = () => {
      if (done) return;
      appendDebugLine("stream_error", { run_id: runId });
      upsertWorkflowNode("report-stream-warning", {
        parentId: "report",
        label: "流式连接异常",
        status: "partial",
        detail: "切换为结果拉取模式",
        payload: { run_id: runId },
        nodeType: "warning",
      });
      renderWorkflowTree();
      addEvent("系统提示", "流式连接异常，转为拉取最终结果。", "warning", "system");
      finish(true);
    };

    setTimeout(() => {
      if (!done) {
        upsertWorkflowNode("report-stream-timeout", {
          parentId: "report",
          label: "流式超时",
          status: "partial",
          detail: "已切换为结果拉取",
          payload: { run_id: runId, timeout_sec: 120 },
          nodeType: "warning",
        });
        renderWorkflowTree();
        addEvent("系统提示", "流式等待超时，转为结果拉取。", "warning", "system");
        finish(true);
      }
    }, 120000);
  });
}

async function executeConfirmedRun({
  claim,
  keyword,
  sourceUrl,
  platforms,
  tuning,
  confirmedClaims,
  confirmedPlatforms,
  previewId,
}) {
  runInProgress = true;
  setPreviewStatus("success", "已确认并进入执行阶段");
  runButton.disabled = true;
  if (previewConfirmButton) previewConfirmButton.disabled = true;
  if (previewRefreshButton) previewRefreshButton.disabled = true;
  setStatus("调度中");
  updateSegmentCard({
    conclusion: "请求已提交，等待后端调度...",
    reasoning: ["任务入队中"],
    recommendation: ["你可以打开调试面板查看原始 SSE 事件"],
  });

  let renderedExtractTask = Promise.resolve(null);
  try {
    addEvent(
      "系统提示",
      `本次阈值：有效证据≥${tuning.target_valid_evidence_min}，实时证据≥${tuning.live_evidence_target}，平台覆盖≥${tuning.min_platforms_with_data}`,
      "info",
      "system"
    );
    appendDebugLine("run_request", {
      claim: claim.slice(0, 160),
      preview_id: previewId || "",
      confirmed_claim_count: confirmedClaims.length,
      confirmed_platform_count: confirmedPlatforms.length,
    });

    const accepted = await postJson("/investigations/run", {
      claim,
      keyword,
      platforms,
      mode: currentMode,
      audience_profile: "both",
      report_template_id: "deep-research-report",
      limit_per_platform: 80,
      target_valid_evidence_min: tuning.target_valid_evidence_min,
      live_evidence_target: tuning.live_evidence_target,
      quality_mode: "balanced",
      max_runtime_sec: tuning.max_runtime_sec,
      min_platforms_with_data: tuning.min_platforms_with_data,
      free_source_only: true,
      source_strategy: "auto",
      source_profile: "stable_mixed_v1",
      strict_pipeline: "staged_strict",
      use_mediacrawler: true,
      mediacrawler_platforms: ["weibo", "xiaohongshu", "douyin", "zhihu"],
      mediacrawler_timeout_sec: 120,
      enable_cached_evidence: true,
      phase1_target_valid_evidence: tuning.phase1_target_valid_evidence,
      phase1_deadline_sec: tuning.phase1_deadline_sec,
      phase1_live_rescue_timeout_sec: 12,
      max_concurrent_platforms_fast: tuning.max_concurrent_platforms_fast,
      max_concurrent_platforms_fill: tuning.max_concurrent_platforms_fill,
      enable_opinion_monitoring: true,
      allow_synthetic_comments: false,
      opinion_comment_target: 120,
      opinion_comment_limit_per_post: 40,
      opinion_max_posts_per_platform: 2,
      opinion_max_platforms: 6,
      confirmed_preview_id: previewId || null,
      confirmed_claims: confirmedClaims.length ? confirmedClaims : null,
      confirmed_platforms: confirmedPlatforms.length ? confirmedPlatforms : null,
    });

    const runId = accepted.run_id;
    currentRun = { ...(currentRun || {}), run_id: runId, status: "running", search: { keyword } };
    upsertWorkflowNode("run_started", {
      parentId: "preview",
      label: "run started",
      status: "success",
      detail: `run=${runId}`,
      payload: { run_id: runId, preview_id: previewId || "" },
      nodeType: "event",
    });
    upsertWorkflowNode("root", {
      status: "running",
      detail: `run=${runId} · 结论=${currentClaimAnalysis.run_verdict || "UNCERTAIN"}`,
      payload: { run_id: runId },
    });
    renderWorkflowTree();
    renderRailSearchPanel();
    appendDebugLine("run_accepted", accepted);
    setStatus(`运行中 ${runId}`);
    addEvent("系统提示", `run_id=${runId}`, "info", "system");

    if (sourceUrl) {
      addEvent("系统提示", `附加任务：页面渲染抽取 ${sourceUrl}`, "info", "system");
      renderedExtractTask = postJson("/multiplatform/playwright-rendered-extract", {
        url: sourceUrl,
        critical_selector: "body",
        schema: DEFAULT_RENDER_SCHEMA,
        api_url_keyword: "",
        max_api_items: 20,
        visible_text_limit: 18000,
        html_limit: 250000,
        headless: true,
      })
        .then((payload) => {
          const normalized = normalizeRenderedExtract(payload);
          if (!normalized) return null;
          currentRenderedExtract = normalized;
          addEvent(
            "系统提示",
            `渲染抽取完成：请求 ${Number(normalized?.diagnostics?.requests_seen || 0)}，API ${Array.isArray(normalized?.api_responses) ? normalized.api_responses.length : 0}`,
            "success",
            "system"
          );
          return normalized;
        })
        .catch((e) => {
          addEvent("系统提示", `渲染抽取失败：${e instanceof Error ? e.message : "unknown"}`, "warning", "system");
          return null;
        });
    }

    await consumeRunStream(runId);

    const [result, renderedExtract] = await Promise.all([getJson(`/investigations/${runId}`), renderedExtractTask]);
    currentRun = result;
    currentEvidenceRegistry = result.evidence_registry || [];
    currentSourcePlan = normalizeSourcePlan(result.source_plan || currentSourcePlan);
    currentAcquisitionReport = normalizeAcquisitionReport(result.acquisition_report || currentAcquisitionReport);
    currentOpinionMonitoring = normalizeOpinionMonitoring(
      result.opinion_monitoring || currentOpinionMonitoring
    );
    if (renderedExtract) {
      currentRenderedExtract = renderedExtract;
    }
    renderRailSearchPanel();
    renderRailMetricsPanel();

    renderFeed(result.search || {}, currentRenderedExtract);
    renderSourcePlanPanel(currentSourcePlan);
    renderNoDataPanel(result.no_data_explainer);
    populateEvidenceFilters(currentEvidenceRegistry);
    renderEvidenceCards(currentEvidenceRegistry);
    renderClaimAnalysisPanels(
      result.claim_analysis || EMPTY_CLAIM_ANALYSIS,
      currentOpinionMonitoring
    );
    renderStepSummaryPanel(result.step_summaries || [], result);
    renderAgentPanel(result);
    renderReport(result, currentRenderedExtract);
    renderMyTodoPanel(result);
    renderMyArticleSuggestionPanel(result);
    await renderMermaid(result);
    renderScoreCanvas(result);
    renderBreakdown(result);
    renderAnomalySummary(result);
    pushRunSummaryToChat(result);

    currentNarrative = buildNarrative(result, currentRenderedExtract);
    currentReportPayload = {
      title: `Aletheia核验报告-${result.search?.keyword || keyword}-${new Date().toLocaleDateString("zh-CN")}`,
      content: currentNarrative,
      run_id: runId,
      run_at: new Date().toISOString(),
      source_url: sourceUrl || undefined,
      source_plan: currentSourcePlan,
      claim_analysis: result.claim_analysis || currentClaimAnalysis,
      opinion_monitoring: result.opinion_monitoring || currentOpinionMonitoring,
      step_summaries: result.step_summaries || currentStepSummaries || [],
    };

    try {
      const saved = await postJson("/reports/generate-from-run", {
        run_id: runId,
        tags: ["investigation", `mode_${currentMode}`],
      });
      addEvent("系统提示", `报告已写入：${saved.id}`, "success", "system");
    } catch (e) {
      addEvent("系统提示", `报告写入失败：${e instanceof Error ? e.message : "unknown"}`, "error", "system");
    }

    setStatus(`完成 (${result.status || "complete"})`);
    addEvent("系统提示", "任务结束", "success", "system");
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown";
    if (message.includes("PREVIEW_EXPIRED")) {
      setStatus("预分析已过期");
      setPreviewStatus("degraded", "预分析过期，请重新生成后再执行");
      if (previewStatusBadge) {
        previewStatusBadge.classList.remove("ready", "running");
        previewStatusBadge.classList.add("degraded");
        previewStatusBadge.textContent = "预分析过期";
      }
      addEvent("系统提示", "预分析已过期，请点击“重新预分析”。", "warning", "system");
    } else {
      setStatus("失败");
      addEvent("系统提示", `执行失败：${message}`, "error", "system");
    }
    appendDebugLine("run_error", { error: message });
    updateSegmentCard({ conclusion: `执行失败：${message}` });
    if (currentSegmentCard) currentSegmentCard.dataset.level = "error";
  } finally {
    runInProgress = false;
    runButton.disabled = false;
    if (previewRefreshButton) previewRefreshButton.disabled = false;
    if (previewConfirmButton) previewConfirmButton.disabled = false;
    await loadRecentReports();
    renderFailureImpactPanel();
  }
}

async function runAudit() {
  const claim = claimInput?.value.trim() || "";
  if (!claim || previewInProgress || runInProgress) return;

  previewInProgress = true;
  runButton.disabled = true;
  if (previewConfirmButton) previewConfirmButton.disabled = true;
  if (previewRefreshButton) previewRefreshButton.disabled = true;
  setStatus("预分析中");
  resetStateForRun();
  addEvent("user", claim, "user", "user");
  addEvent("系统提示", "开始预分析：解析意图与选源计划", "info", "system");
  setPreviewStatus("running", "解析输入意图...");
  upsertWorkflowNode("preview-input", {
    parentId: "preview",
    label: "input_received",
    status: "running",
    detail: compactInlineText(claim, 120),
    payload: { claim: claim.slice(0, 200) },
    nodeType: "event",
  });
  renderWorkflowTree();

  const keyword = keywordInput?.value.trim() || deriveKeyword(claim);
  const sourceUrl = sourceUrlInput?.value.trim() || "";
  const platforms = getPlatforms();
  const tuning = buildInvestigationTuning(keyword, platforms, sourceUrl);

  try {
    const previewRaw = await postJson("/investigations/preview", {
      claim,
      keyword,
      platforms,
      mode: currentMode,
      source_strategy: "auto",
    });
    const preview = normalizePreviewPayload(previewRaw);
    currentPreview = preview;
    pendingExecutionContext = { claim, keyword, sourceUrl, platforms, tuning };
    currentSourcePlan = normalizeSourcePlan(preview.source_plan || currentSourcePlan);
    renderSourcePlanPanel(currentSourcePlan);
    renderPreviewPanel(preview);
    jumpToPreviewStage();

    const statusLabel = preview.status === "ready" ? "success" : "partial";
    setPreviewStatus(preview.status, `preview=${preview.preview_id} · claims=${preview.claims_draft.length}`);
    upsertWorkflowNode("preview-input", {
      parentId: "preview",
      label: "input_received",
      status: "success",
      detail: `keyword=${keyword || "未设置"}`,
      payload: { keyword, platforms },
      nodeType: "event",
    });
    upsertWorkflowNode("intent_preview_ready", {
      parentId: "preview",
      label: "intent_preview_ready",
      status: statusLabel,
      detail: `status=${preview.status} · conf=${Math.round(Number(preview.source_plan.selection_confidence || 0) * 100)}%`,
      payload: {
        preview_id: preview.preview_id,
        status: preview.status,
        risk_notes: preview.risk_notes,
      },
      nodeType: "event",
    });
    renderWorkflowTree();

    if (preview.status === "degraded") {
      addEvent("系统提示", "预分析降级完成：可直接确认执行。", "warning", "system");
    } else {
      addEvent("系统提示", "预分析完成：请确认主张草案与平台后执行。", "success", "system");
    }
    setStatus("待确认执行");
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown";
    currentPreview = normalizePreviewPayload({
      status: "degraded",
      intent_summary: "预分析失败，已切换为规则降级。你仍可直接确认执行。",
      event_type: "generic_claim",
      domain: "general_news",
      claims_draft: [],
      source_plan: {
        event_type: "generic_claim",
        domain: "general_news",
        selected_platforms: platforms,
        must_have_platforms: [],
        candidate_platforms: platforms,
        excluded_platforms: [],
        plan_version: "fallback_manual",
        selection_confidence: 0.2,
      },
      risk_notes: ["PREVIEW_REQUEST_FAILED"],
      fallback_reason: message,
    });
    pendingExecutionContext = { claim, keyword, sourceUrl, platforms, tuning };
    renderPreviewPanel(currentPreview);
    jumpToPreviewStage();
    setPreviewStatus("degraded", "预分析失败，允许手动确认执行");
    upsertWorkflowNode("intent_preview_ready", {
      parentId: "preview",
      label: "intent_preview_ready",
      status: "failed",
      detail: compactInlineText(message, 120),
      payload: { error: message },
      nodeType: "event",
    });
    renderWorkflowTree();
    setStatus("预分析失败（可继续）");
    addEvent("系统提示", `预分析失败：${message}`, "warning", "system");
    appendDebugLine("preview_error", { error: message });
  } finally {
    previewInProgress = false;
    runButton.disabled = false;
    if (previewRefreshButton) previewRefreshButton.disabled = false;
    if (previewConfirmButton) previewConfirmButton.disabled = false;
  }
}

async function confirmAndRunAudit() {
  if (previewInProgress || runInProgress) return;
  if (!pendingExecutionContext || !currentPreview) {
    addEvent("系统提示", "请先生成预分析。", "warning", "system");
    return;
  }
  const confirmedClaims = getConfirmedClaimsFromPreview();
  const confirmedPlatforms = getConfirmedPlatformsFromPreview();

  upsertWorkflowNode("claims_confirmed", {
    parentId: "preview",
    label: "claims_confirmed",
    status: "success",
    detail: `claims=${confirmedClaims.length || 1}`,
    payload: { confirmed_claims: confirmedClaims.slice(0, 8) },
    nodeType: "event",
  });
  upsertWorkflowNode("source_plan_confirmed", {
    parentId: "preview",
    label: "source_plan_confirmed",
    status: "success",
    detail: `platforms=${confirmedPlatforms.length || pendingExecutionContext.platforms.length}`,
    payload: { confirmed_platforms: confirmedPlatforms.slice(0, 12) },
    nodeType: "event",
  });
  renderWorkflowTree();
  addEvent("系统提示", "已确认预分析，开始执行正式核验。", "info", "system");

  // 隐藏预分析面板，回到初始界面
  if (previewPanel) previewPanel.classList.add("hidden");

  jumpToExecutionStage();

  await executeConfirmedRun({
    ...pendingExecutionContext,
    confirmedClaims,
    confirmedPlatforms,
    previewId: currentPreview.preview_id,
  });
}

async function exportReport(format) {
  if (!currentNarrative) {
    addEvent("系统提示", "暂无可导出报告", "warning", "system");
    return;
  }
  try {
    const payload = {
      title: currentReportPayload?.title || "Aletheia-report",
      content: currentNarrative,
      run_at: new Date().toISOString(),
      run_id: currentRun?.run_id || "",
      keyword: currentRun?.search?.keyword || "",
      source_url: currentReportPayload?.source_url || "",
      source_plan: currentRun?.source_plan || currentSourcePlan || null,
      evidence_registry: currentRun?.evidence_registry || [],
      score_breakdown: currentRun?.score_breakdown || {},
      claim_analysis: currentRun?.claim_analysis || currentClaimAnalysis || EMPTY_CLAIM_ANALYSIS,
      opinion_monitoring: currentRun?.opinion_monitoring || currentOpinionMonitoring || EMPTY_OPINION_MONITORING,
      step_summaries: currentRun?.step_summaries || currentStepSummaries || [],
      rendered_extract: currentRenderedExtract || null,
    };
    const res = await postJson("/reports/export", { format, payload });
    const raw = atob(res.content_base64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
    const blob = new Blob([bytes], { type: res.mime_type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.file_name;
    a.click();
    URL.revokeObjectURL(url);
    addEvent("系统提示", `导出成功：${res.file_name}`, "success", "system");
  } catch (e) {
    addEvent("系统提示", `导出失败：${e instanceof Error ? e.message : "unknown"}`, "error", "system");
  }
}

modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    modeButtons.forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    currentMode = button.dataset.mode || "dual";
    const label = button.textContent || "双工模式";
    if (selectedMode) selectedMode.textContent = label;
    if (modeBadge) modeBadge.textContent = label;
    renderRailSearchPanel();
  });
});

if (toggleTools) toggleTools.addEventListener("click", () => toolsMenu.classList.toggle("hidden"));
if (toggleDebug && debugDrawer) {
  toggleDebug.addEventListener("click", () => {
    debugDrawer.classList.toggle("hidden");
  });
}
if (runButton) runButton.addEventListener("click", runAudit);
if (previewRefreshButton) previewRefreshButton.addEventListener("click", runAudit);
if (previewConfirmButton) previewConfirmButton.addEventListener("click", confirmAndRunAudit);
if (exportMd) exportMd.addEventListener("click", () => exportReport("md"));
if (exportJson) exportJson.addEventListener("click", () => exportReport("json"));
if (claimInput) claimInput.addEventListener("input", () => renderRailSearchPanel());
if (keywordInput) keywordInput.addEventListener("input", () => renderRailSearchPanel());
if (sourceUrlInput) sourceUrlInput.addEventListener("input", () => renderRailSearchPanel());
if (platformSelect) platformSelect.addEventListener("change", () => renderRailSearchPanel());
if (evidencePlatformFilter) evidencePlatformFilter.addEventListener("change", () => renderEvidenceCards(currentEvidenceRegistry));
if (evidenceStanceFilter) evidenceStanceFilter.addEventListener("change", () => renderEvidenceCards(currentEvidenceRegistry));
if (evidenceTierFilter) evidenceTierFilter.addEventListener("change", () => renderEvidenceCards(currentEvidenceRegistry));
if (evidenceOriginFilter) evidenceOriginFilter.addEventListener("change", () => renderEvidenceCards(currentEvidenceRegistry));
if (evidenceClassFilter) evidenceClassFilter.addEventListener("change", () => renderEvidenceCards(currentEvidenceRegistry));
if (reportList) {
  reportList.addEventListener("click", async (event) => {
    const target = event.target instanceof Element ? event.target.closest(".report-item-btn") : null;
    if (!target) return;
    const reportId = target.getAttribute("data-report-id");
    if (!reportId) return;
    await openReportFromHistory(reportId);
  });
}
if (claimGraphPanel) {
  claimGraphPanel.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target.closest(".claim-card") : null;
    if (!target) return;
    const claimId = target.getAttribute("data-claim-id");
    if (!claimId) return;
    selectedClaimId = claimId;
    renderClaimAnalysisPanels(currentClaimAnalysis);
  });
}
if (previewPlatformsEditor) {
  previewPlatformsEditor.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (!target.matches("input[data-preview-platform]")) return;
    const chip = target.closest(".preview-platform-chip");
    if (!chip) return;
    if (target.checked) chip.classList.add("selected");
    else chip.classList.remove("selected");
  });
}
if (workflowTree) {
  workflowTree.addEventListener("click", (event) => {
    const toggle = event.target instanceof Element ? event.target.closest(".workflow-toggle") : null;
    if (toggle) {
      const nodeId = toggle.getAttribute("data-node-id");
      if (!nodeId) return;
      if (collapsedWorkflowNodeIds.has(nodeId)) collapsedWorkflowNodeIds.delete(nodeId);
      else collapsedWorkflowNodeIds.add(nodeId);
      renderWorkflowTree();
      return;
    }
    const target = event.target instanceof Element ? event.target.closest(".workflow-node") : null;
    if (!target) return;
    const nodeId = target.getAttribute("data-node-id");
    if (!nodeId) return;
    selectedWorkflowNodeId = nodeId;
    renderWorkflowTree();
  });
}

tabButtons.forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

window.addEventListener("error", (event) => {
  addEvent("系统提示", `前端异常: ${event.message}`, "error", "system");
});

window.addEventListener("beforeunload", () => {
  stopBackgroundPolling();
  closeActiveEventSource();
});

document.addEventListener("visibilitychange", () => {
  startBackgroundPolling();
});

resetStateForRun();
addEvent("Aletheia", "控制台就绪。你可以直接输入主张，我会以对话流形式返回证据链与推理过程。", "info", "assistant");
setStatus("待命");
setBackendStatus("后端检测中...");
checkBackend();
loadRecentReports();
startBackgroundPolling();
