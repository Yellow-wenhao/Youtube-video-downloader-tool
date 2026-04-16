# P0 Core Boundary Audit

本审计用于完成 `docs/AGENT_TODO.md` 中的第一项：

- 盘点历史 CLI wrapper 和 `gui_app.py` 中仍未迁移到 `app/core/` / `app/tools/` 的业务逻辑

结论先行：

1. 历史 CLI wrapper 现在已经是薄兼容壳，本身几乎不再承载核心业务逻辑。
2. 真正仍需收口的残留逻辑主要集中在 `gui_app.py`。
3. 除了 GUI，`app/web/main.py` 里也还存在一部分应继续下沉到 service 层的业务编排逻辑。
4. 旧脚本形态的业务兼容入口现在更接近 `youtube_batch.py`，后续若继续做“CLI 薄适配器收口”，应把它一并视为盘点对象。

---

## 1. 已完成迁移的主干能力

当前已经在 `app/core/` / `app/tools/` 中存在并可复用的能力：

- 搜索候选与去重
  - `app/core/search_service.py`
  - `app/tools/search_tools.py`
- 详细元数据抓取
  - `app/core/metadata_service.py`
- 规则打分与筛选
  - `app/core/filter_service.py`
- 报告、CSV、URL 导出
  - `app/core/report_service.py`
- 下载参数到下载执行
  - `app/core/download_service.py`
  - `app/tools/download_tools.py`
- 任务持久化、任务事件、日志、下载进度
  - `app/core/task_service.py`
- 审核候选读取与选择保存
  - `app/core/review_service.py`
- 工具层注册和基础状态工具
  - `app/tools/registry.py`
  - `app/tools/status_tools.py`

---

## 2. `youtube_batch_compat.py` 现状

现状：

- `youtube_batch_compat.py` 仅做兼容转发，直接调用 `youtube_batch.main(...)`
- 它本身不再包含搜索、筛选、下载、报告等核心逻辑

结论：

- `youtube_batch_compat.py` 本身不构成当前 P0 的主要边界风险
- TODO 中对历史 CLI wrapper 的表述可以保留语义，但实际执行上应把注意力转向：
  - `gui_app.py`
  - `app/web/main.py`
  - `youtube_batch.py` 这个旧脚本兼容入口

---

## 3. `gui_app.py` 中仍未迁移的业务逻辑

### A. 下载参数组装仍在 GUI 中

关键位置：

- `build_args(...)`
- `_download_args_for_task(...)`
- `_download_args_for_task_with_file(...)`
- `_enqueue(...)`
- `resume_last_download_task(...)`

残留内容：

- GUI 直接拼 CLI 参数
- GUI 直接决定下载 session name
- GUI 直接组装 cookies / sponsorblock / 并发 / 音频格式等下载参数
- GUI 直接把筛选产物路径映射到下载命令

判断：

- 这些属于典型的 core/service 边界，后续应统一下沉
- Web 和 CLI 不应继续各自复制这一层参数拼装逻辑

### B. 基于工作目录产物的状态推断仍在 GUI 中

关键位置：

- `_count_selected_urls(...)`
- `_summarize_filter_failures(...)`
- `_read_download_summary(...)`
- `_collect_downloaded_records(...)`
- `_find_latest_resume_workdir(...)`

残留内容：

- 通过 `05_selected_urls.txt` 推断是否可下载
- 通过 `03_scored_candidates.jsonl` 生成失败原因摘要
- 通过 `07_download_report.csv` 和 `08_last_download_session.txt` 读取下载摘要
- 通过扫描 workdir 寻找最近可恢复任务

判断：

- 这些逻辑不应只存在于 GUI
- Web 结果页、CLI 恢复能力、未来统一结果视图都需要复用同一套 service

### C. 队列运行编排仍在 GUI 中

关键位置：

- `start_queue(...)`
- `_start_next_pending(...)`
- `_start_download_for_row(...)`
- `download_selected_task(...)`
- `download_all_ready_tasks(...)`
- `_start_next_ready_download(...)`
- `retry_selected_failed_tasks(...)`
- `retry_failed_urls_for_selected_task(...)`
- `download_checked_videos(...)`
- `download_single_video(...)`

残留内容：

- GUI 自己维护 filter queue / download queue 状态机
- GUI 自己决定失败重试、批量下载、单视频下载、从失败 URL 重试
- GUI 自己决定从审核结果到下载动作的跳转

判断：

- 这些是当前最明显的“GUI still owns orchestration”区域
- 后续若要做到 Web / CLI / legacy GUI 共用路径，需要把这一层整理为正式 service 或 runner API

### D. 进程启动与下载进度消费仍是 GUI 私有逻辑

关键位置：

- `_start_process(...)`
- `append_log(...)`
- `_consume_log_for_progress(...)`
- `_parse_progress_line(...)`
- `on_finished(...)`

残留内容：

- GUI 直接启动脚本进程
- GUI 直接从 stdout 文本解析下载阶段与进度
- GUI 直接在结束时读取目录与报告再生成摘要

判断：

- 进程驱动型 legacy path 可以保留
- 但进度解析、摘要读取、结果定位不应只存在于 GUI

### E. 本地 GUI 配置持久化仍独立于 SessionStore

关键位置：

- `_current_config(...)`
- `_apply_config(...)`
- `_load_settings(...)`
- `_save_settings(...)`

残留内容：

- GUI 用独立 `SETTINGS_FILE` 保存 workdir 历史、下载目录历史、最近配置
- 与 `SessionStore` 的默认参数存储没有统一边界

判断：

- 这是后续需要明确“GUI 偏好 vs 任务默认值 vs agent session defaults”的边界点

---

## 4. `app/web/main.py` 当前仍存在的 service 缺口

虽然本轮 TODO 盘点目标最初写的是历史 CLI wrapper / `gui_app.py`，但实际下一步落地前，必须同时注意 Web 层的这几类残留编排：

### A. Web 直接使用非正式 runner 执行路径

关键位置：

- `_run_task_worker(...)`
- `runner._execute_task(...)`

判断：

- 这是 P0 第二、第三项的直接落点
- 需要改成正式的 runner / service 接口

### B. 下载 payload 和 session 路径推断仍在 Web 层

关键位置：

- `_download_task_payload(...)`
- `_extract_session_dir(...)`
- `_download_root(...)`
- `_build_download_results_response(...)`

判断：

- 下载任务组装、结果目录推断、session 聚合，本质都不是 API 层职责
- 这些应继续下沉成正式 service

### C. 结果聚合与删除产物规则仍在 Web 层

关键位置：

- `_build_download_session_view(...)`
- `_build_download_results_response(...)`
- `_delete_task_download_artifacts(...)`

判断：

- 结果页已经产品化，但其底层结果聚合规则还在 API 层
- 后续结果页闭环增强前，应先收口这一层

---

## 5. 下一步建议

基于本次盘点，`docs/AGENT_TODO.md` 中 B 区域后续四项建议按下面顺序推进：

1. 先收口“下载参数组装 + session/path 推断”
   - 对应 GUI 的 `_download_args_for_task*`
   - 对应 Web 的 `_download_task_payload` / `_extract_session_dir` / `_download_root`
2. 再收口“正式执行接口”
   - 去掉 Web 对 `runner._execute_task(...)` 的直接调用
3. 再收口“结果/失败/恢复相关 service”
   - 统一下载摘要、失败列表、最近恢复任务发现逻辑
4. 最后再处理 CLI 薄适配器整理
   - 将 `youtube_batch.py` 与 legacy GUI 都收敛到同一核心边界

---

## 6. 可直接用于下一轮的拆分

下一轮建议直接拆成以下 5 个子任务：

1. 新增统一的下载任务参数组装 service
2. 新增统一的下载会话 / 报告 / 失败文件定位 service
3. 让 Web 改用正式 runner/service 执行入口
4. 让 GUI 下载路径改为复用上述 service
5. 为结果定位和执行入口补最小回归测试
