const presets = {
  openai: { baseUrl: "https://api.openai.com/v1", models: ["gpt-5.4", "gpt-5.3", "gpt-4.1"] },
  openrouter: { baseUrl: "https://openrouter.ai/api/v1", models: ["openai/gpt-5", "anthropic/claude-3.7-sonnet"] },
  deepseek: { baseUrl: "https://api.deepseek.com", models: ["deepseek-chat", "deepseek-reasoner"] },
  moonshot: { baseUrl: "https://api.moonshot.cn/v1", models: ["kimi-k2-0711-preview", "kimi-latest"] },
  aliyun_bailian: { baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen3.6-plus", "qwen-plus", "qwen-turbo"] },
  custom: { baseUrl: "", models: [] },
};

const state = {
  currentTaskId: "",
  currentWorkdir: "",
  currentTaskStatus: "",
  currentLifecycle: null,
  review: null,
  results: null,
  reviewRenderItems: [],
  reviewPage: 1,
  reviewPageSize: 12,
  resultsSearch: "",
  resultsScope: "all",
  resultsSort: "recent_desc",
  resultsPinLatest: true,
  resultsView: "gallery",
  resultsSearchTimer: null,
  reviewStatusText: "",
  reviewSaveTimer: null,
  reviewSaveInFlight: false,
  reviewSaveSeq: 0,
  currentLogsCount: 0,
  activeTab: "status",
  onlyNeedsAttention: false,
  pollTimer: null,
  pollInFlight: false,
  lastTaskRefreshAt: 0,
  taskListRequestSeq: 0,
  taskItems: [],
  taskRowHeight: 210,
  taskOverscan: 4,
  taskRenderRange: { start: 0, end: 0 },
  searchTimer: null,
  workdirTimer: null,
  statusTiming: null,
  statusClockTimer: null,
  taskScrollRaf: 0,
  lastTaskSignature: "",
  creatingTask: false,
  pendingResumeTaskId: "",
  pendingDownloadLaunch: false,
  pendingRetrySessionDir: "",
  agentFailure: null,
  graphDebug: null,
  renderCache: { metrics: "", execution: "", graphDebug: "", download: "", entry: "", confirm: "", queue: "", logs: "" },
};

const $ = (id) => document.getElementById(id);

const els = {
  provider: $("provider"),
  providerCustom: $("providerCustom"),
  providerHint: $("providerHint"),
  baseUrl: $("baseUrl"),
  modelSelect: $("modelSelect"),
  modelManual: $("modelManual"),
  workdir: $("workdir"),
  apiKey: $("apiKey"),
  request: $("request"),
  requestTemplateHint: $("requestTemplateHint"),
  requestTemplateChips: $("requestTemplateChips"),
  requestTemplateGrid: $("requestTemplateGrid"),
  modelSuggestion: $("modelSuggestion"),
  taskInputAdvanced: $("taskInputAdvanced"),
  advancedSummaryText: $("advancedSummaryText"),
  btnTest: $("btnTest"),
  btnRun: $("btnRun"),
  btnResume: $("btnResume"),
  queuePills: $("queuePills"),
  taskStatusFilter: $("taskStatusFilter"),
  taskSort: $("taskSort"),
  taskSearch: $("taskSearch"),
  taskList: $("taskList"),
  taskListSpacer: $("taskListSpacer"),
  taskListWindow: $("taskListWindow"),
  workspaceTitle: $("workspaceTitle"),
  workspaceSubtitle: $("workspaceSubtitle"),
  workspaceActionsBar: $("workspaceActionsBar"),
  statusPill: $("statusPill"),
  taskIdPill: $("taskIdPill"),
  updatedPill: $("updatedPill"),
  workspaceStagePill: $("workspaceStagePill"),
  primaryMessage: $("primaryMessage"),
  overallTitle: $("overallTitle"),
  overallValue: $("overallValue"),
  overallFill: $("overallFill"),
  overallDetail: $("overallDetail"),
  metricGrid: $("metricGrid"),
  executionBox: $("executionBox"),
  graphDebugPanel: $("graphDebugPanel"),
  graphDebugPill: $("graphDebugPill"),
  graphDebugBox: $("graphDebugBox"),
  confirmWrap: $("confirmWrap"),
  downloadPhase: $("downloadPhase"),
  downloadBox: $("downloadBox"),
  entryStatusPill: $("entryStatusPill"),
  entryBox: $("entryBox"),
  reviewStatusPill: $("reviewStatusPill"),
  reviewSummaryPills: $("reviewSummaryPills"),
  reviewSearch: $("reviewSearch"),
  reviewScope: $("reviewScope"),
  reviewSort: $("reviewSort"),
  reviewPageSize: $("reviewPageSize"),
  reviewStatus: $("reviewStatus"),
  reviewList: $("reviewList"),
  reviewPageLabel: $("reviewPageLabel"),
  btnStartSelectedDownload: $("btnStartSelectedDownload"),
  resultsStatusPill: $("resultsStatusPill"),
  resultsSummary: $("resultsSummary"),
  resultsList: $("resultsList"),
  btnRefreshResults: $("btnRefreshResults"),
  resultsFilterStatusPill: $("resultsFilterStatusPill"),
  resultsSearch: $("resultsSearch"),
  resultsScope: $("resultsScope"),
  resultsSort: $("resultsSort"),
  resultsPinLatest: $("resultsPinLatest"),
  resultsViewSwitch: $("resultsViewSwitch"),
  logsCount: $("logsCount"),
  logList: $("logList"),
  settingsForm: $("settingsForm"),
  settingsStatus: $("settingsStatus"),
  settingsSummaryText: $("settingsSummaryText"),
  settingsMediaSummaryText: $("settingsMediaSummaryText"),
  settingsAdvancedSummaryText: $("settingsAdvancedSummaryText"),
  settingsMediaSummaryBadge: $("settingsMediaSummaryBadge"),
  settingsAdvancedSummaryBadge: $("settingsAdvancedSummaryBadge"),
  settingDownloadDir: $("settingDownloadDir"),
  settingDownloadMode: $("settingDownloadMode"),
  settingIncludeAudio: $("settingIncludeAudio"),
  settingVideoContainer: $("settingVideoContainer"),
  settingMaxHeight: $("settingMaxHeight"),
  settingAudioFormat: $("settingAudioFormat"),
  settingAudioQuality: $("settingAudioQuality"),
  settingConcurrentVideos: $("settingConcurrentVideos"),
  settingConcurrentFragments: $("settingConcurrentFragments"),
  settingSponsorBlockRemove: $("settingSponsorBlockRemove"),
  settingCleanVideo: $("settingCleanVideo"),
  fieldSettingIncludeAudio: $("fieldSettingIncludeAudio"),
  fieldSettingMaxHeight: $("fieldSettingMaxHeight"),
  fieldSettingVideoContainer: $("fieldSettingVideoContainer"),
  fieldSettingAudioFormat: $("fieldSettingAudioFormat"),
  fieldSettingAudioQuality: $("fieldSettingAudioQuality"),
  btnReviewSelectRecommended: $("btnReviewSelectRecommended"),
  btnReviewSelectPage: $("btnReviewSelectPage"),
  btnReviewClearPage: $("btnReviewClearPage"),
  btnReviewPrev: $("btnReviewPrev"),
  btnReviewNext: $("btnReviewNext"),
};

const tf = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escA(value) {
  return esc(value).replace(/'/g, "&#39;");
}

function stable(value) {
  return JSON.stringify(value ?? null);
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function fmtTime(value) {
  const date = parseDate(value);
  return date ? tf.format(date) : "-";
}

function fmtDur(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "-";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}小时 ${String(m).padStart(2, "0")}分 ${String(s).padStart(2, "0")}秒`;
  if (m > 0) return `${m}分 ${String(s).padStart(2, "0")}秒`;
  return `${s}秒`;
}

function fmtVideoDur(label, seconds) {
  if (label) return String(label);
  if (!Number.isFinite(seconds) || seconds < 0) return "-";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function fmtUploadDate(value) {
  const text = String(value || "").trim();
  if (/^\d{8}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
  return text || "-";
}

function fmtBytes(value) {
  let size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const digits = size >= 100 || index === 0 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[index]}`;
}

function compactTime(value) {
  const date = parseDate(value);
  if (!date) return "-";
  return new Intl.DateTimeFormat(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function tone(status) {
  const value = String(status || "").toLowerCase();
  if (["failed", "error", "danger"].includes(value)) return "danger";
  if (["awaiting_confirmation", "warning", "warn"].includes(value)) return "warn";
  if (["running", "preparing_download", "downloading", "finalizing", "info"].includes(value)) return "info";
  if (["succeeded", "completed", "success"].includes(value)) return "success";
  return "neutral";
}

function stepSummaryMarkup(label, step, fallback = "暂无") {
  if (!step) {
    return `
      <article class="execution-card muted">
        <div class="k">${esc(label)}</div>
        <strong>${esc(fallback)}</strong>
        <div class="subtle">当前没有可展示的步骤信息。</div>
      </article>
    `;
  }
  return `
    <article class="execution-card">
      <div class="execution-head">
        <div class="k">${esc(label)}</div>
        <span class="pill tone-${escA(step.status_tone || tone(step.status))}">${esc(step.tool_name || "-")}</span>
      </div>
      <strong>${esc(step.title || step.step_id || "未命名步骤")}</strong>
      <div class="subtle">${esc(step.message || (step.requires_confirmation ? "这个步骤需要确认后才能继续。" : "等待执行或更新中。"))}</div>
    </article>
  `;
}

function taskStatusText(status) {
  const value = String(status || "").toLowerCase();
  if (!value) return "";
  if (value === "planned") return "任务准备中";
  if (value === "running") return "执行中";
  if (value === "awaiting_confirmation") return "等待确认";
  if (value === "succeeded") return "已完成";
  if (value === "failed") return "失败";
  if (value === "cancelled") return "已取消";
  return value;
}

function resultTaskMetaMarkup(session) {
  if (!session?.source_task_id) return "";
  const title = session.source_task_title || `任务 ${session.source_task_id}`;
  const status = taskStatusText(session.source_task_status);
  const suffix = status ? ` · ${status}` : "";
  return `<div class="subtle">关联任务：${esc(title)}${esc(suffix)}</div>`;
}

function findResultSession(sessionDir) {
  const target = String(sessionDir || "").trim();
  return (state.results?.sessions || []).find((item) => item.session_dir === target) || null;
}

function resultScopeLabel(scope) {
  const value = String(scope || "all");
  if (value === "failed") return "只看有失败项";
  if (value === "retryable") return "只看可重试";
  if (value === "linked_task") return "只看有关联任务";
  if (value === "success_only") return "只看全部成功";
  return "全部会话";
}

function resultSessionSearchText(session) {
  const itemTokens = (session?.items || []).flatMap((item) => [
    item?.title || "",
    item?.video_id || "",
    item?.watch_url || "",
  ]);
  return [
    session?.session_name || "",
    session?.session_dir || "",
    session?.source_task_title || "",
    session?.source_task_id || "",
    ...itemTokens,
  ].join(" ").toLowerCase();
}

function sessionCreatedAtValue(session) {
  const value = Date.parse(String(session?.created_at || ""));
  return Number.isFinite(value) ? value : 0;
}

function resultSessionMatchesScope(session, scope) {
  const value = String(scope || "all");
  if (value === "failed") return Number(session?.failed_count || 0) > 0;
  if (value === "retryable") return !!session?.retry_available;
  if (value === "linked_task") return !!session?.source_task_id;
  if (value === "success_only") return Number(session?.video_count || 0) > 0 && Number(session?.failed_count || 0) === 0;
  return true;
}

function compareResultSessions(a, b, sort) {
  const value = String(sort || "recent_desc");
  if (value === "failed_desc") {
    const failedDiff = Number(b?.failed_count || 0) - Number(a?.failed_count || 0);
    if (failedDiff) return failedDiff;
    return sessionCreatedAtValue(b) - sessionCreatedAtValue(a);
  }
  if (value === "video_desc") {
    const videoDiff = Number(b?.video_count || 0) - Number(a?.video_count || 0);
    if (videoDiff) return videoDiff;
    return sessionCreatedAtValue(b) - sessionCreatedAtValue(a);
  }
  if (value === "title_asc") {
    const titleDiff = String(a?.session_name || "").localeCompare(String(b?.session_name || ""), "zh-Hans-CN");
    if (titleDiff) return titleDiff;
    return sessionCreatedAtValue(b) - sessionCreatedAtValue(a);
  }
  if (value === "recent_asc") return sessionCreatedAtValue(a) - sessionCreatedAtValue(b);
  return sessionCreatedAtValue(b) - sessionCreatedAtValue(a);
}

function deriveResultSessions(payload) {
  const sessions = Array.isArray(payload?.sessions) ? [...payload.sessions] : [];
  const query = String(state.resultsSearch || "").trim().toLowerCase();
  const filtered = sessions.filter((session) => {
    if (!resultSessionMatchesScope(session, state.resultsScope)) return false;
    if (!query) return true;
    return resultSessionSearchText(session).includes(query);
  });
  filtered.sort((a, b) => compareResultSessions(a, b, state.resultsSort));
  const latest = sessions[0];
  if (state.resultsPinLatest && latest) {
    const latestIndex = filtered.findIndex((item) => item.session_dir === latest.session_dir);
    if (latestIndex > 0) {
      const [latestSession] = filtered.splice(latestIndex, 1);
      filtered.unshift(latestSession);
    }
  }
  return {
    sessions: filtered,
    latest,
    filteredCount: filtered.length,
    totalCount: sessions.length,
  };
}

function resultViewLabel(view) {
  return view === "compact" ? "紧凑列表" : "封面预览";
}

function syncResultsViewSwitch() {
  document.querySelectorAll("[data-results-view]").forEach((button) => {
    button.classList.toggle("active", (button.getAttribute("data-results-view") || "gallery") === state.resultsView);
  });
  if (els.resultsList) {
    els.resultsList.dataset.view = state.resultsView;
  }
}

function resultRetryCalloutMarkup(session, { compact = false } = {}) {
  const failedItems = (session?.items || []).filter((item) => !item.success);
  const failedCount = Number(session?.failed_count || failedItems.length || 0);
  if (failedCount <= 0 || !session?.retry_available) return "";
  const retryPending = state.pendingRetrySessionDir === session.session_dir;
  const preview = failedItems
    .slice(0, compact ? 2 : 3)
    .map((item) => `<span class="pill tone-danger">${esc(item.title || item.video_id || "失败视频")}</span>`)
    .join("");
  return `
    <section class="result-retry-callout ${compact ? "compact" : ""}">
      <div>
        <strong>本次有 ${esc(failedCount)} 条失败项可直接重试</strong>
        <div class="subtle">系统会基于当前下载会话里的失败 URL 重新发起下载，不需要重新回到审核阶段。</div>
        ${preview ? `<div class="result-retry-preview">${preview}</div>` : ""}
      </div>
      <div class="mini-actions">
        <button class="btn" type="button" data-result-retry="${escA(session.session_dir)}" ${retryPending ? "disabled" : ""}>${retryPending ? "正在创建重试任务..." : "重试这批失败项"}</button>
      </div>
    </section>
  `;
}

function resultJourneyMarkup(session, { compact = false } = {}) {
  const canInspectTask = !!session?.source_task_id && !!session?.source_task_available;
  const canRelaunch = !!session?.source_task_user_request;
  const canRetry = !!session?.retry_available && Number(session?.failed_count || 0) > 0;
  const taskLabel = session?.source_task_title || session?.source_task_id || "未关联任务";
  const taskStatus = taskStatusText(session?.source_task_status);
  const reviewText = canInspectTask
    ? "回到审核页调整勾选，再次决定哪些视频进入下载。"
    : "当前结果没有可回跳的审核任务。";
  const resultText = `成功 ${esc(session?.success_count ?? 0)} 条，失败 ${esc(session?.failed_count ?? 0)} 条。`;
  const nextText = canRetry
    ? "可以直接重试失败项，也可以基于原始请求重新发起相似任务。"
    : canRelaunch
      ? "这次结果已经生成，可继续基于原始请求发起相似任务。"
      : "当前可直接查看结果或回到原任务继续调整。";
  return `
    <section class="result-journey ${compact ? "compact" : ""}">
      <article class="journey-step">
        <div class="k">1. 原任务</div>
        <strong>${esc(taskLabel)}</strong>
        <div class="subtle">${esc(taskStatus || "任务上下文已关联到本次结果。")}</div>
        ${canInspectTask ? `<div class="mini-actions"><button class="btn2" type="button" data-result-task="${escA(session.source_task_id)}">查看任务状态</button></div>` : ""}
      </article>
      <article class="journey-step">
        <div class="k">2. 审核</div>
        <strong>回到审核继续调整</strong>
        <div class="subtle">${reviewText}</div>
        ${canInspectTask ? `<div class="mini-actions"><button class="btn2" type="button" data-result-review="${escA(session.source_task_id)}">回到审核</button></div>` : ""}
      </article>
      <article class="journey-step">
        <div class="k">3. 下载结果</div>
        <strong>${esc(session?.session_name || "下载会话")}</strong>
        <div class="subtle">${resultText}</div>
      </article>
      <article class="journey-step">
        <div class="k">4. 下一步</div>
        <strong>${canRetry ? "重试 / 再发起" : "继续下一轮任务"}</strong>
        <div class="subtle">${nextText}</div>
        <div class="mini-actions">
          ${canRetry ? `<button class="btn" type="button" data-result-retry="${escA(session.session_dir)}">重试失败项</button>` : ""}
          ${canRelaunch ? `<button class="btn2" type="button" data-result-relaunch="${escA(session.session_dir)}">新建相似任务</button>` : ""}
        </div>
      </article>
    </section>
  `;
}

async function api(url, opt = {}) {
  try {
    const response = await fetch(url, opt);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return {
        code: data.code || `http_${response.status}`,
        error_category: data.error_category || "unknown",
        user_title: data.user_title || "",
        user_message: data.detail || data.user_message || "请求失败。",
        user_recovery: data.user_recovery || "",
        user_actions: Array.isArray(data.user_actions) ? data.user_actions : [],
      };
    }
    return data;
  } catch (error) {
    return {
      code: "network_error",
      error_category: "connection",
      user_title: "网络请求失败",
      user_message: error?.message || "网络请求失败。",
      user_recovery: "请检查本地服务是否已启动，以及当前网络或系统代理是否正常。",
      user_actions: ["重试", "检查本地服务"],
    };
  }
}

async function loadBootstrapDefaults() {
  const payload = await api("/api/bootstrap");
  if (payload.code) return null;
  return payload;
}

function formatAgentFeedback(response, fallbackTitle = "操作失败", fallbackMessage = "请求失败。") {
  if (!response?.code) {
    const title = response?.user_title || "操作成功";
    const message = response?.user_message || response?.message || fallbackMessage;
    return `${title}：${message}`;
  }
  const title = response.user_title || fallbackTitle;
  const message = response.user_message || fallbackMessage;
  const recovery = response.user_recovery || "";
  return recovery ? `${title}：${message} ${recovery}` : `${title}：${message}`;
}

function clearAgentFailure() {
  state.agentFailure = null;
}

function setAgentFailure(kind, response, extra = {}) {
  const actions = [];
  if (kind === "run") {
    actions.push({ label: "重试运行", action: "retry-run", style: "btn" });
  } else if (kind === "resume") {
    actions.push({ label: "重新恢复", action: "retry-resume", style: "btn" });
  }
  if (extra.taskId || state.currentTaskId) {
    actions.push({ label: "刷新任务状态", action: "reload-current-task", style: "btn2" });
    actions.push({ label: "查看日志", action: "go-logs", style: "btn2" });
  } else {
    actions.push({ label: "回到任务输入", action: "focus-run", style: "btn2" });
  }
  actions.push({ label: "检查设置", action: "go-settings", style: "btn2" });

  state.agentFailure = {
    kind,
    title: response?.user_title || (kind === "resume" ? "任务恢复失败" : "任务运行失败"),
    message: response?.user_message || "",
    recovery: response?.user_recovery || "",
    code: response?.code || "",
    category: response?.error_category || "unknown",
    taskId: extra.taskId || state.currentTaskId || "",
    workdir: extra.workdir || state.currentWorkdir || els.workdir.value.trim(),
    actions,
  };
}

function failureRecoveryMarkup(failure) {
  if (!failure) return "";
  const messageParts = [failure.message, failure.recovery].filter(Boolean);
  return `
    <section class="inner recovery-card">
      <div class="section">
        <h3>${esc(failure.kind === "resume" ? "恢复没有成功" : "运行没有成功")}</h3>
        <span class="pill tone-danger">${esc(failure.code || failure.category || "需要处理")}</span>
      </div>
      <div class="message"><strong>${esc(failure.title || "当前操作失败")}</strong>${messageParts.length ? `：${esc(messageParts.join(" "))}` : ""}</div>
      <div class="actions" style="margin-top:12px">
        ${failure.actions.map((item) => `<button class="${escA(item.style || "btn2")}" type="button" data-ui-action="${escA(item.action)}">${esc(item.label)}</button>`).join("")}
      </div>
    </section>
  `;
}

function debugListMarkup(label, items) {
  const values = Array.isArray(items) && items.length ? items : ["-"];
  return `<article class="metric"><div class="k">${esc(label)}</div><div class="v">${esc(values.join(", "))}</div></article>`;
}

function renderGraphDebug() {
  const payload = state.graphDebug;
  if (!payload?.enabled) {
    if (els.graphDebugPanel) els.graphDebugPanel.hidden = true;
    if (els.graphDebugBox) els.graphDebugBox.textContent = "仅本地开发模式下显示最近一个 LangGraph checkpoint。";
    state.renderCache.graphDebug = "";
    return;
  }
  if (els.graphDebugPanel) els.graphDebugPanel.hidden = false;
  if (els.graphDebugPill) {
    els.graphDebugPill.className = `pill tone-${payload.failure_origin || payload.last_error?.message ? "warn" : "info"}`;
    els.graphDebugPill.textContent = payload.node_name || "checkpoint";
  }
  const errorText = payload.last_error?.message
    ? `${payload.last_error.message}${payload.failure_origin ? ` · ${payload.failure_origin}` : ""}`
    : "当前没有记录到 graph 执行错误。";
  const html = `
    <details class="graph-debug-details">
      <summary>查看最近一个 graph checkpoint</summary>
      <div class="execution-shell" style="margin-top:12px">
        <div class="execution-summary">
          <article class="metric"><div class="k">节点</div><div class="v">${esc(payload.node_name || "-")}</div><div class="d">${esc(payload.updated_at ? `更新于 ${fmtTime(payload.updated_at)}` : "还没有 checkpoint 时间戳")}</div></article>
          <article class="metric"><div class="k">规划器</div><div class="v">${esc(payload.planner_name || "-")}</div><div class="d">${esc((payload.planner_notes || []).join(" · ") || "没有 planner notes")}</div></article>
          <article class="metric"><div class="k">选中步骤</div><div class="v">${esc(payload.selected_step_id || "-")}</div><div class="d">${esc(payload.selected_step_index == null ? "没有 selected_step_index" : `index ${payload.selected_step_index}`)}</div></article>
          <article class="metric"><div class="k">等待确认</div><div class="v">${esc(payload.pending_step_id || "-")}</div><div class="d">${esc(payload.task_status || "未知任务状态")}</div></article>
        </div>
        <div class="execution-event">
          <div class="k">最近错误</div>
          <div class="message">${esc(errorText)}</div>
        </div>
        <div class="metrics">
          ${debugListMarkup("resolved_payloads", payload.resolved_payload_keys)}
          ${debugListMarkup("step_results", payload.step_result_keys)}
          ${debugListMarkup("runtime_defaults", payload.runtime_default_keys)}
        </div>
      </div>
    </details>
  `;
  if (html !== state.renderCache.graphDebug) {
    els.graphDebugBox.className = "";
    els.graphDebugBox.innerHTML = html;
    state.renderCache.graphDebug = html;
  }
}

function curProvider() {
  return els.provider.value === "custom" ? els.providerCustom.value.trim() : els.provider.value.trim();
}

function curModel() {
  return els.modelSelect.value === "__manual__" ? els.modelManual.value.trim() : els.modelSelect.value.trim();
}

function runtimePayload() {
  return {
    llm_provider: curProvider(),
    llm_base_url: els.baseUrl.value.trim(),
    llm_model: curModel(),
    llm_api_key: els.apiKey.value.trim(),
  };
}

function panelStateMarkup({
  toneName = "neutral",
  eyebrow = "",
  title = "",
  message = "",
  actionLabel = "",
  action = "",
  center = true,
  actionStyle = "btn2",
} = {}) {
  const safeEyebrow = eyebrow || (toneName === "danger" ? "需要处理" : toneName === "info" ? "处理中" : "当前状态");
  return `
    <div class="empty-state tone-${escA(toneName)} ${center ? "center" : ""}">
      <div class="empty-state-eyebrow">${esc(safeEyebrow)}</div>
      <h4 class="empty-state-title">${esc(title || "暂无内容")}</h4>
      <div class="empty-state-copy">${esc(message || "")}</div>
      ${actionLabel && action ? `<div class="mini-actions"><button class="${escA(actionStyle)}" type="button" data-ui-action="${escA(action)}">${esc(actionLabel)}</button></div>` : ""}
    </div>
  `;
}

function panelStateOptions(payloadState, fallback = {}) {
  const base = payloadState && typeof payloadState === "object"
    ? {
        toneName: payloadState.tone || fallback.toneName,
        eyebrow: payloadState.eyebrow || fallback.eyebrow,
        title: payloadState.title || fallback.title,
        message: payloadState.message || fallback.message,
        actionLabel: payloadState.action_label || fallback.actionLabel,
        action: payloadState.action || fallback.action,
        actionStyle: payloadState.action_style || fallback.actionStyle,
      }
    : {};
  return { ...fallback, ...base };
}

function syncModel() {
  const manual = els.modelSelect.value === "__manual__";
  els.modelManual.hidden = !manual;
  if (!manual) els.modelManual.value = "";
  if (manual && els.taskInputAdvanced) els.taskInputAdvanced.open = true;
  updateAdvancedSummary();
}

function updateProviderPreset() {
  const preset = presets[els.provider.value] || presets.custom;
  const custom = els.provider.value === "custom";
  els.providerCustom.hidden = !custom;
  if (!els.baseUrl.value.trim() || !custom) els.baseUrl.value = preset.baseUrl || "";
  els.modelSelect.innerHTML = "";
  (preset.models || []).forEach((modelName) => {
    const option = document.createElement("option");
    option.value = modelName;
    option.textContent = modelName;
    els.modelSelect.appendChild(option);
  });
  const manualOption = document.createElement("option");
  manualOption.value = "__manual__";
  manualOption.textContent = "手动填写模型";
  els.modelSelect.appendChild(manualOption);
  els.modelSuggestion.textContent = preset.models?.length ? `建议模型: ${preset.models.join(" / ")}` : "建议模型: 手动填写";
  els.providerHint.textContent = custom
    ? "自定义 provider 不做额外兼容假设，请同时确认 Base URL、模型名和请求头兼容性。"
    : "预置 provider 会自动带出推荐 URL 和模型；如需兼容平台可切换到手动填写。";
  if (custom && els.taskInputAdvanced) els.taskInputAdvanced.open = true;
  syncModel();
}

function updateAdvancedSummary() {
  if (!els.advancedSummaryText) return;
  const providerLabel = curProvider() || "未设置 provider";
  const modelLabel = curModel() || "未设置模型";
  const presetBaseUrl = (presets[els.provider.value] || presets.custom).baseUrl || "";
  const baseUrl = els.baseUrl.value.trim();
  const baseUrlLabel = !baseUrl ? "未设置 URL" : baseUrl === presetBaseUrl ? "默认 URL" : "自定义 URL";
  els.advancedSummaryText.textContent = `${providerLabel} / ${modelLabel} / ${baseUrlLabel}`;
}

function setActiveRequestTemplate(name) {
  const current = String(name || "review");
  document.querySelectorAll("[data-request-template]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-request-template") === current);
  });
  document.querySelectorAll("[data-request-template-card]").forEach((card) => {
    card.classList.toggle("active", card.getAttribute("data-request-template-card") === current);
  });
  if (!els.requestTemplateHint) return;
  const hints = {
    review: "推荐默认流程：先筛选候选，再由你确认后下载。",
    compare: "适合需要限定时间范围、数量和对比维度的横评任务。",
    clips: "适合找画面素材，建议在请求里写清横竖屏、画质和无解说要求。",
    audio: "适合播客、访谈、演讲，填入后可到设置页切换成音频模式。",
  };
  els.requestTemplateHint.textContent = hints[current] || "点击填入后再改主题即可";
}

function applyRequestTemplate(text) {
  const value = String(text || "").trim();
  if (!value) return;
  els.request.value = value;
  els.request.focus();
  els.request.setSelectionRange(els.request.value.length, els.request.value.length);
  els.workspaceSubtitle.textContent = "已填入请求模板。按你的主题、时间范围和数量要求改几处后即可运行任务。";
}

function setTab(name) {
  state.activeTab = name;
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${name}`);
  });
  if (name === "logs") loadLogs(true);
  if (name === "review" && state.currentTaskId && state.currentWorkdir) loadReview(state.currentTaskId, state.currentWorkdir);
  if (name === "results") loadResults(els.workdir.value.trim());
  if (name === "settings") loadSettings(els.workdir.value.trim(), false);
}

function setHeader(task, summary, stageLabel, primaryMessage) {
  const title = task?.title || summary?.title || "未选择任务";
  const subtitle = primaryMessage || summary?.last_message || task?.user_request || "运行或选择一个任务后，这里会显示当前阶段、下载进度、日志以及下载入口。";
  const taskId = task?.task_id || summary?.task_id || "-";
  const stage = stageLabel || task?.status_label || task?.status || "未开始";
  els.workspaceTitle.textContent = title;
  els.workspaceSubtitle.textContent = subtitle;
  els.statusPill.className = `pill tone-${tone(task?.status || stage)}`;
  els.statusPill.textContent = `阶段: ${stage}`;
  els.taskIdPill.textContent = `Task: ${taskId}`;
}

function setActionButtons() {
  const creating = state.creatingTask;
  const resuming = !!state.pendingResumeTaskId;
  els.btnRun.disabled = creating || resuming;
  els.btnResume.disabled = creating || resuming || !state.currentTaskId;
  els.btnTest.disabled = creating || resuming;
}

function showTaskShell({ taskId = "", title = "", userRequest = "", status = "planned", statusLabel = "任务准备中", subtitle = "" } = {}) {
  clearWorkspace();
  state.currentTaskId = taskId || "";
  state.currentWorkdir = els.workdir.value.trim();
  state.currentTaskStatus = status || "";
  if (taskId || title) {
    setHeader({ task_id: taskId, title: title || "新任务", user_request: userRequest, status, status_label: statusLabel }, null, statusLabel, subtitle);
  }
  els.workspaceStagePill.className = `pill tone-${tone(status)}`;
  els.workspaceStagePill.textContent = statusLabel;
  els.primaryMessage.textContent = subtitle || "任务已创建，等待执行。";
  els.taskIdPill.textContent = `Task: ${taskId || "-"}`;
}

function progressPct(task, downloadProgress) {
  if (!task) return 0;
  if (String(task.status || "").toLowerCase() === "succeeded") return 100;
  const metrics = task.metrics || {};
  const total = Number(metrics.total_steps || 0);
  const completed = Number(metrics.completed_steps || 0);
  if (total <= 0) {
    return downloadProgress?.percent ? Math.round(Math.min(100, Math.max(0, downloadProgress.percent))) : 0;
  }
  const bonus = downloadProgress?.percent
    ? Math.min(0.99, Math.max(0, downloadProgress.percent / 100))
    : String(task.status || "").toLowerCase() === "running"
      ? 0.35
      : 0;
  return Math.round(Math.max(0, Math.min(100, ((completed + bonus) / total) * 100)));
}

function setTiming(activeElapsedSeconds, isRunning) {
  state.statusTiming = {
    activeElapsedSeconds: Number.isFinite(activeElapsedSeconds) ? Number(activeElapsedSeconds) : null,
    isRunning: Boolean(isRunning),
    tickStartedAt: Date.now(),
  };
  if (state.statusClockTimer) {
    clearInterval(state.statusClockTimer);
    state.statusClockTimer = null;
  }
  updateElapsed();
  if (state.statusTiming.activeElapsedSeconds != null && state.statusTiming.isRunning) {
    state.statusClockTimer = setInterval(updateElapsed, 1000);
  }
}

function updateElapsed() {
  if (state.statusTiming?.activeElapsedSeconds == null) return;
  const extra = state.statusTiming.isRunning ? Math.max(0, Math.floor((Date.now() - state.statusTiming.tickStartedAt) / 1000)) : 0;
  const seconds = Math.max(0, Math.floor(state.statusTiming.activeElapsedSeconds) + extra);
  const node = document.querySelector('[data-metric="elapsed"] .v');
  const detail = document.querySelector('[data-metric="elapsed"] .d');
  if (node) node.textContent = fmtDur(seconds);
  if (detail) detail.textContent = state.statusTiming.isRunning ? "任务仍在持续运行" : "累计有效运行时长";
}

function defaultLocation() {
  return String(els.settingDownloadDir.value || "").trim();
}

function settingsDownloadMode() {
  return els.settingDownloadMode.value === "audio" ? "audio" : "video";
}

function setSettingsFieldHidden(node, hidden) {
  if (!node) return;
  node.hidden = !!hidden;
}

function syncSettingsModeVisibility() {
  const isAudioMode = settingsDownloadMode() === "audio";
  setSettingsFieldHidden(els.fieldSettingMaxHeight, isAudioMode);
  setSettingsFieldHidden(els.fieldSettingIncludeAudio, isAudioMode);
  setSettingsFieldHidden(els.fieldSettingVideoContainer, isAudioMode);
  setSettingsFieldHidden(els.fieldSettingAudioFormat, !isAudioMode);
  setSettingsFieldHidden(els.fieldSettingAudioQuality, !isAudioMode);
}

function updateSettingsSummary() {
  const mode = settingsDownloadMode();
  const dir = defaultLocation() || "当前 workdir 默认目录";
  const isAudioMode = mode === "audio";
  const maxHeight = String(els.settingMaxHeight.value || "").trim();
  const audioQuality = String(els.settingAudioQuality.value || "").trim();
  const sponsorBlock = String(els.settingSponsorBlockRemove.value || "").trim();
  const concurrentVideos = Math.max(1, Number(els.settingConcurrentVideos.value || 1));
  const concurrentFragments = Math.max(1, Number(els.settingConcurrentFragments.value || 4));

  const summaryText = isAudioMode
    ? `默认下载到 ${dir}，以音频模式输出，可直接用于播客、剪辑或纯音频归档。`
    : `默认下载到 ${dir}，以视频模式输出，适合直接开始常规下载任务。`;
  const mediaSummary = isAudioMode
    ? `格式 ${els.settingAudioFormat.value || "best"} · 音质 ${audioQuality ? `${audioQuality} kbps` : "默认"}`
    : `封装 ${els.settingVideoContainer.value || "auto"} · ${maxHeight ? `${maxHeight}p 上限` : "分辨率自动"} · ${els.settingIncludeAudio.checked ? "包含音轨" : "仅视频轨"}`;
  const advancedFlags = [];
  if (sponsorBlock) advancedFlags.push(`SponsorBlock: ${sponsorBlock}`);
  if (els.settingCleanVideo.checked) advancedFlags.push("清理模式开启");
  const advancedSummary = [`${concurrentVideos} 路视频并发`, `${concurrentFragments} 路分片并发`, ...advancedFlags].join(" · ");

  if (els.settingsSummaryText) els.settingsSummaryText.textContent = summaryText;
  if (els.settingsMediaSummaryText) els.settingsMediaSummaryText.textContent = mediaSummary;
  if (els.settingsAdvancedSummaryText) els.settingsAdvancedSummaryText.textContent = advancedSummary;
  if (els.settingsMediaSummaryBadge) els.settingsMediaSummaryBadge.textContent = mediaSummary;
  if (els.settingsAdvancedSummaryBadge) els.settingsAdvancedSummaryBadge.textContent = advancedSummary;
}

function fillSettings(payload) {
  els.settingDownloadDir.value = payload.download_dir || "";
  els.settingDownloadMode.value = payload.download_mode || "video";
  els.settingIncludeAudio.checked = !!payload.include_audio;
  els.settingVideoContainer.value = payload.video_container || "auto";
  els.settingMaxHeight.value = payload.max_height ?? "";
  els.settingAudioFormat.value = payload.audio_format || "best";
  els.settingAudioQuality.value = payload.audio_quality ?? "";
  els.settingConcurrentVideos.value = payload.concurrent_videos ?? 1;
  els.settingConcurrentFragments.value = payload.concurrent_fragments ?? 4;
  els.settingSponsorBlockRemove.value = payload.sponsorblock_remove || "";
  els.settingCleanVideo.checked = !!payload.clean_video;
  syncSettingsModeVisibility();
  updateSettingsSummary();
}

function settingsPayload() {
  return {
    workdir: els.workdir.value.trim(),
    download_dir: els.settingDownloadDir.value.trim(),
    download_mode: els.settingDownloadMode.value,
    include_audio: els.settingIncludeAudio.checked,
    video_container: els.settingVideoContainer.value,
    max_height: els.settingMaxHeight.value.trim() ? Number(els.settingMaxHeight.value.trim()) : null,
    audio_format: els.settingAudioFormat.value,
    audio_quality: els.settingAudioQuality.value.trim() ? Number(els.settingAudioQuality.value.trim()) : null,
    concurrent_videos: Math.max(1, Number(els.settingConcurrentVideos.value || 1)),
    concurrent_fragments: Math.max(1, Number(els.settingConcurrentFragments.value || 4)),
    sponsorblock_remove: els.settingSponsorBlockRemove.value.trim(),
    clean_video: els.settingCleanVideo.checked,
  };
}

async function loadSettings(workdir, show = true) {
  const target = String(workdir || "").trim();
  if (!target) return;
  const payload = await api(`/api/settings/download?workdir=${encodeURIComponent(target)}`);
  if (payload.code) {
    els.settingsStatus.textContent = payload.user_message || "读取下载设置失败。";
    return;
  }
  fillSettings(payload);
  if (show) els.settingsStatus.textContent = `已读取 ${target} 的下载默认设置。`;
}

async function saveSettings(show = true) {
  const payload = settingsPayload();
  const response = await api("/api/settings/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.code) {
    els.settingsStatus.textContent = response.user_message || "保存下载设置失败。";
    return false;
  }
  fillSettings(response);
  if (show) els.settingsStatus.textContent = `已保存 ${payload.workdir} 的下载默认设置。`;
  return true;
}

function stageTone(stage) {
  const value = String(stage || "").toLowerCase();
  if (value === "awaiting_confirmation") return "warn";
  if (value === "completed") return "success";
  if (value === "failed") return "danger";
  if (["preparing_download", "downloading", "finalizing", "planned"].includes(value)) return "info";
  return "neutral";
}

function fallbackStage(task, downloadProgress) {
  const status = String(task?.status || "").toLowerCase();
  if (status === "awaiting_confirmation") return "awaiting_confirmation";
  if (status === "succeeded") return "completed";
  if (status === "failed") return "failed";
  if (status === "running" && downloadProgress?.phase === "downloading") return "downloading";
  if (status === "running" && downloadProgress?.phase === "completed") return "finalizing";
  if (status === "running") return "preparing_download";
  return "planned";
}

function fallbackStageLabel(stage) {
  const labels = {
    planned: "任务准备中",
    awaiting_confirmation: "等待确认下载",
    preparing_download: "准备下载中",
    downloading: "正在下载",
    finalizing: "整理下载结果",
    completed: "下载已完成",
    failed: "任务失败",
  };
  return labels[stage] || "任务准备中";
}

function fallbackEntry(task, stage) {
  const path = defaultLocation() || task?.workdir || "";
  return {
    path,
    label: stage === "completed" ? "打开已下载视频" : "查看目标目录",
    ready: stage === "completed" && !!path,
  };
}

function reviewSelectedCount() {
  const summary = state.review?.summary || null;
  if (summary) return Number(summary.selected_count || 0);
  return Number(state.currentLifecycle?.focus_summary?.selected_url_count || 0);
}

function canLaunchSelectedDownload() {
  const stage = currentStage();
  if (state.pendingDownloadLaunch || state.pendingResumeTaskId || state.reviewSaveInFlight) return false;
  if (["preparing_download", "downloading", "finalizing"].includes(stage)) return false;
  return reviewSelectedCount() > 0;
}

function syncReviewSummaryIntoLifecycle() {
  if (!state.currentLifecycle?.focus_summary || !state.review?.summary) return;
  state.currentLifecycle.focus_summary.selected_url_count = Number(state.review.summary.selected_count || 0);
}

function setReviewStatusText(value) {
  state.reviewStatusText = String(value || "");
  if (els.reviewStatus) els.reviewStatus.textContent = state.reviewStatusText || "先运行或选中一个任务，然后在这里决定哪些视频真正进入下载。";
}

function resultsSummaryMarkup(payload) {
  const latest = payload?.sessions?.[0] || null;
  const retryPending = latest && state.pendingRetrySessionDir === latest.session_dir;
  const pills = [
    ["下载会话", payload?.total_sessions ?? 0, "info"],
    ["已下载视频", payload?.total_videos ?? 0, "success"],
    ["下载目录", payload?.download_dir ? 1 : 0, "neutral"],
  ];
  const summary = pills.map(([label, count, toneName]) => `<span class="pill tone-${toneName}">${esc(label)} ${esc(count)}</span>`).join("");
  const latestMarkup = latest
    ? `
      <div class="results-highlight">
        <div>
          <div class="k">最新会话</div>
          <strong>${esc(latest.session_name || "最近下载")}</strong>
          ${resultTaskMetaMarkup(latest)}
          <div class="result-meta-row">
            <span>${esc(fmtTime(latest.created_at))}</span>
            <span>成功 ${esc(latest.success_count ?? 0)}</span>
            <span>失败 ${esc(latest.failed_count ?? 0)}</span>
            <span>视频 ${esc(latest.video_count ?? 0)}</span>
          </div>
        </div>
        <div class="mini-actions">
          <button class="btn" type="button" data-result-open="${escA(latest.session_dir || payload?.download_dir || "")}">打开这次下载</button>
          ${latest.source_task_id && latest.source_task_available ? `<button class="btn2" type="button" data-result-task="${escA(latest.source_task_id)}">回到原任务继续调整</button>` : ""}
          ${latest.source_task_user_request ? `<button class="btn2" type="button" data-result-relaunch="${escA(latest.session_dir)}">基于这次结果新建相似任务</button>` : ""}
          ${latest.retry_available ? `<button class="btn2" type="button" data-result-retry="${escA(latest.session_dir)}" ${retryPending ? "disabled" : ""}>${retryPending ? "正在创建重试任务..." : "重试失败项"}</button>` : ""}
          ${latest.report_path ? `<button class="btn2" type="button" data-result-open="${escA(latest.report_path)}">查看报告</button>` : ""}
        </div>
      </div>
    `
    : "";
  const rootActions = payload?.download_dir
    ? `<div class="mini-actions"><button class="btn2" type="button" data-result-open="${escA(payload.download_dir)}">打开下载目录</button></div>`
    : "";
  const path = payload?.download_dir ? `<div class="path results-root-path">${esc(payload.download_dir)}</div>` : "";
  return `
    <section class="results-overview">
      <div class="results-summary-heading">
        <div>
          <strong>最近下载结果</strong>
          <div class="subtle">结果页优先展示最新会话和可直接打开的视频，不再把内部文件当成主结果。</div>
        </div>
        ${rootActions}
      </div>
      <div class="results-summary-box">${summary}</div>
      ${latestMarkup}
      ${latest ? resultJourneyMarkup(latest, { compact: true }) : ""}
      ${latest?.failed_count ? resultRetryCalloutMarkup(latest, { compact: true }) : ""}
      ${path}
    </section>
  `;
}

function workspaceActionsMarkup({ stage, selectedCount, downloadEntry, hasReview, agentFailure = null }) {
  if (agentFailure) {
    return `
      <section class="action-callout">
        <div>
          <strong>${esc(agentFailure.kind === "resume" ? "恢复被中断，需要你决定下一步" : "本次运行没有完成，可以直接继续处理")}</strong>
          <div class="subtle">${esc([agentFailure.message, agentFailure.recovery].filter(Boolean).join(" ") || "可以直接重试，也可以先检查日志和设置。")}</div>
        </div>
        <div class="mini-actions">
          ${agentFailure.actions.map((item) => `<button class="${escA(item.style || "btn2")}" type="button" data-workspace-action="${escA(item.action)}">${esc(item.label)}</button>`).join("")}
        </div>
      </section>
    `;
  }
  if (!state.currentTaskId) {
    return `
      <section class="action-callout">
        <div>
          <strong>从一个自然语言任务开始</strong>
          <div class="subtle">输入请求后直接运行。筛选完成时，再到审核里保留真正要下载的视频。</div>
        </div>
        <div class="mini-actions">
          <button class="btn" type="button" data-workspace-action="focus-run">创建新任务</button>
        </div>
      </section>
    `;
  }
  if (stage === "awaiting_confirmation") {
    return `
      <section class="action-callout">
        <div>
          <strong>下载前还差一步确认</strong>
          <div class="subtle">当前已选择 ${esc(selectedCount)} 条视频。先确认审核结果，再开始下载。</div>
        </div>
        <div class="mini-actions">
          <button class="btn" type="button" data-workspace-action="confirm-download" ${selectedCount > 0 ? "" : "disabled"}>确认并开始下载</button>
          <button class="btn2" type="button" data-workspace-action="go-review">查看审核</button>
        </div>
      </section>
    `;
  }
  if (["preparing_download", "downloading", "finalizing"].includes(stage)) {
    return `
      <section class="action-callout">
        <div>
          <strong>下载进行中</strong>
          <div class="subtle">当前任务已经进入下载阶段。进度和详细输出在状态与日志里查看。</div>
        </div>
        <div class="mini-actions">
          <button class="btn" type="button" data-workspace-action="go-logs">查看日志</button>
          <button class="btn2" type="button" data-workspace-action="go-status">回到状态</button>
        </div>
      </section>
    `;
  }
  if (stage === "completed") {
    return `
      <section class="action-callout">
        <div>
          <strong>下载完成</strong>
          <div class="subtle">结果页会按下载会话列出视频和主要打开入口，方便直接回看已下载内容。</div>
        </div>
        <div class="mini-actions">
          <button class="btn" type="button" data-workspace-action="go-results">查看下载结果</button>
          ${downloadEntry?.path ? `<button class="btn2" type="button" data-workspace-action="open-entry" data-entry-path="${escA(downloadEntry.path)}">打开目录</button>` : ""}
        </div>
      </section>
    `;
  }
  if (stage === "failed") {
    return `
      <section class="action-callout">
        <div>
          <strong>任务没有完成</strong>
          <div class="subtle">先看日志定位问题；如果筛选结果还在，也可以回到审核重新开始下载。</div>
        </div>
        <div class="mini-actions">
          <button class="btn" type="button" data-workspace-action="go-logs">查看日志</button>
          ${hasReview ? '<button class="btn2" type="button" data-workspace-action="go-review">回到审核</button>' : ""}
        </div>
      </section>
    `;
  }
  return `
    <section class="action-callout">
      <div>
        <strong>${hasReview ? "先看审核结果，再开始下载" : "任务已准备好"}</strong>
        <div class="subtle">${hasReview ? `当前有 ${esc(selectedCount)} 条视频已进入下载队列。` : "任务还在准备或筛选阶段。"} 下一步会根据当前阶段自动收敛到最合适的操作。</div>
      </div>
      <div class="mini-actions">
        ${hasReview ? '<button class="btn" type="button" data-workspace-action="go-review">去审核候选</button>' : '<button class="btn" type="button" data-workspace-action="go-status">查看状态</button>'}
        ${hasReview && selectedCount > 0 ? '<button class="btn2" type="button" data-workspace-action="start-selected-download">开始下载</button>' : ""}
      </div>
    </section>
  `;
}

function resultVideoMarkup(item, session = null, view = "gallery") {
  const thumb = item.thumbnail_url
    ? `<img src="${escA(item.thumbnail_url)}" alt="${escA(item.title || "视频封面")}" loading="lazy" referrerpolicy="no-referrer" />`
    : `<div class="thumb-fallback">暂无封面</div>`;
  const actions = [];
  if (item.file_path) actions.push(`<button class="btn" type="button" data-result-open="${escA(item.file_path)}">打开视频</button>`);
  if (!item.success && session?.retry_available) actions.push(`<button class="btn" type="button" data-result-retry="${escA(session.session_dir)}">${esc("重试失败项")}</button>`);
  if (item.watch_url) actions.push(`<a class="btn2 review-link" href="${escA(item.watch_url)}" target="_blank" rel="noreferrer noopener">原始链接</a>`);
  const detail = [
    item.video_id || "-",
    item.upload_date || "-",
    fmtBytes(item.file_size_bytes || 0),
  ];
  return `
    <article class="result-video ${item.success ? "" : "is-failed"} ${view === "compact" ? "compact" : "gallery"}">
      <div class="result-thumb">${thumb}</div>
      <div class="result-body">
        <div class="result-head">
          <strong class="result-title">${esc(item.title || "未命名视频")}</strong>
          <span class="pill tone-${item.success ? "success" : "danger"}">${esc(item.success ? "下载成功" : "下载失败")}</span>
        </div>
        <div class="result-meta-row">${detail.map((value) => `<span>${esc(value)}</span>`).join("")}</div>
        <div class="result-actions">${actions.join("")}</div>
      </div>
    </article>
  `;
}

function resultSessionMarkup(session) {
  const retryPending = state.pendingRetrySessionDir === session.session_dir;
  const failedItems = (session.items || []).filter((item) => !item.success);
  const successItems = (session.items || []).filter((item) => item.success);
  const view = state.resultsView || "gallery";
  const actions = [
    `<button class="btn2" type="button" data-result-open="${escA(session.session_dir)}">打开目录</button>`,
  ];
  if (session.source_task_id && session.source_task_available) actions.push(`<button class="btn2" type="button" data-result-task="${escA(session.source_task_id)}">回到原任务继续调整</button>`);
  if (session.source_task_user_request) actions.push(`<button class="btn2" type="button" data-result-relaunch="${escA(session.session_dir)}">基于这次结果新建相似任务</button>`);
  if (session.retry_available) actions.push(`<button class="btn" type="button" data-result-retry="${escA(session.session_dir)}" ${retryPending ? "disabled" : ""}>${retryPending ? "正在创建重试任务..." : "重试失败项"}</button>`);
  if (session.report_path) actions.push(`<button class="btn2" type="button" data-result-open="${escA(session.report_path)}">打开报告</button>`);
  return `
    <section class="result-session ${view === "compact" ? "compact" : "gallery"}">
      <div class="result-session-head">
        <div>
          <h4>${esc(session.session_name || "下载会话")}</h4>
          ${resultTaskMetaMarkup(session)}
          <div class="result-meta-row">
            <span>${esc(fmtTime(session.created_at))}</span>
            <span>成功 ${esc(session.success_count ?? 0)}</span>
            <span>失败 ${esc(session.failed_count ?? 0)}</span>
          </div>
        </div>
        <div class="mini-actions">${actions.join("")}</div>
      </div>
      ${resultJourneyMarkup(session)}
      ${session.failed_count ? resultRetryCalloutMarkup(session) : ""}
      ${(session.items || []).length ? `
        <div class="result-groups">
          ${failedItems.length ? `
            <section class="result-group danger">
              <div class="result-group-head">
                <strong>失败项</strong>
                <span class="pill tone-danger">${esc(failedItems.length)} 条</span>
              </div>
              <div class="result-videos ${view === "compact" ? "compact" : "gallery"}">${failedItems.map((item) => resultVideoMarkup(item, session, view)).join("")}</div>
            </section>
          ` : ""}
          ${successItems.length ? `
            <section class="result-group">
              <div class="result-group-head">
                <strong>已下载视频</strong>
                <span class="pill tone-success">${esc(successItems.length)} 条</span>
              </div>
              <div class="result-videos ${view === "compact" ? "compact" : "gallery"}">${successItems.map((item) => resultVideoMarkup(item, session, view)).join("")}</div>
            </section>
          ` : ""}
        </div>
      ` : panelStateMarkup({
        eyebrow: "暂无视频",
        title: "这个下载会话里还没有可展示的视频记录",
        message: "会话目录已经建立，但还没有读到可展示的视频文件或报告条目。",
      })}
    </section>
  `;
}

function renderResults() {
  const payload = state.results;
  syncResultsViewSwitch();
  if (!payload) {
    els.resultsStatusPill.className = "pill tone-info";
    els.resultsStatusPill.textContent = "加载中";
    if (els.resultsFilterStatusPill) {
      els.resultsFilterStatusPill.className = "pill tone-info";
      els.resultsFilterStatusPill.textContent = "读取中";
    }
    els.resultsSummary.innerHTML = "";
    els.resultsList.innerHTML = panelStateMarkup({
      toneName: "info",
      eyebrow: "处理中",
      title: "正在读取下载结果",
      message: "正在聚合下载会话、视频文件和封面信息。",
    });
    return;
  }
  const resultsTone = payload.load_error ? "danger" : payload.available ? "success" : "neutral";
  const derived = deriveResultSessions(payload);
  const filterTone = payload.load_error ? "danger" : derived.filteredCount ? "info" : "neutral";
  els.resultsStatusPill.className = `pill tone-${resultsTone}`;
  els.resultsStatusPill.textContent = payload.load_error ? "读取失败" : payload.available ? "已就绪" : "暂无结果";
  if (els.resultsFilterStatusPill) {
    els.resultsFilterStatusPill.className = `pill tone-${filterTone}`;
    const pinText = state.resultsPinLatest ? " · 最近置顶" : "";
    els.resultsFilterStatusPill.textContent = `${resultScopeLabel(state.resultsScope)} ${derived.filteredCount}/${derived.totalCount} · ${resultViewLabel(state.resultsView)}${pinText}`;
  }
  els.resultsSummary.innerHTML = resultsSummaryMarkup(payload);
  els.resultsList.innerHTML = payload.available
    ? (payload.sessions || []).map(resultSessionMarkup).join("")
    : panelStateMarkup(panelStateOptions(
      payload.panel_state,
      payload.load_error
        ? {
            toneName: "danger",
            eyebrow: "读取失败",
            title: "结果页暂时无法读取",
            message: payload.empty_message || "下载结果读取失败，请稍后重试。",
            actionLabel: "重新读取",
            action: "refresh-results",
            actionStyle: "btn3",
          }
        : {
            toneName: "neutral",
            eyebrow: "还没有结果",
            title: "这里还没有已下载视频",
            message: payload.empty_message || "完成一次下载后，这里会展示最新会话和可直接打开的视频。",
            actionLabel: "创建新任务",
            action: "focus-run",
          }
    ));
  if (payload.available) {
    els.resultsList.innerHTML = derived.filteredCount
      ? derived.sessions.map(resultSessionMarkup).join("")
      : panelStateMarkup({
          toneName: "neutral",
          eyebrow: "没有匹配结果",
          title: "当前筛选条件下没有匹配的下载会话",
          message: `已按“${resultScopeLabel(state.resultsScope)}”和当前关键词过滤。可以清空筛选，或关闭“最近会话置顶”后重新查看。`,
          actionLabel: "重置筛选",
          action: "reset-results-filters",
          actionStyle: "btn2",
        });
  }
}

async function loadResults(workdir = "") {
  const target = String(workdir || state.currentWorkdir || els.workdir.value || "").trim();
  if (!target) return;
  state.results = null;
  renderResults();
  const payload = await api(`/api/results?workdir=${encodeURIComponent(target)}`);
  state.results = payload.code
    ? {
        workdir: target,
        download_dir: "",
        available: false,
        load_error: true,
        total_sessions: 0,
        total_videos: 0,
        empty_message: payload.user_message || "读取下载结果失败。",
        panel_state: {
          state: "failed",
          tone: "danger",
          eyebrow: "读取失败",
          title: "结果页暂时无法读取",
          message: payload.user_message || "下载结果读取失败，请稍后重试。",
          action_label: "重新读取",
          action: "refresh-results",
          action_style: "btn3",
        },
        sessions: [],
      }
    : payload;
  renderResults();
}

function reviewFilterItems(items) {
  const scope = els.reviewScope?.value || "all";
  const keyword = String(els.reviewSearch?.value || "").trim().toLowerCase();
  const sort = els.reviewSort?.value || "recommended";
  const filtered = (items || []).filter((item) => {
    if (scope === "selected" && !item.selected) return false;
    if (scope === "agent_selected" && !item.agent_selected) return false;
    if (scope === "manual_review" && !item.manual_review) return false;
    if (scope === "low_similarity" && !item.low_similarity) return false;
    if (scope === "modified" && !item.selection_modified) return false;
    if (!keyword) return true;
    const haystack = [
      item.title,
      item.channel,
      item.watch_url,
      item.description_preview,
      item.reasons_summary,
    ].join("\n").toLowerCase();
    return haystack.includes(keyword);
  });
  filtered.sort((a, b) => {
    if (sort === "vector_desc") return Number(b.vector_score || 0) - Number(a.vector_score || 0);
    if (sort === "date_desc") return Number(String(b.upload_date || "").replace(/\D/g, "") || 0) - Number(String(a.upload_date || "").replace(/\D/g, "") || 0);
    if (sort === "duration_desc") return Number(b.duration_seconds || 0) - Number(a.duration_seconds || 0);
    if (sort === "title_asc") return String(a.title || "").localeCompare(String(b.title || ""), "zh-CN");
    const rank = (item) => {
      if (item.selected) return 0;
      if (item.manual_review) return 1;
      if (item.agent_selected) return 2;
      if (item.low_similarity) return 4;
      return 3;
    };
    const diff = rank(a) - rank(b);
    if (diff !== 0) return diff;
    const vectorDiff = Number(b.vector_score || 0) - Number(a.vector_score || 0);
    if (vectorDiff !== 0) return vectorDiff;
    return Number(b.score || 0) - Number(a.score || 0);
  });
  return filtered;
}

function reviewSummaryMarkup(summary) {
  const items = [
    ["全部候选", summary?.total_count ?? 0, "neutral"],
    ["已选下载", summary?.selected_count ?? 0, "success"],
    ["Agent 推荐", summary?.agent_selected_count ?? 0, "info"],
    ["需复核", summary?.manual_review_count ?? 0, "warn"],
    ["手动改动", summary?.modified_count ?? 0, "neutral"],
  ];
  return items.map(([label, count, toneName]) => `<span class="pill tone-${toneName}">${esc(label)} ${esc(count)}</span>`).join("");
}

function reviewCardMarkup(item) {
  const thumb = item.thumbnail_url
    ? `<img src="${escA(item.thumbnail_url)}" alt="${escA(item.title || "视频缩略图")}" loading="lazy" referrerpolicy="no-referrer" />`
    : `<div class="thumb-fallback">暂无封面</div>`;
  const scoreBits = [];
  if (item.vector_score != null) scoreBits.push(`语义 ${Number(item.vector_score).toFixed(3)}`);
  if (item.score != null) scoreBits.push(`规则 ${item.score}`);
  const scoreText = scoreBits.length ? scoreBits.join(" · ") : "未记录评分";
  const selectedText = item.selected ? "已加入下载" : "未加入下载";
  return `
    <article class="review-card" data-review-key="${escA(item.selection_key)}">
      <div class="review-check">
        <label class="review-checker">
          <input type="checkbox" data-review-toggle="${escA(item.selection_key)}" ${item.selected ? "checked" : ""} ${state.review?.editable ? "" : "disabled"} />
          <span>${esc(selectedText)}</span>
        </label>
      </div>
      <div class="review-thumb">${thumb}</div>
      <div class="review-body">
        <div class="review-headline">
          <h4>${esc(item.title || "未命名视频")}</h4>
          <div class="review-badges">
            <span class="pill tone-${escA(item.status_tone || "neutral")}">${esc(item.status_label || "候选")}</span>
            <span class="pill tone-${item.selected ? "success" : (item.agent_selected ? "info" : "neutral")}">${esc(item.agent_selected ? "Agent 推荐" : "候选观察")}</span>
            ${item.low_similarity ? '<span class="pill tone-danger">低相似</span>' : ""}
            ${item.selection_modified ? '<span class="pill tone-neutral">已手动调整</span>' : ""}
          </div>
        </div>
        <div class="review-meta-row">
          <span>${esc(item.channel || "未知频道")}</span>
          <span>${esc(fmtUploadDate(item.upload_date))}</span>
          <span>${esc(fmtVideoDur(item.duration_label, item.duration_seconds))}</span>
          <span>${esc(scoreText)}</span>
        </div>
        <div class="review-decision tone-${escA(item.status_tone || "neutral")}">
          <strong>${esc(item.decision_label || "筛选结论")}</strong>
          <span>${esc(item.decision_detail || "")}</span>
        </div>
        <p class="review-desc">${esc(item.description_preview || "暂无摘要信息。")}</p>
        <div class="review-foot">
          <div class="review-reason">${esc(item.reasons_summary || "暂无筛选原因记录")}</div>
          <div class="mini-actions">
            <a class="btn2 review-link" href="${escA(item.watch_url || "#")}" target="_blank" rel="noreferrer noopener">打开链接</a>
            <button class="btn2" type="button" data-review-copy="${escA(item.watch_url || "")}">复制链接</button>
          </div>
        </div>
      </div>
    </article>
  `;
}

function currentReviewPageItems() {
  const pageSize = Math.max(1, Number(state.reviewPageSize || 12));
  const start = Math.max(0, (state.reviewPage - 1) * pageSize);
  const end = Math.min(state.reviewRenderItems.length, start + pageSize);
  return state.reviewRenderItems.slice(start, end);
}

function renderReview() {
  const review = state.review;
  const fallbackText = "先运行或选中一个任务，然后在这里决定哪些视频真正进入下载。";
  const stage = currentStage();
  const selectedCount = reviewSelectedCount();
  if (!state.currentTaskId) {
    state.reviewRenderItems = [];
    els.reviewStatusPill.className = "pill";
    els.reviewStatusPill.textContent = "未加载";
    els.reviewSummaryPills.innerHTML = "";
    els.reviewPageLabel.textContent = "第 0/0 页";
    els.reviewList.innerHTML = panelStateMarkup({
      eyebrow: "等待任务",
      title: "还没有可审核的视频",
      message: fallbackText,
      actionLabel: "创建新任务",
      action: "focus-run",
    });
    setReviewStatusText(fallbackText);
    [els.btnReviewSelectRecommended, els.btnReviewSelectPage, els.btnReviewClearPage, els.btnReviewPrev, els.btnReviewNext].forEach((button) => {
      if (button) button.disabled = true;
    });
    if (els.btnStartSelectedDownload) {
      els.btnStartSelectedDownload.disabled = true;
      els.btnStartSelectedDownload.textContent = "开始下载已勾选视频";
    }
    return;
  }

  if (!review) {
    els.reviewStatusPill.className = "pill tone-info";
    els.reviewStatusPill.textContent = "加载中";
    els.reviewSummaryPills.innerHTML = "";
    els.reviewPageLabel.textContent = "第 0/0 页";
    els.reviewList.innerHTML = panelStateMarkup({
      toneName: "info",
      eyebrow: "处理中",
      title: "正在读取候选视频",
      message: "正在准备审核列表、封面和推荐结果。",
    });
    setReviewStatusText(state.reviewStatusText || "正在读取候选视频列表...");
    if (els.btnStartSelectedDownload) {
      els.btnStartSelectedDownload.disabled = true;
      els.btnStartSelectedDownload.textContent = "加载候选中...";
    }
    return;
  }

  const editable = !!review.editable;
  const pillTone = state.reviewSaveInFlight ? "info" : editable ? "success" : "neutral";
  els.reviewStatusPill.className = `pill tone-${pillTone}`;
  els.reviewStatusPill.textContent = state.reviewSaveInFlight ? "保存中" : editable ? "可调整" : "只读";
  els.reviewSummaryPills.innerHTML = reviewSummaryMarkup(review.summary);

  if (!review.available || !(review.items || []).length) {
    state.reviewRenderItems = [];
    els.reviewPageLabel.textContent = "第 0/0 页";
    els.reviewList.innerHTML = panelStateMarkup(panelStateOptions(
      review.panel_state,
      review.load_error
        ? {
            toneName: "danger",
            eyebrow: "读取失败",
            title: "候选视频暂时不可用",
            message: review.empty_message || "候选视频读取失败，请稍后重试。",
            actionLabel: "重新读取",
            action: "refresh-review",
            actionStyle: "btn3",
          }
        : {
            eyebrow: "没有候选",
            title: "当前任务还没有候选视频",
            message: review.empty_message || "如果任务还在搜索或筛选，稍后再回来查看；如果已经完成，可以检查日志确认发生了什么。",
            actionLabel: "查看状态",
            action: "go-status",
          }
    ));
    setReviewStatusText(review.empty_message || "当前没有可审核的视频候选。");
    [els.btnReviewSelectRecommended, els.btnReviewSelectPage, els.btnReviewClearPage, els.btnReviewPrev, els.btnReviewNext].forEach((button) => {
      if (button) button.disabled = true;
    });
    if (els.btnStartSelectedDownload) {
      els.btnStartSelectedDownload.disabled = true;
      els.btnStartSelectedDownload.textContent = "开始下载已勾选视频";
    }
    return;
  }

  state.reviewRenderItems = reviewFilterItems(review.items || []);
  const pageSize = Math.max(1, Number(state.reviewPageSize || 12));
  const total = state.reviewRenderItems.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (state.reviewPage > pages) state.reviewPage = pages;
  if (state.reviewPage < 1) state.reviewPage = 1;
  const pageItems = currentReviewPageItems();
  const start = total ? (state.reviewPage - 1) * pageSize + 1 : 0;
  const end = total ? start + pageItems.length - 1 : 0;

  els.reviewPageLabel.textContent = total ? `第 ${state.reviewPage}/${pages} 页 · ${start}-${end} / ${total}` : "第 0/0 页";
  els.reviewList.innerHTML = pageItems.length
    ? pageItems.map(reviewCardMarkup).join("")
    : panelStateMarkup({
        eyebrow: "筛选后为空",
        title: "当前筛选条件下没有匹配视频",
        message: "可以清空搜索词、切回“全部候选”，或者恢复默认排序后再看一遍。",
        actionLabel: "清空筛选",
        action: "clear-review-filters",
      });

  [els.btnReviewSelectRecommended, els.btnReviewSelectPage, els.btnReviewClearPage].forEach((button) => {
    if (button) button.disabled = !editable;
  });
  if (els.btnReviewPrev) els.btnReviewPrev.disabled = state.reviewPage <= 1;
  if (els.btnReviewNext) els.btnReviewNext.disabled = state.reviewPage >= pages;
  if (els.btnStartSelectedDownload) {
    const awaitingConfirm = stage === "awaiting_confirmation";
    const activeDownload = ["preparing_download", "downloading", "finalizing"].includes(stage);
    let label = "开始下载已勾选视频";
    if (state.pendingDownloadLaunch) label = "正在启动下载...";
    else if (state.pendingResumeTaskId) label = "正在确认...";
    else if (awaitingConfirm) label = "确认并下载已勾选视频";
    else if (activeDownload) label = "下载进行中";
    else if (selectedCount <= 0) label = "请先勾选要下载的视频";
    els.btnStartSelectedDownload.textContent = label;
    els.btnStartSelectedDownload.disabled = !canLaunchSelectedDownload();
  }

  const reviewModeText = editable
    ? `已选择 ${review.summary?.selected_count ?? 0} 条视频进入下载队列。你可以直接勾选或取消勾选，系统会自动保存。`
    : `当前阶段为只读，共选择 ${review.summary?.selected_count ?? 0} 条视频进入下载队列。`;
  setReviewStatusText(state.reviewStatusText || reviewModeText);
}

async function loadReview(taskId, workdir) {
  if (!taskId || !workdir) return;
  const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}/review?workdir=${encodeURIComponent(workdir)}`);
  if (payload.code) {
    state.review = {
      task_id: taskId,
      workdir,
      available: false,
      editable: false,
      load_error: true,
      empty_message: payload.user_message || "读取候选视频失败。",
      panel_state: {
        state: "failed",
        tone: "danger",
        eyebrow: "读取失败",
        title: "候选视频暂时不可用",
        message: payload.user_message || "候选视频读取失败，请稍后重试。",
        action_label: "重新读取",
        action: "refresh-review",
        action_style: "btn3",
      },
      items: [],
      summary: { total_count: 0, selected_count: 0, agent_selected_count: 0, manual_review_count: 0, low_similarity_count: 0, modified_count: 0 },
    };
    setReviewStatusText(payload.user_message || "读取候选视频失败。");
    renderReview();
    return;
  }
  state.review = payload;
  syncReviewSummaryIntoLifecycle();
  setReviewStatusText(
    payload.available
      ? `已读取 ${payload.summary?.total_count ?? 0} 条候选视频，当前选择 ${payload.summary?.selected_count ?? 0} 条进入下载。`
      : (payload.empty_message || "当前没有可审核的视频候选。")
  );
  renderReview();
}

function applyReviewSelection(predicate) {
  if (!state.review?.editable || !Array.isArray(state.review?.items)) return;
  state.review.items = state.review.items.map((item) => {
    const selected = !!predicate(item);
    return { ...item, selected, selection_modified: selected !== item.agent_selected };
  });
  if (state.review.summary) {
    state.review.summary.selected_count = state.review.items.filter((item) => item.selected).length;
    state.review.summary.modified_count = state.review.items.filter((item) => item.selected !== item.agent_selected).length;
  }
  syncReviewSummaryIntoLifecycle();
  renderReview();
  renderStatus(state.currentLifecycle || {});
  scheduleReviewSave();
}

function setReviewPageSelection(selected) {
  if (!state.review?.editable || !Array.isArray(state.review?.items)) return;
  const keys = new Set(currentReviewPageItems().map((item) => item.selection_key));
  state.review.items = state.review.items.map((item) => (
    keys.has(item.selection_key)
      ? { ...item, selected, selection_modified: selected !== item.agent_selected }
      : item
  ));
  if (state.review.summary) {
    state.review.summary.selected_count = state.review.items.filter((item) => item.selected).length;
    state.review.summary.modified_count = state.review.items.filter((item) => item.selected !== item.agent_selected).length;
  }
  syncReviewSummaryIntoLifecycle();
  renderReview();
  renderStatus(state.currentLifecycle || {});
  scheduleReviewSave();
}

function scheduleReviewSave() {
  if (!state.review?.editable || !state.currentTaskId || !state.currentWorkdir) return;
  if (state.reviewSaveTimer) clearTimeout(state.reviewSaveTimer);
  setReviewStatusText("正在保存下载选择...");
  state.reviewSaveTimer = setTimeout(() => persistReviewSelection(), 220);
}

async function persistReviewSelection() {
  if (!state.review?.editable || !state.currentTaskId || !state.currentWorkdir) return true;
  const seq = ++state.reviewSaveSeq;
  state.reviewSaveInFlight = true;
  renderReview();
  const payload = await api(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/review-selection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workdir: state.currentWorkdir,
      selected_keys: (state.review.items || []).filter((item) => item.selected).map((item) => item.selection_key),
    }),
  });
  if (seq !== state.reviewSaveSeq) return false;
  state.reviewSaveInFlight = false;
  if (payload.code) {
    setReviewStatusText(payload.user_message || "保存下载选择失败。");
    renderReview();
    return false;
  }
  state.review = payload;
  syncReviewSummaryIntoLifecycle();
  setReviewStatusText(`已保存下载选择，当前有 ${payload.summary?.selected_count ?? 0} 条视频会进入下载。`);
  renderReview();
  renderStatus(state.currentLifecycle || {});
  return true;
}

function failureDiagnosisMarkup(failure) {
  if (!failure) return "";
  const actions = Array.isArray(failure.actions) ? failure.actions.filter((item) => String(item || "").trim()) : [];
  return `
    <div class="stack">
      <div class="message"><strong>${esc(failure.title || "任务执行失败")}</strong>${failure.failed_step_title ? ` · ${esc(failure.failed_step_title)}` : ""}</div>
      <div class="subtle">${esc(failure.summary || "当前任务执行失败。")}</div>
      ${failure.recovery ? `<div class="message" style="margin-top:12px"><strong>建议处理</strong>${esc(failure.recovery)}</div>` : ""}
      ${actions.length ? `<div class="pills" style="margin-top:12px">${actions.map((item) => `<span class="pill tone-neutral">${esc(item)}</span>`).join("")}</div>` : ""}
    </div>
  `;
}

function renderStatus(payload) {
  const task = payload?.task || null;
  const summary = payload?.summary || null;
  const execution = payload?.execution || task?.execution || null;
  const downloadProgress = payload?.download_progress || task?.download_progress || null;
  const stage = payload?.workspace_stage || fallbackStage(task, downloadProgress);
  const stageLabel = payload?.workspace_stage_label || fallbackStageLabel(stage);
  const primaryMessage = payload?.primary_message || summary?.last_message || task?.progress_text || "等待任务开始。";
  const failure = payload?.failure || payload?.result?.failure || null;
  const confirmation = payload?.confirmation || null;
  const downloadEntry = payload?.download_entry || fallbackEntry(task, stage);
  const updated = task?.updated_at || summary?.updated_at || downloadProgress?.updated_at || "";
  const currentStep = task?.current_step_title || "暂无步骤";
  const taskStatus = task?.status_label || task?.status || stageLabel;
  const progress = progressPct(task, downloadProgress);
  const runningNow = ["preparing_download", "downloading", "finalizing"].includes(stage) || String(task?.status || "").toLowerCase() === "running";
  const activeElapsed = task?.active_elapsed_seconds ?? payload?.active_elapsed_seconds ?? null;
  const selectedCount = reviewSelectedCount();
  const totalReviewCount = Number(state.review?.summary?.total_count || 0);
  const hasReview = !!state.review?.available;
  const agentFailure = state.agentFailure;

  setHeader(task, summary, stageLabel, primaryMessage);
  els.workspaceActionsBar.innerHTML = workspaceActionsMarkup({ stage, selectedCount, downloadEntry, hasReview, agentFailure });

  els.updatedPill.textContent = `最近更新: ${fmtTime(updated)}`;
  els.workspaceStagePill.className = `pill tone-${stageTone(stage)}`;
  els.workspaceStagePill.textContent = stageLabel;
  els.primaryMessage.textContent = primaryMessage;
  els.overallTitle.textContent = currentStep;
  els.overallValue.textContent = `${progress}%`;
  els.overallFill.style.width = `${progress}%`;
  els.overallDetail.textContent = stage === "failed"
    ? (failure?.recovery || primaryMessage)
    : (task?.progress_text || primaryMessage);

  const metricsHtml = [
    { id: "step", k: "当前步骤", v: currentStep, d: task?.progress_text || "等待执行" },
    { id: "stage", k: "当前阶段", v: stageLabel, d: taskStatus },
    { id: "selected", k: "待下载视频", v: `${selectedCount} 条`, d: totalReviewCount ? `共 ${totalReviewCount} 条候选，可在审核面板调整` : "候选视频生成后可在审核面板调整" },
    { id: "elapsed", k: "已耗时", v: activeElapsed == null ? "-" : fmtDur(activeElapsed), d: activeElapsed == null ? "任务尚未产生有效运行时间" : "累计有效运行时长" },
    { id: "updated", k: "最近更新时间", v: fmtTime(updated), d: updated ? "按浏览器本地时间显示" : "暂无时间信息" },
  ].map((item) => (
    `<article class="metric" data-metric="${escA(item.id)}"><div class="k">${esc(item.k)}</div><div class="v">${esc(item.v)}</div><div class="d">${esc(item.d)}</div></article>`
  )).join("");
  if (metricsHtml !== state.renderCache.metrics) {
    els.metricGrid.innerHTML = metricsHtml;
    state.renderCache.metrics = metricsHtml;
  }

  let executionHtml = "";
  if (execution) {
    const plannerName = String(execution.planner_name || "").trim();
    const plannerNotes = Array.isArray(execution.planner_notes) ? execution.planner_notes.filter(Boolean) : [];
    const recentEvent = execution.recent_event || null;
    const recentEventText = recentEvent
      ? `${recentEvent.message || recentEvent.event_type || "最近事件"} · ${compactTime(recentEvent.timestamp)}`
      : "最近事件会在执行开始后显示在这里。";
    executionHtml = `
      <div class="execution-shell">
        <div class="execution-summary">
          <article class="metric">
            <div class="k">规划器</div>
            <div class="v">${esc(plannerName || "当前任务未记录规划器名称")}</div>
            <div class="d">${plannerNotes.length ? esc(plannerNotes.join(" · ")) : "这里会显示本次计划的来源和备注。"}</div>
          </article>
          <article class="metric">
            <div class="k">步骤进度</div>
            <div class="v">${esc(`${execution.completed_steps || 0} / ${execution.total_steps || 0}`)}</div>
            <div class="d">${esc(`剩余 ${execution.remaining_steps || 0} 步`)}</div>
          </article>
        </div>
        <div class="execution-grid">
          ${stepSummaryMarkup("当前步骤", execution.current_step, "当前步骤未就绪")}
          ${stepSummaryMarkup("下一步", execution.next_step, "没有下一步")}
          ${stepSummaryMarkup("确认边界", execution.pending_confirmation_step, "当前没有确认门")}
          ${stepSummaryMarkup(execution.failed_step ? "失败步骤" : "最近完成", execution.failed_step || execution.last_completed_step, execution.failed_step ? "暂无失败步骤" : "尚未完成任何步骤")}
        </div>
        <div class="execution-event">
          <div class="k">最近事件</div>
          <div class="message">${esc(recentEventText)}</div>
        </div>
      </div>
    `;
  } else {
    executionHtml = "任务开始后，这里会显示当前步骤、下一步、确认边界和最近事件。";
  }
  if (executionHtml !== state.renderCache.execution) {
    els.executionBox.className = execution ? "" : "empty";
    els.executionBox.innerHTML = executionHtml;
    state.renderCache.execution = executionHtml;
  }
  setTiming(activeElapsed, runningNow);

  const progressTime = parseDate(downloadProgress?.updated_at);
  const staleMs = progressTime ? Date.now() - progressTime.getTime() : null;
  let downloadHtml = "";
  if (downloadProgress) {
    const staleNote = staleMs != null && staleMs > 3000 && ["preparing_download", "downloading", "finalizing"].includes(stage)
      ? "等待下一次进度刷新"
      : "进度持续刷新中";
    downloadHtml = `
      <div class="progress">
        <div class="progress-meta">
          <strong>${esc(downloadProgress.current_video_label || downloadProgress.current_video_id || "当前下载项")}</strong>
          <span>${esc(Number(downloadProgress.percent || 0).toFixed(1))}%</span>
        </div>
        <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, Number(downloadProgress.percent || 0)))}%"></div></div>
        <div class="subtle">最近更新: ${esc(fmtTime(downloadProgress.updated_at))} · ${esc(staleNote)}</div>
      </div>
      <div class="metrics">
        <article class="metric"><div class="k">已下载 / 总大小</div><div class="v">${esc(fmtBytes(downloadProgress.downloaded_bytes))} / ${esc(fmtBytes(downloadProgress.total_bytes))}</div></article>
        <article class="metric"><div class="k">当前速度</div><div class="v">${esc(downloadProgress.speed_text || "-")}</div></article>
        <article class="metric"><div class="k">当前视频 ID</div><div class="v">${esc(downloadProgress.current_video_id || "-")}</div></article>
        <article class="metric"><div class="k">下载阶段</div><div class="v">${esc(downloadProgress.phase || "-")}</div></article>
      </div>
    `;
  } else if (stage === "awaiting_confirmation") {
    downloadHtml = "等待你确认后，任务才会进入下载阶段。";
  } else if (stage === "preparing_download") {
    downloadHtml = primaryMessage || "已确认下载，正在准备下载环境和启动下载任务。";
  } else if (stage === "downloading") {
    downloadHtml = primaryMessage || "正在下载中，详细进度会在下一次刷新后显示。";
  } else if (stage === "finalizing") {
    downloadHtml = primaryMessage || "下载流已结束，正在整理最终结果。";
  } else if (stage === "completed") {
    downloadHtml = primaryMessage || "下载已经完成，可直接通过下方入口打开目录查看视频。";
  } else if (stage === "failed") {
    downloadHtml = failureDiagnosisMarkup(failure) || primaryMessage || "任务已失败，请切换到日志标签查看失败原因。";
  } else {
    downloadHtml = "当前还没有下载进度。开始下载后，这里会显示百分比、速度、当前视频以及最近更新时间。";
  }
  els.downloadPhase.className = `pill tone-${stageTone(stage)}`;
  els.downloadPhase.textContent = downloadProgress?.phase || stageLabel;
  if (downloadHtml !== state.renderCache.download) {
    els.downloadBox.className = downloadProgress ? "" : "empty";
    els.downloadBox.innerHTML = downloadHtml;
    state.renderCache.download = downloadHtml;
  }

  const entryTone = downloadEntry?.ready ? "success" : "info";
  els.entryStatusPill.className = `pill tone-${entryTone}`;
  els.entryStatusPill.textContent = downloadEntry?.ready ? "已就绪" : "目标目录";
  let entryHtml = "任务完成后，这里会提供打开下载目录的唯一入口。";
  if (downloadEntry?.path) {
    entryHtml = `
      <div class="message"><strong>${esc(downloadEntry.label || "查看目标目录")}</strong>${downloadEntry.ready ? "。下载已经完成，可以直接打开目录查看视频。" : "。任务还未完成，这里只显示本次下载会使用的目标目录。"}</div>
      <div class="path">${esc(downloadEntry.path)}</div>
      ${downloadEntry.ready ? `<div class="path-actions" style="margin-top:12px"><button class="btn" type="button" data-entry-action="open" data-entry-path="${escA(downloadEntry.path)}">打开下载目录</button><button class="btn2" type="button" data-entry-action="copy" data-entry-path="${escA(downloadEntry.path)}">复制路径</button></div>` : ""}
    `;
  }
  if (entryHtml !== state.renderCache.entry) {
    els.entryBox.className = downloadEntry?.path ? "" : "empty";
    els.entryBox.innerHTML = entryHtml;
    state.renderCache.entry = entryHtml;
  }

  let confirmHtml = "";
  if (agentFailure) {
    confirmHtml = failureRecoveryMarkup(agentFailure);
  } else if (confirmation?.required && task?.task_id) {
    const waiting = state.pendingResumeTaskId === task.task_id;
    const reviewKnown = !!state.review && state.review.available;
    const allowConfirm = !reviewKnown || selectedCount > 0;
    confirmHtml = `
      <section class="inner">
        <div class="section">
          <h3>需要确认后继续下载</h3>
          <span class="pill tone-warn">确认边界</span>
        </div>
        <div class="message">当前任务在下载前进入了确认边界。待确认步骤: ${esc(confirmation.step_title || currentStep)}。${reviewKnown ? `当前已选择 ${esc(selectedCount)} 条视频进入下载队列。` : "你可以先切到审核面板确认具体要下载的视频。"}${allowConfirm ? "确认后将继续执行下载。" : "请先在审核面板至少选择 1 条视频。"} </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn" id="btnConfirmNow" type="button" ${(waiting || !allowConfirm) ? "disabled" : ""}>${esc(waiting ? "正在确认..." : (allowConfirm ? (confirmation.cta_label || "确认下载并继续") : "请先选择视频"))}</button>
          <button class="btn2" id="btnRefreshNow" type="button">刷新当前状态</button>
        </div>
      </section>
    `;
  } else if (state.pendingResumeTaskId && task?.task_id === state.pendingResumeTaskId && stage === "preparing_download") {
    confirmHtml = `
      <section class="inner">
        <div class="section">
          <h3>已确认，正在进入下载阶段</h3>
          <span class="pill tone-info">准备中</span>
        </div>
        <div class="message">系统已经收到继续执行指令，正在启动下载任务。下载进度出现后，这里会自动收起。</div>
      </section>
    `;
  }
  if (confirmHtml !== state.renderCache.confirm) {
    els.confirmWrap.innerHTML = confirmHtml;
    state.renderCache.confirm = confirmHtml;
  }
  if ($("btnConfirmNow")) $("btnConfirmNow").addEventListener("click", () => resumeTask(task?.task_id || "", true));
  if ($("btnRefreshNow")) $("btnRefreshNow").addEventListener("click", () => loadTaskLifecycle(task?.task_id || "", els.workdir.value.trim()));
}

function applyStageFallback(payload) {
  const stage = String(payload?.workspace_stage || "").trim();
  const message = String(payload?.primary_message || "").trim();
  if (!stage || !message) return;
  if (!["preparing_download", "downloading", "finalizing", "completed", "failed"].includes(stage)) return;
  els.downloadPhase.className = `pill tone-${stageTone(stage)}`;
  els.downloadPhase.textContent = payload?.download_progress?.phase || stage;
  els.downloadBox.className = payload?.download_progress ? "" : "empty";
  els.downloadBox.textContent = message;
}

function clearWorkspace() {
  state.currentTaskId = "";
  state.currentTaskStatus = "";
  state.currentLifecycle = null;
  state.review = null;
  state.reviewRenderItems = [];
  state.reviewPage = 1;
  state.reviewStatusText = "";
  state.pendingDownloadLaunch = false;
  clearAgentFailure();
  if (state.reviewSaveTimer) {
    clearTimeout(state.reviewSaveTimer);
    state.reviewSaveTimer = null;
  }
  state.reviewSaveInFlight = false;
  state.currentLogsCount = 0;
  state.pendingResumeTaskId = "";
  state.graphDebug = null;
  state.renderCache = { metrics: "", execution: "", graphDebug: "", download: "", entry: "", confirm: "", queue: "", logs: "" };
  stopPolling();
  if (state.statusClockTimer) {
    clearInterval(state.statusClockTimer);
    state.statusClockTimer = null;
  }
  setHeader(null, null, "未开始", "运行或选择一个任务后，这里会显示当前阶段、下载进度、日志以及下载入口。");
  els.updatedPill.textContent = "最近更新: -";
  els.workspaceStagePill.className = "pill tone-info";
  els.workspaceStagePill.textContent = "任务准备中";
  els.primaryMessage.textContent = "等待任务开始。";
  els.workspaceActionsBar.innerHTML = workspaceActionsMarkup({ stage: "planned", selectedCount: 0, downloadEntry: null, hasReview: false, agentFailure: null });
  els.overallTitle.textContent = "等待任务开始";
  els.overallValue.textContent = "0%";
  els.overallFill.style.width = "0%";
  els.overallDetail.textContent = "尚未开始执行。";
  els.metricGrid.innerHTML = '<article class="metric"><div class="k">当前步骤</div><div class="v">-</div><div class="d">暂无步骤信息</div></article>';
  els.executionBox.className = "empty";
  els.executionBox.textContent = "任务开始后，这里会显示当前步骤、下一步、确认边界和最近事件。";
  if (els.graphDebugPanel) els.graphDebugPanel.hidden = true;
  if (els.graphDebugPill) {
    els.graphDebugPill.className = "pill tone-neutral";
    els.graphDebugPill.textContent = "开发模式";
  }
  if (els.graphDebugBox) {
    els.graphDebugBox.className = "empty";
    els.graphDebugBox.textContent = "仅本地开发模式下显示最近一个 LangGraph checkpoint。";
  }
  els.confirmWrap.innerHTML = "";
  els.downloadPhase.className = "pill";
  els.downloadPhase.textContent = "未开始";
  els.downloadBox.className = "empty";
  els.downloadBox.textContent = "当前还没有下载进度。开始下载后，这里会显示百分比、速度、当前视频以及最近更新时间。";
  els.entryStatusPill.className = "pill";
  els.entryStatusPill.textContent = "目标目录";
  els.entryBox.className = "empty";
  els.entryBox.textContent = "任务完成后，这里会提供打开下载目录的唯一入口。";
  els.reviewStatusPill.className = "pill";
  els.reviewStatusPill.textContent = "未加载";
  els.reviewSummaryPills.innerHTML = "";
  els.reviewPageLabel.textContent = "第 0/0 页";
  els.reviewList.innerHTML = panelStateMarkup({
    eyebrow: "等待任务",
    title: "还没有可审核的视频",
    message: "先运行或选中一个任务，然后在这里决定哪些视频真正进入下载。",
    actionLabel: "创建新任务",
    action: "focus-run",
  });
  setReviewStatusText("先运行或选中一个任务，然后在这里决定哪些视频真正进入下载。");
  els.logsCount.textContent = "0 行";
  els.logList.innerHTML = panelStateMarkup({
    eyebrow: "等待任务",
    title: "还没有日志内容",
    message: "选择一个任务后，这里会显示运行日志和下载输出。",
    actionLabel: "查看状态",
    action: "go-status",
  });
  setActionButtons();
  renderReview();
  renderResults();
}

async function copyText(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {}
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.focus();
  area.select();
  try {
    return document.execCommand("copy");
  } catch (_) {
    return false;
  } finally {
    area.remove();
  }
}

async function openPath(value) {
  const path = String(value || "").trim();
  if (!path) return;
  const response = await api("/api/system/open-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  els.workspaceSubtitle.textContent = response.code
    ? (response.user_message || "打开目录失败。")
    : "系统已尝试打开目标位置。";
}

async function handleUiAction(action, button = null) {
  if (action === "focus-run") {
    setTab("status");
    els.request.focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  if (action === "go-settings") {
    return setTab("settings");
  }
  if (action === "confirm-download") {
    return resumeTask(state.currentTaskId, true);
  }
  if (action === "go-review") {
    return setTab("review");
  }
  if (action === "go-results") {
    return setTab("results");
  }
  if (action === "go-logs") {
    return setTab("logs");
  }
  if (action === "go-status") {
    return setTab("status");
  }
  if (action === "retry-run") {
    return runTask(false);
  }
  if (action === "retry-resume") {
    return resumeTask(state.agentFailure?.taskId || state.currentTaskId || "", false);
  }
  if (action === "reload-current-task") {
    const taskId = state.agentFailure?.taskId || state.currentTaskId || "";
    const workdir = state.agentFailure?.workdir || state.currentWorkdir || els.workdir.value.trim();
    if (taskId && workdir) return loadTaskLifecycle(taskId, workdir);
    return refreshTasks(true);
  }
  if (action === "start-selected-download") {
    return startSelectedDownload();
  }
  if (action === "open-entry") {
    return openPath(button?.getAttribute("data-entry-path") || "");
  }
  if (action === "refresh-results") {
    return loadResults(els.workdir.value.trim());
  }
  if (action === "reset-results-filters") {
    state.resultsSearch = "";
    state.resultsScope = "all";
    state.resultsSort = "recent_desc";
    state.resultsPinLatest = true;
    state.resultsView = "gallery";
    els.resultsSearch.value = "";
    els.resultsScope.value = "all";
    els.resultsSort.value = "recent_desc";
    els.resultsPinLatest.checked = true;
    renderResults();
    return;
  }
  if (action === "refresh-logs") {
    return loadLogs(true);
  }
  if (action === "refresh-tasks") {
    return refreshTasks(true);
  }
  if (action === "refresh-review") {
    if (state.currentTaskId && state.currentWorkdir) return loadReview(state.currentTaskId, state.currentWorkdir);
    return;
  }
  if (action === "clear-review-filters") {
    els.reviewSearch.value = "";
    els.reviewScope.value = "all";
    els.reviewSort.value = "recommended";
    state.reviewPage = 1;
    renderReview();
    return;
  }
  if (action === "reset-task-filters") {
    state.onlyNeedsAttention = false;
    els.taskStatusFilter.value = "";
    els.taskSearch.value = "";
    els.taskSort.value = "updated_desc";
    $("btnToggleAttention").textContent = "仅看异常 / 待确认";
    return refreshTasks(true);
  }
}

async function loadLogs(force = false) {
  if (!state.currentTaskId || !state.currentWorkdir) {
    els.logsCount.textContent = "0 行";
    els.logList.innerHTML = panelStateMarkup({
      eyebrow: "等待任务",
      title: "还没有日志内容",
      message: "选择一个任务后，这里会显示运行日志和下载输出。",
      actionLabel: "查看任务队列",
      action: "go-status",
    });
    return;
  }
  if (!force && state.activeTab !== "logs") return;
  const payload = await api(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/logs?workdir=${encodeURIComponent(state.currentWorkdir)}&limit=200`);
  if (payload.code) {
    els.logsCount.textContent = "读取失败";
    els.logList.innerHTML = panelStateMarkup(panelStateOptions(
      payload.panel_state,
      {
        toneName: "danger",
        eyebrow: "读取失败",
        title: "日志暂时无法读取",
        message: payload.user_message || "日志读取失败，请稍后重试。",
        actionLabel: "重新读取",
        action: "refresh-logs",
        actionStyle: "btn3",
      }
    ));
    return;
  }
  state.currentLogsCount = Number(payload.count || 0);
  els.logsCount.textContent = `${state.currentLogsCount} 行`;
  const logsHtml = (payload.items || []).map((item) => (
    `<div class="log"><div class="lt">${esc(fmtTime(item.timestamp))}</div><div class="lk ${escA(String(item.kind || "info").toLowerCase())}">${esc(String(item.kind || "info").toLowerCase())}</div><div class="lm">${esc(item.message || "")}</div></div>`
  )).join("") || panelStateMarkup(panelStateOptions(
    payload.panel_state,
    {
      eyebrow: "暂无输出",
      title: "当前任务暂时没有日志输出",
      message: "如果任务刚启动，稍后刷新即可；如果长时间为空，可以回到状态页确认任务是否真的开始执行。",
    }
  ));
  if (logsHtml !== state.renderCache.logs) {
    els.logList.innerHTML = logsHtml;
    state.renderCache.logs = logsHtml;
  }
  if (state.activeTab === "logs") els.logList.scrollTop = els.logList.scrollHeight;
}

function canDelete(task) {
  return !["running", "awaiting_confirmation"].includes(String(task?.status || "").toLowerCase());
}

function renderQueuePills(queue) {
  const items = [
    ["", "全部", queue?.total ?? 0, "info"],
    ["running", "运行中", queue?.running ?? 0, "info"],
    ["awaiting_confirmation", "待确认", queue?.awaiting_confirmation ?? 0, "warn"],
    ["needs_attention", "异常", queue?.needs_attention ?? 0, "danger"],
    ["succeeded", "已完成", queue?.succeeded ?? 0, "success"],
  ];
  els.queuePills.innerHTML = items.map(([status, label, count, kind]) => {
    const active = (status === "needs_attention" && state.onlyNeedsAttention)
      || (status !== "needs_attention" && !state.onlyNeedsAttention && els.taskStatusFilter.value === status)
      || (!status && !state.onlyNeedsAttention && !els.taskStatusFilter.value);
    return `<button class="pill queue-pill-btn tone-${kind} ${active ? "active" : ""}" type="button" data-queue-filter="${escA(status)}">${esc(label)} ${esc(count)}</button>`;
  }).join("");
}

function taskMarkup(task) {
  const deletable = canDelete(task);
  const badge = task.badge_text ? `<span class="pill tone-${task.needs_confirmation ? "warn" : tone(task.status)}">${esc(task.badge_text)}</span>` : "";
  return `
    <article class="task" data-status="${escA(String(task.status || "").toLowerCase())}">
      <div class="task-top">
        <div>
          <div class="task-title">${esc(task.title || "未命名任务")}</div>
          <div class="task-line">${esc(task.current_step_title || "暂无步骤")} · ${esc(task.progress_text || "等待开始")}</div>
        </div>
        <div class="stage-row">
          <span class="pill tone-${tone(task.status)}">${esc(task.status_label || task.status || "-")}</span>
          ${badge}
        </div>
      </div>
      <div class="task-meta-row">
        <span>更新时间 ${esc(fmtTime(task.updated_at))}</span>
        <span>${esc(task.task_id || "-")}</span>
      </div>
      <div class="task-line">${esc(task.last_message || "暂无额外信息")}</div>
      <div class="task-actions">
        <button class="btn2" type="button" data-action="inspect" data-task-id="${escA(task.task_id)}">查看</button>
        <button class="btn2" type="button" data-action="resume" data-task-id="${escA(task.task_id)}">继续</button>
        <button class="btn3" type="button" data-action="delete" data-task-id="${escA(task.task_id)}" ${deletable ? "" : "disabled"} title="${escA(deletable ? "删除任务" : "运行中或等待确认的任务不能删除")}">删除</button>
      </div>
    </article>
  `;
}

function renderTaskEmpty(config) {
  const payload = typeof config === "string"
    ? {
        eyebrow: "暂无任务",
        title: "当前工作区还没有任务",
        message: config,
        actionLabel: "创建新任务",
        action: "focus-run",
      }
    : (config || {});
  state.taskItems = [];
  state.lastTaskSignature = "";
  state.taskRenderRange = { start: 0, end: 0 };
  els.taskListSpacer.style.height = "100%";
  els.taskListWindow.style.transform = "translateY(0)";
  els.taskListWindow.innerHTML = panelStateMarkup(payload);
}

function updateRowHeight() {
  const sample = state.taskItems[0];
  if (!sample) return;
  const probe = document.createElement("div");
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  probe.style.pointerEvents = "none";
  probe.style.width = `${Math.max(280, els.taskList.clientWidth - 18)}px`;
  probe.innerHTML = taskMarkup(sample);
  document.body.appendChild(probe);
  const item = probe.firstElementChild;
  if (item) state.taskRowHeight = Math.max(190, Math.ceil(item.getBoundingClientRect().height) + 10);
  probe.remove();
}

function renderTaskWindow(force = false) {
  const items = state.taskItems || [];
  if (!items.length) {
    return renderTaskEmpty({
      eyebrow: "暂无任务",
      title: "当前工作区还没有任务",
      message: "先在上方输入自然语言请求，然后运行第一条任务。",
      actionLabel: "创建新任务",
      action: "focus-run",
    });
  }
  const viewportHeight = els.taskList.clientHeight || 520;
  const top = els.taskList.scrollTop || 0;
  const row = Math.max(180, state.taskRowHeight || 210);
  const count = Math.ceil(viewportHeight / row);
  const start = Math.max(0, Math.floor(top / row) - state.taskOverscan);
  const end = Math.min(items.length, start + count + state.taskOverscan * 2);
  if (!force && start === state.taskRenderRange.start && end === state.taskRenderRange.end) return;
  state.taskRenderRange = { start, end };
  els.taskListSpacer.style.height = `${items.length * row}px`;
  els.taskListWindow.style.transform = `translateY(${start * row}px)`;
  els.taskListWindow.innerHTML = items.slice(start, end).map(taskMarkup).join("");
}

function renderTasks(payload) {
  const signature = stable(payload?.items || []);
  renderQueuePills(payload?.queue || {});
  const items = payload?.items || [];
  if (!items.length) {
    return renderTaskEmpty({
      eyebrow: "暂无任务",
      title: "当前筛选下没有任务",
      message: "可以切换队列过滤条件，或者直接创建一个新的下载任务。",
      actionLabel: "清空筛选",
      action: "reset-task-filters",
    });
  }
  if (signature === state.lastTaskSignature && items.length === state.taskItems.length) return;
  state.lastTaskSignature = signature;
  const previousTop = els.taskList.scrollTop;
  state.taskItems = items;
  updateRowHeight();
  els.taskList.scrollTop = previousTop;
  renderTaskWindow(true);
}

function taskQuery() {
  const params = new URLSearchParams({ workdir: els.workdir.value.trim(), limit: "100" });
  const status = els.taskStatusFilter.value.trim();
  const query = els.taskSearch.value.trim();
  const sort = els.taskSort.value.trim();
  if (status) params.set("status", status);
  if (state.onlyNeedsAttention) params.set("needs_attention", "true");
  if (query) params.set("q", query);
  if (sort) params.set("sort", sort);
  return params.toString();
}

async function refreshTasks(force = false) {
  const now = Date.now();
  if (!force && now - state.lastTaskRefreshAt < 1200) return;
  state.lastTaskRefreshAt = now;
  const seq = ++state.taskListRequestSeq;
  const payload = await api(`/api/tasks?${taskQuery()}`);
  if (seq !== state.taskListRequestSeq) return;
  if (payload.code) {
    return renderTaskEmpty({
      toneName: "danger",
      eyebrow: "读取失败",
      title: "任务队列暂时无法读取",
      message: payload.user_message || "任务列表加载失败。",
      actionLabel: "重新读取",
      action: "refresh-tasks",
      actionStyle: "btn3",
    });
  }
  renderTasks(payload);
}

function isLiveTaskStatus(status) {
  return ["planned", "running", "awaiting_confirmation"].includes(String(status || "").toLowerCase());
}

function currentStage() {
  return state.currentLifecycle?.workspace_stage || fallbackStage(state.currentLifecycle?.task, state.currentLifecycle?.download_progress);
}

function pollDelay(stage) {
  if (document.hidden) return 6000;
  if (stage === "awaiting_confirmation") return 2000;
  if (stage === "preparing_download") return 800;
  if (stage === "downloading") return 800;
  if (stage === "finalizing") return 1500;
  return 2500;
}

async function loadTaskLifecycle(taskId, workdir) {
  stopPolling();
  state.currentTaskId = taskId;
  state.currentWorkdir = workdir;
  state.review = null;
  state.graphDebug = null;
  state.reviewPage = 1;
  renderReview();
  const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}/lifecycle?workdir=${encodeURIComponent(workdir)}&events_limit=16`);
  if (payload.code) {
    els.workspaceSubtitle.textContent = payload.user_message || "读取任务详情失败。";
    return;
  }
  state.currentTaskId = taskId;
  state.currentWorkdir = workdir;
  state.currentTaskStatus = payload.task?.status || "";
  state.currentLifecycle = payload;
  if (!["failed", "awaiting_confirmation", "planned"].includes(String(payload.task?.status || "").toLowerCase())) {
    clearAgentFailure();
  }
  applyStageFallback(payload);
  renderStatus(payload);
  await loadGraphDebug(taskId, workdir);
  setActionButtons();
  await loadLogs(true);
  await loadReview(taskId, workdir);
  if (state.activeTab === "results" || payload.workspace_stage === "completed") await loadResults(workdir);
  if (isLiveTaskStatus(payload.task?.status)) startPolling(taskId, workdir);
}

function mergePoll(payload) {
  const previous = state.currentLifecycle || {};
  const task = previous.task ? { ...previous.task } : { task_id: payload.task_id };
  task.status = payload.status;
  task.status_label = payload.status_label;
  task.status_tone = payload.status_tone;
  task.needs_confirmation = payload.needs_confirmation;
  task.progress_text = payload.progress_text;
  task.active_elapsed_seconds = payload.active_elapsed_seconds ?? task.active_elapsed_seconds ?? null;
  task.current_step_title = payload.current_step_title;
  task.current_step_status = payload.current_step_status;
  if (payload.summary) {
    task.updated_at = payload.summary.updated_at;
    task.created_at = payload.summary.created_at;
  }
  return {
    ...previous,
    task,
    summary: payload.summary || previous.summary || null,
    failure: payload.failure || previous.failure || payload.result?.failure || previous.result?.failure || null,
    execution: payload.execution || previous.execution || task.execution || null,
    focus_summary: payload.focus_summary || previous.focus_summary || null,
    events_tail: payload.events_tail || [],
    download_progress: payload.download_progress || previous.download_progress || null,
    result: previous.result || null,
    active_elapsed_seconds: payload.active_elapsed_seconds ?? previous.active_elapsed_seconds ?? null,
    workspace_stage: payload.workspace_stage || previous.workspace_stage,
    workspace_stage_label: payload.workspace_stage_label || previous.workspace_stage_label,
    primary_message: payload.primary_message || previous.primary_message,
    confirmation: payload.confirmation || null,
    download_entry: payload.download_entry || previous.download_entry || null,
  };
}

async function loadGraphDebug(taskId, workdir) {
  if (!taskId || !workdir) {
    state.graphDebug = null;
    renderGraphDebug();
    return;
  }
  const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}/graph-debug?workdir=${encodeURIComponent(workdir)}`);
  state.graphDebug = payload.code ? null : payload;
  renderGraphDebug();
}

async function pollCurrentTask(taskId, workdir) {
  if (state.pollInFlight) return;
  state.pollInFlight = true;
  const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}/poll?workdir=${encodeURIComponent(workdir)}&events_limit=12`);
  state.pollInFlight = false;
  if (payload.code) {
    stopPolling();
    return;
  }
  state.currentTaskStatus = payload.status || "";
  state.currentLifecycle = mergePoll(payload);
  applyStageFallback(state.currentLifecycle);
  renderStatus(state.currentLifecycle);
  refreshTasks();
  if (payload.logs_tail_count !== state.currentLogsCount || state.activeTab === "logs") {
    loadLogs(true);
  }
  if (!isLiveTaskStatus(payload.status)) {
    stopPolling();
    await loadTaskLifecycle(taskId, workdir);
    await loadResults(workdir);
  }
}

function schedulePoll(taskId, workdir, delay = 2500) {
  stopPolling();
  state.pollTimer = setTimeout(async () => {
    if (document.hidden) {
      schedulePoll(taskId, workdir, 6000);
      return;
    }
    await pollCurrentTask(taskId, workdir);
    if (state.currentTaskId === taskId && isLiveTaskStatus(state.currentTaskStatus)) {
      schedulePoll(taskId, workdir, pollDelay(currentStage()));
    }
  }, delay);
}

function startPolling(taskId, workdir, immediate = false) {
  stopPolling();
  if (!taskId) return;
  schedulePoll(taskId, workdir, immediate ? 0 : pollDelay(currentStage()));
}

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
  state.pollInFlight = false;
}

function optimisticResumeState(taskId, auto) {
  if (!state.currentLifecycle?.task || state.currentTaskId !== taskId) return;
  state.currentLifecycle.task.status = "running";
  state.currentLifecycle.task.status_label = "运行中";
  state.currentLifecycle.task.active_elapsed_seconds = state.currentLifecycle.task.active_elapsed_seconds ?? 0;
  if (auto) {
    state.currentLifecycle.workspace_stage = "preparing_download";
    state.currentLifecycle.workspace_stage_label = "准备下载中";
    state.currentLifecycle.primary_message = "已确认，正在进入下载阶段。";
    state.currentLifecycle.confirmation = null;
  } else {
    state.currentLifecycle.workspace_stage = state.currentLifecycle.workspace_stage || "planned";
    state.currentLifecycle.primary_message = "正在恢复任务执行。";
  }
  renderStatus(state.currentLifecycle);
}

async function testConnection() {
  els.workspaceSubtitle.textContent = "正在测试 LLM 连接...";
  const response = await api("/api/agent/test-connection", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(runtimePayload()),
  });
  els.workspaceSubtitle.textContent = response.code
    ? formatAgentFeedback(response, "LLM 连接测试失败", "当前无法完成连接测试。")
    : formatAgentFeedback(response, "LLM 连接测试成功", "当前配置可以正常连到规划模型。");
}

async function runTask(auto = false) {
  const workdir = els.workdir.value.trim();
  const userRequest = els.request.value.trim();
  if (!workdir || !userRequest) return;
  state.currentWorkdir = workdir;
  clearAgentFailure();
  state.creatingTask = true;
  setActionButtons();
  await saveSettings(false);
  showTaskShell({
    title: "正在创建新任务",
    userRequest,
    status: "planned",
    statusLabel: "任务准备中",
    subtitle: "正在创建任务记录并准备执行...",
  });
  try {
    const plan = await api("/api/agent/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...runtimePayload(), user_request: userRequest, workdir }),
    });
    if (plan.code) {
      setAgentFailure("run", plan, { workdir });
      els.workspaceSubtitle.textContent = formatAgentFeedback(plan, "任务创建失败", "当前无法生成可执行计划。");
      renderStatus(state.currentLifecycle || {});
      return;
    }
    const taskId = plan.task_id || "";
    state.currentTaskId = taskId;
    state.currentWorkdir = workdir;
    state.currentTaskStatus = String(plan.status || "planned");
    showTaskShell({
      taskId,
      title: plan.title || "新任务",
      userRequest,
      status: String(plan.status || "planned"),
      statusLabel: "任务准备中",
      subtitle: "新任务已创建，正在启动执行。",
    });
    await refreshTasks(true);
    if (taskId) await loadTaskLifecycle(taskId, workdir);
    if (taskId) resumeTask(taskId, auto, true);
  } finally {
    state.creatingTask = false;
    setActionButtons();
  }
}

async function resumeTask(taskId = "", auto = true, skipSave = false) {
  const workdir = els.workdir.value.trim();
  if (!skipSave) await saveSettings(false);
  const id = taskId || state.currentTaskId;
  if (!id || state.pendingResumeTaskId === id) return;
  clearAgentFailure();
  state.pendingResumeTaskId = id;
  state.currentTaskId = id;
  state.currentWorkdir = workdir;
  state.currentTaskStatus = "running";
  els.workspaceSubtitle.textContent = auto ? "正在确认并继续执行任务..." : "正在恢复任务并继续执行...";
  optimisticResumeState(id, auto);
  setActionButtons();
  refreshTasks(true);
  startPolling(id, workdir, auto);
  if (auto) void pollCurrentTask(id, workdir);
  api("/api/agent/resume", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...runtimePayload(), workdir, task_id: id, auto_confirm: auto }),
  }).then(async (response) => {
    if (response.code) {
      stopPolling();
      setAgentFailure("resume", response, { taskId: id, workdir });
      els.workspaceSubtitle.textContent = formatAgentFeedback(response, "任务恢复失败", "当前任务无法继续恢复执行。");
      await loadTaskLifecycle(id, workdir);
      renderStatus(state.currentLifecycle || {});
      return;
    }
    state.currentTaskId = response.task_id || id;
    state.currentWorkdir = workdir;
    await refreshTasks(true);
    if (state.currentTaskId) await loadTaskLifecycle(state.currentTaskId, workdir);
  }).finally(() => {
    if (state.pendingResumeTaskId === id) state.pendingResumeTaskId = "";
    setActionButtons();
  });
}

async function startSelectedDownload() {
  if (!state.currentTaskId || !state.currentWorkdir || !canLaunchSelectedDownload()) return;
  const stage = currentStage();
  if (state.reviewSaveTimer) {
    clearTimeout(state.reviewSaveTimer);
    state.reviewSaveTimer = null;
    const ok = await persistReviewSelection();
    if (!ok) return;
  }
  if (stage === "awaiting_confirmation") {
    return resumeTask(state.currentTaskId, true);
  }
  state.pendingDownloadLaunch = true;
  setReviewStatusText("正在创建下载任务...");
  renderReview();
  const response = await api(`/api/tasks/${encodeURIComponent(state.currentTaskId)}/download-selected?workdir=${encodeURIComponent(state.currentWorkdir)}`, {
    method: "POST",
  });
  state.pendingDownloadLaunch = false;
  if (response.code) {
    setReviewStatusText(response.user_message || "启动下载失败。");
    renderReview();
    return;
  }
  setTab("status");
  els.workspaceSubtitle.textContent = response.message || "已创建下载任务，正在启动下载。";
  await refreshTasks(true);
  if (response.task_id) await loadTaskLifecycle(response.task_id, state.currentWorkdir);
  await loadResults(state.currentWorkdir);
  renderReview();
}

async function retryResultSession(sessionDir) {
  const target = String(sessionDir || "").trim();
  if (!target || !state.currentWorkdir || state.pendingRetrySessionDir) return;
  const session = (state.results?.sessions || []).find((item) => item.session_dir === target);
  if (session && !session.retry_available) {
    els.workspaceSubtitle.textContent = "这个下载会话当前没有可直接重试的失败项。";
    return;
  }
  state.pendingRetrySessionDir = target;
  els.workspaceSubtitle.textContent = "正在创建失败项重试任务...";
  renderResults();
  const response = await api("/api/results/retry-session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workdir: state.currentWorkdir, session_dir: target }),
  });
  state.pendingRetrySessionDir = "";
  if (response.code) {
    els.workspaceSubtitle.textContent = response.user_message || "创建失败项重试任务失败。";
    renderResults();
    return;
  }
  setTab("status");
  els.workspaceSubtitle.textContent = response.message || "已创建失败项重试任务。";
  await refreshTasks(true);
  if (response.task_id) await loadTaskLifecycle(response.task_id, state.currentWorkdir);
  await loadResults(state.currentWorkdir);
}

async function inspectResultTask(taskId) {
  const target = String(taskId || "").trim();
  const workdir = state.currentWorkdir || els.workdir.value.trim();
  if (!target || !workdir) return;
  setTab("status");
  els.workspaceSubtitle.textContent = "正在回到原任务...";
  await loadTaskLifecycle(target, workdir);
}

async function inspectResultReview(taskId) {
  const target = String(taskId || "").trim();
  const workdir = state.currentWorkdir || els.workdir.value.trim();
  if (!target || !workdir) return;
  els.workspaceSubtitle.textContent = "正在回到原任务审核页...";
  await loadTaskLifecycle(target, workdir);
  setTab("review");
}

function relaunchResultSession(sessionDir) {
  const session = findResultSession(sessionDir);
  if (!session?.source_task_user_request) {
    els.workspaceSubtitle.textContent = "当前结果没有可复用的原始任务请求。";
    return;
  }
  els.request.value = session.source_task_user_request;
  setTab("status");
  els.request.focus();
  window.scrollTo({ top: 0, behavior: "smooth" });
  const taskHint = session.source_task_title || session.session_name || "这次下载";
  els.workspaceSubtitle.textContent = `已带回原始请求，可基于“${taskHint}”继续修改后新建任务。`;
}

async function deleteTask(taskId) {
  const task = state.taskItems.find((item) => item.task_id === taskId);
  if (!task) return;
  if (!canDelete(task)) {
    els.workspaceSubtitle.textContent = "运行中或等待确认的任务不能删除。";
    return;
  }
  const ok = window.confirm(`确定删除任务“${task.title || task.task_id}”吗？\n\n会删除该任务记录，以及能明确定位到的下载会话目录/报告文件。共享 workdir 文件不会被删除。`);
  if (!ok) return;
  const response = await api(`/api/tasks/${encodeURIComponent(taskId)}?workdir=${encodeURIComponent(els.workdir.value.trim())}`, { method: "DELETE" });
  if (response.code) {
    els.workspaceSubtitle.textContent = response.user_message || "删除任务失败。";
    return;
  }
  if (state.currentTaskId === taskId) clearWorkspace();
  els.workspaceSubtitle.textContent = "任务已删除，队列已刷新。";
  await refreshTasks(true);
}

function onWorkdirChange() {
  state.currentWorkdir = els.workdir.value.trim();
  state.results = null;
  clearWorkspace();
  if (!state.currentWorkdir) return;
  loadSettings(state.currentWorkdir);
  loadResults(state.currentWorkdir);
  refreshTasks(true);
}

async function initializeWorkspace() {
  const bootstrap = await loadBootstrapDefaults();
  if (bootstrap?.workdir && !els.workdir.value.trim()) {
    els.workdir.value = bootstrap.workdir;
    state.currentWorkdir = bootstrap.workdir;
  } else {
    state.currentWorkdir = els.workdir.value.trim();
  }

  updateProviderPreset();
  updateAdvancedSummary();
  setActiveRequestTemplate("review");
  syncSettingsModeVisibility();
  updateSettingsSummary();
  state.reviewPageSize = Number(els.reviewPageSize.value || 12);
  state.resultsSearch = els.resultsSearch.value || "";
  state.resultsScope = els.resultsScope.value || "all";
  state.resultsSort = els.resultsSort.value || "recent_desc";
  state.resultsPinLatest = !!els.resultsPinLatest.checked;
  setTab("status");
  clearWorkspace();

  if (!state.currentWorkdir) {
    els.workspaceSubtitle.textContent = "先确认一个工作区目录，然后再创建或恢复任务。";
    els.settingsStatus.textContent = "当前还没有可用的工作区目录。";
    return;
  }

  await loadSettings(state.currentWorkdir);
  await loadResults(state.currentWorkdir);
  await refreshTasks(true);
}

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => setTab(button.dataset.tab || "status")));

els.btnTest.addEventListener("click", testConnection);
els.btnRun.addEventListener("click", () => runTask(false));
els.btnResume.addEventListener("click", () => resumeTask("", true));
if (els.requestTemplateChips) {
  els.requestTemplateChips.addEventListener("click", (event) => {
    const button = event.target.closest("[data-request-template]");
    if (!button) return;
    setActiveRequestTemplate(button.getAttribute("data-request-template") || "review");
  });
}
if (els.requestTemplateGrid) {
  els.requestTemplateGrid.addEventListener("click", (event) => {
    const applyButton = event.target.closest("[data-request-template-apply]");
    if (applyButton) {
      applyRequestTemplate(applyButton.getAttribute("data-request-template-apply") || "");
      return;
    }
    const card = event.target.closest("[data-request-template-card]");
    if (!card) return;
    setActiveRequestTemplate(card.getAttribute("data-request-template-card") || "review");
  });
}
if (els.resultsViewSwitch) {
  els.resultsViewSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("[data-results-view]");
    if (!button) return;
    state.resultsView = button.getAttribute("data-results-view") === "compact" ? "compact" : "gallery";
    renderResults();
  });
}
$("btnReloadTasks").addEventListener("click", () => refreshTasks(true));
$("btnToggleAttention").addEventListener("click", async () => {
  state.onlyNeedsAttention = !state.onlyNeedsAttention;
  $("btnToggleAttention").textContent = state.onlyNeedsAttention ? "显示全部任务" : "仅看异常 / 待确认";
  await refreshTasks(true);
});
$("btnRefreshLogs").addEventListener("click", () => loadLogs(true));
$("btnReloadSettings").addEventListener("click", () => loadSettings(els.workdir.value.trim()));
els.btnRefreshResults.addEventListener("click", () => loadResults(els.workdir.value.trim()));
[
  [els.settingDownloadDir, "input"],
  [els.settingDownloadMode, "change"],
  [els.settingIncludeAudio, "change"],
  [els.settingVideoContainer, "change"],
  [els.settingMaxHeight, "input"],
  [els.settingAudioFormat, "change"],
  [els.settingAudioQuality, "input"],
  [els.settingConcurrentVideos, "input"],
  [els.settingConcurrentFragments, "input"],
  [els.settingSponsorBlockRemove, "input"],
  [els.settingCleanVideo, "change"],
].forEach(([node, eventName]) => {
  if (!node) return;
  node.addEventListener(eventName, () => {
    syncSettingsModeVisibility();
    updateSettingsSummary();
  });
});
els.resultsSearch.addEventListener("input", () => {
  state.resultsSearch = els.resultsSearch.value || "";
  if (state.resultsSearchTimer) clearTimeout(state.resultsSearchTimer);
  state.resultsSearchTimer = setTimeout(() => renderResults(), 160);
});
els.resultsScope.addEventListener("change", () => {
  state.resultsScope = els.resultsScope.value || "all";
  renderResults();
});
els.resultsSort.addEventListener("change", () => {
  state.resultsSort = els.resultsSort.value || "recent_desc";
  renderResults();
});
els.resultsPinLatest.addEventListener("change", () => {
  state.resultsPinLatest = !!els.resultsPinLatest.checked;
  renderResults();
});
els.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveSettings(true);
});

els.provider.addEventListener("change", updateProviderPreset);
els.modelSelect.addEventListener("change", syncModel);
els.baseUrl.addEventListener("input", updateAdvancedSummary);
els.providerCustom.addEventListener("input", updateAdvancedSummary);
els.modelManual.addEventListener("input", updateAdvancedSummary);
els.taskStatusFilter.addEventListener("change", () => refreshTasks(true));
els.taskSort.addEventListener("change", () => refreshTasks(true));
els.taskSearch.addEventListener("input", () => {
  if (state.searchTimer) clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => refreshTasks(true), 220);
});
els.reviewSearch.addEventListener("input", () => {
  state.reviewPage = 1;
  renderReview();
});
els.reviewScope.addEventListener("change", () => {
  state.reviewPage = 1;
  renderReview();
});
els.reviewSort.addEventListener("change", () => {
  state.reviewPage = 1;
  renderReview();
});
els.reviewPageSize.addEventListener("change", () => {
  state.reviewPageSize = Number(els.reviewPageSize.value || 12);
  state.reviewPage = 1;
  renderReview();
});
els.btnStartSelectedDownload.addEventListener("click", startSelectedDownload);
els.btnReviewSelectRecommended.addEventListener("click", () => applyReviewSelection((item) => item.agent_selected));
els.btnReviewSelectPage.addEventListener("click", () => setReviewPageSelection(true));
els.btnReviewClearPage.addEventListener("click", () => setReviewPageSelection(false));
els.btnReviewPrev.addEventListener("click", () => {
  state.reviewPage = Math.max(1, state.reviewPage - 1);
  renderReview();
});
els.btnReviewNext.addEventListener("click", () => {
  state.reviewPage += 1;
  renderReview();
});

els.taskList.addEventListener("scroll", () => {
  if (state.taskScrollRaf) return;
  state.taskScrollRaf = requestAnimationFrame(() => {
    state.taskScrollRaf = 0;
    renderTaskWindow();
  });
});
els.queuePills.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-queue-filter]");
  if (!button) return;
  const filter = button.getAttribute("data-queue-filter") || "";
  if (filter === "needs_attention") {
    state.onlyNeedsAttention = true;
    els.taskStatusFilter.value = "";
    $("btnToggleAttention").textContent = "显示全部任务";
  } else {
    state.onlyNeedsAttention = false;
    els.taskStatusFilter.value = filter;
    $("btnToggleAttention").textContent = "仅看异常 / 待确认";
  }
  await refreshTasks(true);
});

els.taskList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = button.getAttribute("data-task-id");
  if (!id) return;
  if (button.dataset.action === "inspect") return loadTaskLifecycle(id, els.workdir.value.trim());
  if (button.dataset.action === "resume") return resumeTask(id, false);
  if (button.dataset.action === "delete") return deleteTask(id);
});

els.entryBox.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-entry-action]");
  if (!button) return;
  const path = button.getAttribute("data-entry-path") || "";
  if (button.dataset.entryAction === "copy") return copyText(path);
  return openPath(path);
});
els.reviewList.addEventListener("change", (event) => {
  const input = event.target.closest("input[data-review-toggle]");
  if (!input || !state.review?.editable || !Array.isArray(state.review?.items)) return;
  const key = input.getAttribute("data-review-toggle") || "";
  state.review.items = state.review.items.map((item) => (
    item.selection_key === key ? { ...item, selected: input.checked, selection_modified: input.checked !== item.agent_selected } : item
  ));
  if (state.review.summary) {
    state.review.summary.selected_count = state.review.items.filter((item) => item.selected).length;
    state.review.summary.modified_count = state.review.items.filter((item) => item.selected !== item.agent_selected).length;
  }
  syncReviewSummaryIntoLifecycle();
  renderReview();
  renderStatus(state.currentLifecycle || {});
  scheduleReviewSave();
});
els.reviewList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-review-copy]");
  if (!button) return;
  await copyText(button.getAttribute("data-review-copy") || "");
});
els.resultsList.addEventListener("click", async (event) => {
  const reviewButton = event.target.closest("button[data-result-review]");
  if (reviewButton) {
    await inspectResultReview(reviewButton.getAttribute("data-result-review") || "");
    return;
  }
  const relaunchButton = event.target.closest("button[data-result-relaunch]");
  if (relaunchButton) {
    relaunchResultSession(relaunchButton.getAttribute("data-result-relaunch") || "");
    return;
  }
  const taskButton = event.target.closest("button[data-result-task]");
  if (taskButton) {
    await inspectResultTask(taskButton.getAttribute("data-result-task") || "");
    return;
  }
  const retryButton = event.target.closest("button[data-result-retry]");
  if (retryButton) {
    await retryResultSession(retryButton.getAttribute("data-result-retry") || "");
    return;
  }
  const button = event.target.closest("button[data-result-open]");
  if (!button) return;
  await openPath(button.getAttribute("data-result-open") || "");
});
els.resultsSummary.addEventListener("click", async (event) => {
  const reviewButton = event.target.closest("button[data-result-review]");
  if (reviewButton) {
    await inspectResultReview(reviewButton.getAttribute("data-result-review") || "");
    return;
  }
  const relaunchButton = event.target.closest("button[data-result-relaunch]");
  if (relaunchButton) {
    relaunchResultSession(relaunchButton.getAttribute("data-result-relaunch") || "");
    return;
  }
  const taskButton = event.target.closest("button[data-result-task]");
  if (taskButton) {
    await inspectResultTask(taskButton.getAttribute("data-result-task") || "");
    return;
  }
  const retryButton = event.target.closest("button[data-result-retry]");
  if (retryButton) {
    await retryResultSession(retryButton.getAttribute("data-result-retry") || "");
    return;
  }
  const button = event.target.closest("button[data-result-open]");
  if (!button) return;
  await openPath(button.getAttribute("data-result-open") || "");
});
document.body.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-ui-action]");
  if (!button) return;
  await handleUiAction(button.getAttribute("data-ui-action") || "", button);
});
els.workspaceActionsBar.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-workspace-action]");
  if (!button) return;
  await handleUiAction(button.getAttribute("data-workspace-action") || "", button);
});

els.workdir.addEventListener("change", onWorkdirChange);
els.workdir.addEventListener("input", () => {
  if (state.workdirTimer) clearTimeout(state.workdirTimer);
  state.workdirTimer = setTimeout(onWorkdirChange, 420);
});

window.addEventListener("resize", () => renderTaskWindow(true));
document.addEventListener("visibilitychange", () => {
  if (state.currentTaskId && state.currentWorkdir && isLiveTaskStatus(state.currentTaskStatus)) {
    startPolling(state.currentTaskId, state.currentWorkdir);
  }
});

void initializeWorkspace();
