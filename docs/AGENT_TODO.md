# Agent TODO

本文件是项目后续推进的唯一执行清单。

用途只有三个：

1. 回答“项目现在做到哪了”
2. 回答“下一步应该做什么”
3. 给后续会话提供不需要重复询问的默认推进顺序

约定：

- `docs/AGENT_TODO.md`
  - 唯一的项目推进 TODO
- `docs/AGENT_IMPLEMENTATION_PLAN.md`
  - 架构说明和模块边界参考
- `docs/WEB_WORKSPACE_REGRESSION_CHECKLIST.md`
  - Web 工作台改动后的回归验收基线

执行规则：

- 每次新会话默认直接处理本清单中“从上到下第一个未完成的 P0 / P1 项”
- 如果某一项跨度过大，先在该项下拆成 3 到 7 个子任务，再开始实现
- 做完一项后必须同步更新勾选状态，并补一句验证结果
- 非阻塞型 UI polish 不得插队到 P0 核心边界收口之前，除非它是明确的产品级缺陷
- 新需求优先归类到现有 TODO 项下，不新增平行计划

---

## A. 当前基线（已完成）

- [x] Web-first 产品方向已经明确，桌面 GUI 降级为 legacy 参考面
- [x] `app/core/`、`app/tools/`、`app/agent/`、`app/web/` 主体目录已经存在
- [x] Web 工作台主链路可跑通：创建任务、查看状态、审核候选、勾选下载、确认下载、查看结果
- [x] Web 工作台已完成一轮结构拆分：`index.html` / `workspace.css` / `workspace.js`
- [x] 已有基础回归保护：workspace smoke、workspace state、review API
- [x] 已有 `run_web.bat`，本地启动 Web 服务不必每次手敲命令

验证：

- `test_web_workspace_smoke.py` 已通过
- 多轮人工验收已覆盖审核、勾选、下载启动、结果查看、界面打磨

---

## B. P0 当前优先级：核心边界收口

目标：

- Web、CLI、未来 legacy GUI 都通过同一套 core/service 路径完成核心动作
- `app/web/main.py` 主要负责 API 映射和 view model，不再内嵌过多业务流程判断
- 从 `myvi_yt_batch.py` / `gui_app.py` 新发现的核心逻辑不再继续复制到 Web 层

TODO：

- [x] 盘点 `myvi_yt_batch.py` 和 `gui_app.py` 中仍未迁移到 `app/core/` / `app/tools/` 的业务逻辑
- [x] 把剩余的下载参数组装、运行时环境判断、结果产物定位逻辑继续下沉到 core/service 层
- [x] 去掉 Web 层对内部私有执行路径的依赖，尤其是类似 `runner._execute_task(...)` 这类非正式调用
- [x] 确保 CLI 入口继续可用，但角色变成“薄适配器”，不再承载核心业务分支
- [x] 明确 `SessionStore`、`TaskStore`、下载会话目录、报告文件之间的边界，避免路径推断逻辑分散在多个模块

建议子任务拆分模板：

1. 盘点现状与残留逻辑
2. 定义正式 service / runner 边界
3. 替换 Web 非正式调用路径
4. 收口 CLI 适配层
5. 补最小回归验证

验证：

- `docs/P0_CORE_BOUNDARY_AUDIT.md` 已补充本轮边界盘点，确认 `myvi_yt_batch.py` 已是薄兼容壳，残留热点主要在 `gui_app.py`、`app/web/main.py`、`youtube_batch.py`
- 已新增 `app/core/download_workspace_service.py` 与 `app/core/environment_service.py`，并替换 Web / tools 层的下载 payload、session / 结果定位、运行环境检查逻辑
- `app/agent/runner.py` 已新增正式 `execute_task(...)` 入口，`app/web/main.py` 不再直接调用私有 `_execute_task(...)`
- 已新增 `app/core/cli_pipeline_service.py`，`youtube_batch.py` 现在只负责参数解析与调用共享 CLI pipeline；`myvi_yt_batch.py` 继续作为薄兼容 wrapper
- `SessionStore` 已新增正式 `last_download_session` 边界，`TaskStore` 已新增 `load_download_session_ref(...)`，`app/core/download_workspace_service.py` 负责协调 SessionStore、TaskResult 和 legacy marker
- `app/core/download_service.py` 现在会在下载完成后统一写入最近下载会话引用；Web、tools、planner 与 GUI 的关键读取点已切到 shared download session API
- `python -m py_compile app/core/download_workspace_service.py app/core/environment_service.py app/tools/download_tools.py app/tools/status_tools.py tests/test_download_workspace_api.py` 通过
- `python -m py_compile app/agent/runner.py app/web/main.py` 通过
- `python -m py_compile app/core/cli_pipeline_service.py youtube_batch.py myvi_yt_batch.py tests/test_cli_pipeline_service.py` 通过
- `python -m py_compile app/agent/session_store.py app/core/models.py app/core/task_service.py app/core/download_workspace_service.py app/core/download_service.py app/agent/legacy_rule_planner.py app/agent/llm_planner.py app/tools/download_tools.py app/tools/status_tools.py app/web/main.py gui_app.py tests/test_download_session_boundary.py` 通过
- `python -m unittest discover -s tests -p "test_download_session_boundary.py"` 通过
- `python -m unittest discover -s tests -p "test_cli_pipeline_service.py"` 通过
- `python youtube_batch.py --help` 与 `python myvi_yt_batch.py --help` 均可正常输出 CLI 帮助
- 仓库内临时目录冒烟已验证：`build_download_task_payload(...)` 能按当前 session defaults 产出下载 payload，`load_download_results(...)` 能正确聚合下载会话与视频文件
- 受本地默认 `python` 环境缺少 `fastapi` 影响，`tests/test_download_workspace_api.py`、`test_web_review_api.py`、`test_web_workspace_state.py` 当前无法在此解释器下执行

---

## C. P1 下一优先级：Agent Runtime 补强

目标：

- Planner 失败时，前端能区分“配置问题 / 网络问题 / LLM 输出不合法 / 执行失败”
- 用户在失败后能看到可执行的恢复路径，而不是只有报错文本
- Planner 默认路径保持 LLM-first，legacy fallback 仅在配置中显式开启

TODO：

- [x] 把运行时系统提示词正式落到 `app/agent/prompts/system_prompt.md`
- [x] 明确 LLM planner 的成功、配置失败、连接失败、响应结构失败四类错误映射，并统一到用户可理解的前端文案
- [x] 给任务生命周期补充更明确的失败解释和恢复建议，不只返回失败 message
- [x] 扩展 `SessionStore` 的偏好记忆能力，除了默认下载参数，还要覆盖最近任务偏好、最近结果上下文、常用筛选偏好
- [x] 保持 legacy rule planner 仅作为显式 fallback，不允许在默认路径下静默回退
- [x] 把 retry flow 做成正式能力：失败下载重试、结果页重试、从上次审核结果重新发起下载

建议子任务拆分模板：

1. 收口 planner 错误模型
2. 增加前端展示文案映射
3. 落地系统提示词文件
4. 扩展会话记忆
5. 打通 retry / resume / fallback 验收

验证：

- 已新增 [system_prompt.md](D:/YTBDLP/app/agent/prompts/system_prompt.md) 与 [prompt_loader.py](D:/YTBDLP/app/agent/prompt_loader.py)，运行时系统提示词不再硬编码在 `llm_planner.py` 字符串常量里
- [llm_planner.py](D:/YTBDLP/app/agent/llm_planner.py) 现在通过 prompt loader 渲染 `system_prompt.md`，并注入当前 runtime defaults
- `python -m py_compile app/agent/prompt_loader.py app/agent/llm_planner.py tests/test_agent_prompt_loader.py` 通过
- `python -m unittest discover -s tests -p "test_agent_prompt_loader.py"` 通过
- 已在 [planner.py](D:/YTBDLP/app/agent/planner.py) 固定 planner 错误映射：`config`、`connection`、`response_structure`、`unknown`，并统一输出 `user_title` / `user_message` / `user_recovery` / `user_actions`
- [runner.py](D:/YTBDLP/app/agent/runner.py) 与 [main.py](D:/YTBDLP/app/web/main.py) 已保留并透传这套字段；[workspace.js](D:/YTBDLP/app/web/static/workspace.js) 已统一用同一套字段格式化连接测试、任务创建和恢复失败文案
- `python -m py_compile app/agent/planner.py app/agent/runner.py app/agent/llm_planner.py app/web/main.py tests/test_planner_error_mapping.py` 通过
- `python -m unittest discover -s tests -p "test_planner_error_mapping.py"` 通过
- 已新增 [failure_diagnosis.py](D:/YTBDLP/app/web/failure_diagnosis.py)，把任务失败统一收口为 `category / title / summary / recovery / actions` 结构，并接入 lifecycle / poll / result 响应
- [runner.py](D:/YTBDLP/app/agent/runner.py) 现在会显式记录 `error_type` 与 `failure_origin`，上下文占位符解析失败也会正式落盘为失败结果，不再只在后台抛异常
- [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 失败态已改为优先展示“失败原因 + 恢复建议 + 建议动作”，不再只显示原始报错字符串
- `python -m py_compile app/web/failure_diagnosis.py app/web/schemas.py app/web/main.py app/agent/runner.py tests/test_task_failure_diagnosis.py` 通过
- `python -m unittest discover -s tests -p "test_task_failure_diagnosis.py"` 通过
- [session_store.py](D:/YTBDLP/app/agent/session_store.py) 已新增三类正式偏好区块：`recent_task_preferences`、`recent_result_context`、`common_filter_preferences`，并保持旧 session 文件向后兼容
- [runner.py](D:/YTBDLP/app/agent/runner.py) 现在会把这三类记忆注入 planner 默认上下文，并在任务创建 / 任务收尾时自动回写最近任务偏好与筛选偏好
- [llm_planner.py](D:/YTBDLP/app/agent/llm_planner.py) 的 user prompt 已带上最近任务、最近结果和常用筛选偏好上下文，后续规划可直接利用这部分记忆
- [download_workspace_service.py](D:/YTBDLP/app/core/download_workspace_service.py) 与 [main.py](D:/YTBDLP/app/web/main.py) 已在下载会话落盘和结果页聚合时补写最近结果上下文，不再只有 `last_download_session` 单点引用
- `python -m py_compile app/agent/session_store.py app/agent/runner.py app/agent/llm_planner.py app/core/download_workspace_service.py app/web/main.py tests/test_session_store_preferences.py` 通过
- `python -m unittest discover -s tests -p "test_session_store_preferences.py"` 通过
- `python -m unittest discover -s tests -p "test_download_session_boundary.py"` 通过
- [planner.py](D:/YTBDLP/app/agent/planner.py) 现在正式区分三种模式：默认 `llm`、显式 `legacy_rule_based`、显式 `llm_with_legacy_fallback`；默认路径不会再静默回退到 legacy
- 已新增显式 `FallbackPlanner`，只有在 `YTBDLP_AGENT_PLANNER=llm_with_legacy_fallback` 或 `llm_then_legacy` 时，才会在 LLM planner 失败后退到 legacy rule planner，并把 fallback 原因写入 `planner_notes`
- [legacy_rule_planner.py](D:/YTBDLP/app/agent/legacy_rule_planner.py) 已统一补齐 `planner_name` 标记，确保 fallback 后能从结果中识别实际使用的是 legacy planner
- `python -m py_compile app/agent/planner.py app/agent/legacy_rule_planner.py app/agent/llm_planner.py tests/test_planner_fallback_policy.py` 通过
- `python -m unittest discover -s tests -p "test_planner_fallback_policy.py"` 通过
- `python -m unittest discover -s tests -p "test_planner_error_mapping.py"` 通过
- [download_service.py](D:/YTBDLP/app/core/download_service.py) 现在把失败 URL 文件正式写入下载会话目录，而不是只依赖 workdir 根目录共享 `06_failed_urls.txt`；结果页可据此稳定判断会话级 retry 能力
- [download_workspace_service.py](D:/YTBDLP/app/core/download_workspace_service.py) 已新增 retry payload 构建与会话级失败 URL 解析，结果聚合会优先使用 session-local `06_failed_urls.txt`，并避免把最近一次会话的失败文件误关联到其他历史会话
- [main.py](D:/YTBDLP/app/web/main.py) 已新增 `POST /api/results/retry-session`，会从结果会话创建正式 `retry_failed_downloads` 任务并直接走共享 runner 路径
- [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 结果页已补“重试失败项”入口，创建成功后会自动切回状态页并跟踪新任务
- `python -m py_compile app/core/download_workspace_service.py app/core/download_service.py app/tools/download_tools.py app/web/schemas.py app/web/main.py tests/test_download_workspace_api.py` 通过
- `conda run -n base python -m unittest discover -s tests -p "test_download_workspace_api.py"` 通过
- `conda run -n base python -m unittest discover -s tests -p "test_download_session_boundary.py"` 通过
- 已确认本机可执行 Web 测试的解释器来自 Miniconda `base` 环境；`Agent` 环境当前不含 `fastapi`

---

## D. P1 下一优先级：任务到结果的闭环增强

目标：

- 用户完成一次下载后，不需要依赖文件系统手动找目录，就能在 Web 里完成查看、重试、再次发起任务
- 结果页不再只是展示层，而是闭环操作面的一部分

TODO：

- [x] 让结果页中的下载会话和任务 ID 建立更稳定的关联，避免结果页只是一个脱离任务上下文的目录浏览器
- [x] 在结果页增加明确的失败项重试入口，支持基于当前会话重新发起失败视频下载
- [x] 在结果页增加排序、筛选和“最近会话固定置顶”能力
- [x] 增加“基于这次结果重新发起相似任务”或“回到原任务继续调整”的闭环入口
- [x] 把审核结果、已下载结果、失败结果串成完整链路：任务 -> 审核 -> 下载 -> 结果 -> 重试 / 再发起

建议子任务拆分模板：

1. 建立 task 与 session 关联
2. 补结果页动作模型
3. 补失败重试入口
4. 补再次发起任务入口
5. 做结果页验收闭环

验证：

- [download_workspace_service.py](D:/YTBDLP/app/core/download_workspace_service.py) 已新增会话级 metadata `09_download_session.json`，下载会话会正式落盘 `source_task_id`
- 同一文件已补旧数据兼容：历史下载会话若缺少 metadata，会回扫 `TaskStore` 中的下载结果引用，补出 `session_dir -> task_id / task_title / task_status`
- [schemas.py](D:/YTBDLP/app/web/schemas.py) 与 [main.py](D:/YTBDLP/app/web/main.py) 已把 `source_task_id / source_task_title / source_task_status / source_task_available` 暴露给结果页
- [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 结果页已增加“查看关联任务”入口，可从下载会话直接跳回对应任务状态页
- [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 与 [workspace.css](D:/YTBDLP/app/web/static/workspace.css) 已把失败项重试入口强化为双入口：会话级失败提示卡 + 失败视频卡片内直接重试按钮，失败视频会优先分组展示
- [index.html](D:/YTBDLP/app/web/static/index.html)、[workspace.js](D:/YTBDLP/app/web/static/workspace.js) 与 [workspace.css](D:/YTBDLP/app/web/static/workspace.css) 已为结果页补齐关键词筛选、范围筛选、排序和“最近会话固定置顶”开关；最近会话会在任何排序下保持显式置顶
- [download_workspace_service.py](D:/YTBDLP/app/core/download_workspace_service.py)、[schemas.py](D:/YTBDLP/app/web/schemas.py) 与 [main.py](D:/YTBDLP/app/web/main.py) 已把 `source_task_user_request / source_task_intent` 暴露给结果页
- [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 结果页已补两个闭环动作：“回到原任务继续调整”和“基于这次结果新建相似任务”；后者会把原始自然语言请求直接带回输入区，等待用户修改后重新运行
- [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 与 [workspace.css](D:/YTBDLP/app/web/static/workspace.css) 已在结果页补全一条显式 journey：原任务 -> 回到审核 -> 下载结果 -> 重试 / 再发起，用户不需要自己理解这些状态块之间的关系
- `conda run -n base python -m py_compile app/core/download_workspace_service.py app/core/task_service.py app/web/schemas.py app/web/main.py tests/test_download_session_boundary.py tests/test_download_workspace_api.py` 通过
- `conda run -n base python -m unittest discover -s tests -p "test_download_session_boundary.py"` 通过
- `conda run -n base python -m unittest discover -s tests -p "test_download_workspace_api.py"` 通过

---

## E. P2 Web 产品化继续打磨

目标：

- Web 主要页面在桌面使用场景下都能快速扫读
- 新用户第一次进来能知道“现在做什么、下一步点哪里、结果在哪里看”

TODO：

- [x] 继续压缩设置页密度，把下载默认设置也做成分层 / 渐进展开
- [x] 给任务输入区补一组更产品化的请求模板或示例
- [x] 继续优化结果页的视频预览模式，明确大图预览和高密度列表之间的取舍
- [x] 把空状态、失败态、等待态的文案统一到后端展示模型和前端组件层
- [x] 按 `1366px`、`1920px`、Windows `125%` 缩放继续做人工验收

验证：

- [index.html](D:/YTBDLP/app/web/static/index.html)、[workspace.js](D:/YTBDLP/app/web/static/workspace.js) 与 [workspace.css](D:/YTBDLP/app/web/static/workspace.css) 已把设置页改为“常用设置 + 媒体质量设置 + 高级下载行为”的渐进展开结构
- 设置页顶部已补默认策略摘要；目录、下载模式、分辨率、音频格式、并发和 SponsorBlock 等变更会实时同步摘要文案
- 下载模式现在会按相关性显隐字段：`audio` 模式聚焦音频格式与音质，`video` 模式聚焦分辨率、封装和音轨策略
- 本轮未改后端接口；改动范围为静态前端结构、样式和交互收敛
- [index.html](D:/YTBDLP/app/web/static/index.html)、[workspace.js](D:/YTBDLP/app/web/static/workspace.js) 与 [workspace.css](D:/YTBDLP/app/web/static/workspace.css) 已在任务输入区补“快速模板”模块，包含审核型下载、对比评测、素材剪辑、只保留音频四类产品化示例
- 模板区支持切换模板卡片与一键填入请求文本；点击填入后会直接把示例写入输入框，便于用户在原模板上快速改主题、数量和时间范围
- [index.html](D:/YTBDLP/app/web/static/index.html)、[workspace.js](D:/YTBDLP/app/web/static/workspace.js) 与 [workspace.css](D:/YTBDLP/app/web/static/workspace.css) 已在结果页补“封面预览 / 紧凑列表”双模式开关，用户可按当前任务选择偏视觉浏览或高密度扫读
- 结果卡片与视频项现在会随模式切换：封面预览保留大缩略图卡片，紧凑列表改为左侧小封面 + 右侧信息动作区，移动端自动退回单列避免拥挤
- [schemas.py](D:/YTBDLP/app/web/schemas.py) 与 [main.py](D:/YTBDLP/app/web/main.py) 已新增统一 `panel_state` 展示模型，并接入 review / results / logs 响应，用于表达等待态、空态和失败态
- [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 已改为优先消费后端 `panel_state`；接口失败时前端本地兜底也会转成同一结构，再统一走 `panelStateMarkup(...)` 组件渲染
- [WEB_WORKSPACE_REGRESSION_CHECKLIST.md](D:/YTBDLP/docs/WEB_WORKSPACE_REGRESSION_CHECKLIST.md) 已补充桌面验收章节，覆盖 `1366px`、`1920px` 和 Windows `125%` 缩放下的布局、结果页双模式、设置页展开和滚动容器检查点
- 已完成真实浏览器人工验收：`1366px`、`1920px` 与 Windows `125%` 缩放场景通过
- 本轮已继续修复任务输入区在 `356px` 左侧 rail 中的布局拥挤问题，收口为适合窄侧栏的单列表单与纵向主按钮

---

## F. P2 质量与发布收口

目标：

- 文档层没有相互冲突的“下一步”
- 测试投入与当前阶段匹配，优先保护核心状态流和 API 合约
- 新人进入仓库时，能立刻知道默认从 Web 入口工作

TODO：

- [x] 更新 `docs/AGENT_TODO.md`，使其与当前实现状态一致，不再保留已过期的 Phase 0 / Phase 1 skeleton 描述
- [x] 清理和校正文档职责，避免 `TODO_UI_NEXT.md`、`UI_REFACTOR_TODO.md`、`AGENT_TODO.md` 三者对同一事项重复下指令
- [x] 增加后端优先级测试：
  - [x] 任务状态转换
  - [x] review selection 更新
  - [x] download-selected 启动路径
  - [x] results 聚合
  - [x] planner 错误映射
- [x] 保持现有最小前端 smoke 为基线，不扩张成高成本 UI 自动化体系，除非后续确有频繁回归
- [x] 明确“Web 是默认本地入口”的文档和启动方式，把桌面 GUI 描述为 legacy compatibility path

验证：

- 本轮已完成 `docs/AGENT_TODO.md` 重写，使其可以单独回答“做到哪了 / 下一步是什么 / 完成标准是什么”
- [TODO_UI_NEXT.md](D:/YTBDLP/docs/TODO_UI_NEXT.md) 已降级为 legacy / 历史参考文档，明确声明不再承担项目级“下一步 TODO”职责
- [UI_REFACTOR_TODO.md](D:/YTBDLP/docs/UI_REFACTOR_TODO.md) 已改成设计与 legacy GUI 参考文档，不再与 Web-first 主线争夺执行顺序
- 三份文档职责现在收口为：
  - [AGENT_TODO.md](D:/YTBDLP/docs/AGENT_TODO.md)：唯一执行清单
  - [TODO_UI_NEXT.md](D:/YTBDLP/docs/TODO_UI_NEXT.md)：legacy 零散 UI 备忘
  - [UI_REFACTOR_TODO.md](D:/YTBDLP/docs/UI_REFACTOR_TODO.md)：legacy GUI / 设计历史参考
- [test_web_workspace_state.py](D:/YTBDLP/tests/test_web_workspace_state.py) 已新增顺序型状态流测试，覆盖“等待确认 -> 准备下载 -> 正在下载 -> 整理结果 -> 完成”以及“运行中 -> 失败”两条核心转换路径
- `conda run -n base python -m unittest discover -s tests -p "test_web_workspace_state.py"` 通过
- [test_web_review_api.py](D:/YTBDLP/tests/test_web_review_api.py) 已补 review selection 更新契约测试，覆盖更新后返回值与后续 GET 的 round-trip 一致性，以及 `video:` / `url:` / `row:` 选择键回退路径
- `conda run -n base python -m unittest discover -s tests -p "test_web_review_api.py"` 通过
- [test_download_workspace_api.py](D:/YTBDLP/tests/test_download_workspace_api.py) 已补 `download-selected` 启动路径测试，覆盖成功创建下载任务、后台 runner 调用参数，以及“等待确认 / 仍在运行 / 零勾选”三类 409 拒绝路径
- `conda run -n base python -m unittest discover -s tests -p "test_download_workspace_api.py"` 通过
- [test_download_workspace_api.py](D:/YTBDLP/tests/test_download_workspace_api.py) 已补 `results` 聚合测试，覆盖空结果时的 `panel_state`、多会话排序、总会话/总视频统计、每会话 `video_count / success_count / failed_count / retry_available` 以及来源任务关联字段
- `conda run -n base python -m unittest discover -s tests -p "test_download_workspace_api.py"` 通过（9 tests）
- [test_planner_error_mapping.py](D:/YTBDLP/tests/test_planner_error_mapping.py) 已补 `planner 错误映射` 契约测试，覆盖未知错误兜底映射、`AgentRunnerPlanningError` 默认收口、`/api/agent/plan` 的 planning error 透传，以及 `/api/agent/test-connection` 的配置错误文案透传
- `conda run -n base python -m unittest discover -s tests -p "test_planner_error_mapping.py"` 通过（7 tests）
- [README.md](D:/YTBDLP/README.md) 已明确 Web-first 默认入口：`run_web.bat` / `run_web.ps1` 为本地默认启动方式，CLI 为兼容入口，`gui_app.py` 为 legacy compatibility path
- [CONTRIBUTING.md](D:/YTBDLP/CONTRIBUTING.md) 已同步 Web-first 开发约定，并把最小前端 smoke 测试固定为推荐回归基线，明确不扩张为高成本 UI 自动化体系
- [run_web.ps1](D:/YTBDLP/run_web.ps1) 已改为优先使用 conda 环境启动 Web 服务，默认环境名为 `base`，并支持 `YTBDLP_CONDA_ENV` 覆盖
- `conda run -n base python -m unittest discover -s tests -p "test_web_workspace_smoke.py"` 通过（2 tests）
- [app_paths.py](D:/YTBDLP/app/core/app_paths.py) 已新增共享默认路径解析器，Web 与 CLI 不再把 `D:/YTBDLP/...` 这类开发机目录写死在默认值里
- [main.py](D:/YTBDLP/app/web/main.py) 已新增 `/api/bootstrap`，前端首次加载会从当前机器动态获取推荐 workdir 和默认下载目录
- [index.html](D:/YTBDLP/app/web/static/index.html) 与 [workspace.js](D:/YTBDLP/app/web/static/workspace.js) 已去掉前端 `Workdir` 硬编码，首次打开页面不再显示开发机绝对路径
- [runner.py](D:/YTBDLP/app/agent/runner.py) 的 CLI 默认 `--workdir` 已改为 shared default resolver，不再使用仓库内固定目录
- [gui_settings.json](D:/YTBDLP/gui_settings.json) 已清理为通用示例型默认值，不再保留个人历史目录
- [.gitignore](D:/YTBDLP/.gitignore) 已补 `build/`、`dist/`、`.tmp_test_runs/` 等忽略项，降低把本机构建/测试产物继续提交进仓库的风险

---

## 回归与验收约定

文档验收：

- `docs/AGENT_TODO.md` 能单独回答“项目现在做到哪、下一步做什么、完成标准是什么”
- 不需要再依赖聊天上下文解释“下一步任务”

实现验收：

- 涉及 Web 工作台改动时，继续执行 `docs/WEB_WORKSPACE_REGRESSION_CHECKLIST.md`
- 涉及任务状态、审核、结果接口改动时，优先补后端 API / state 测试
- 涉及 planner / runner 改动时，优先验证错误映射、 fallback 策略、resume / retry 路径

交付验收：

- 任一会话结束时，仓库里的 TODO 状态必须比开始时更接近真实，而不是更混乱

---

## 默认推进顺序

1. 核心边界收口
2. Agent runtime 补强
3. 任务与结果闭环
4. Web 产品化继续打磨
5. 质量与发布收口

如果没有新的高优先级产品缺陷，后续默认直接从 B 区域第一个未完成项开始推进。
