# Agent Implementation Plan

## 1. Objective

Turn the current downloader into a task-oriented agent application with minimal rewrite risk.

The first version should let a user say things like:

- "Find 20 Tesla Model 3 reviews from 2024 onward."
- "Download the selected results at 1080p."
- "Retry the failed items from the previous task."

The agent should interpret intent, assemble parameters, invoke tools, track state, and summarize outcomes.

The current repository has already proven that a rule shell can orchestrate tools, but that is now transitional only.
The default planning path should be LLM-first, with the previous regex planner available only as an explicit compatibility fallback.

## 2. Recommended First Release Shape

Use a single-agent architecture:

- one planner/orchestrator
- multiple deterministic tools
- structured task state
- optional GUI integration after the core is stable

Do not start with a chat-only UI that still depends on GUI button automation.

## 3. Current Code Mapping

### Backend source of truth

`myvi_yt_batch.py` already contains the main reusable business capabilities:

- `search_candidates`
- `fetch_detail_metadata`
- `filter_candidates`
- `export_outputs`
- `download_selected`
- `write_download_report_csv`
- CLI parsing in `parse_args` and `main`

### GUI source of truth

`gui_app.py` currently handles:

- desktop interaction
- queue presentation
- subprocess launching
- progress/log rendering
- some run/session orchestration

This means the repository already has:

- execution logic
- a user-facing shell
- multiple natural tool boundaries

What it does not yet have is:

- a reusable application core
- structured tool wrappers
- a task model
- an agent runner

## 4. Target Architecture

```text
app/
  __init__.py
  core/
    __init__.py
    models.py
    search_service.py
    metadata_service.py
    filter_service.py
    download_service.py
    report_service.py
    task_service.py
  adapters/
    __init__.py
    yt_dlp_adapter.py
    ffmpeg_adapter.py
    env_adapter.py
    filesystem_adapter.py
  tools/
    __init__.py
    schemas.py
    registry.py
    search_tools.py
    download_tools.py
    status_tools.py
  agent/
    __init__.py
    runner.py
    planner.py
    session_store.py
    policies.py
    context_provider.py
    prompts/
      system_prompt.md
  gui/
    __init__.py
    agent_bridge.py
```

## 5. Concrete File-by-File Rollout

### Step A: Add shared domain models

Create:

- `app/core/models.py`

Add:

- `SearchRequest`
- `FilterRequest`
- `DownloadRequest`
- `TaskSpec`
- `TaskStatus`
- `TaskResult`
- `TaskSummary`

Purpose:

- stop passing loosely structured dictionaries across new modules
- give tools and agent a stable contract

### Step B: Extract backend services

Create:

- `app/core/search_service.py`
- `app/core/metadata_service.py`
- `app/core/filter_service.py`
- `app/core/report_service.py`
- `app/core/download_service.py`

Move or wrap logic from `myvi_yt_batch.py`:

- search functions -> `search_service`
- metadata functions -> `metadata_service`
- score/filter functions -> `filter_service`
- export/report functions -> `report_service`
- download/report-failure/retry logic -> `download_service`

Important:

- keep old function behavior intact first
- avoid behavior changes during extraction
- only rename after tests exist

### Step C: Isolate adapters

Create:

- `app/adapters/yt_dlp_adapter.py`
- `app/adapters/env_adapter.py`

Move low-level concerns:

- binary detection
- subprocess invocation
- common `yt-dlp` command assembly
- environment checks

Purpose:

- keep core services focused on business flow
- make future mocking/testing easier

### Step D: Introduce a task lifecycle layer

Create:

- `app/core/task_service.py`

Responsibilities:

- create task IDs
- create run/session IDs
- persist task metadata
- publish progress events
- map exceptions to task failure payloads

Suggested statuses:

- `draft`
- `planned`
- `running`
- `awaiting_confirmation`
- `succeeded`
- `failed`
- `cancelled`

### Step E: Add tool wrappers

Create:

- `app/tools/schemas.py`
- `app/tools/registry.py`
- `app/tools/search_tools.py`
- `app/tools/download_tools.py`
- `app/tools/status_tools.py`

First tool set:

- `search_videos`
- `fetch_video_details`
- `filter_videos`
- `prepare_download_list`
- `start_download`
- `get_task_status`
- `retry_failed_downloads`
- `check_runtime_env`

Each tool should:

- accept a typed input model
- call one service
- return JSON-safe payloads
- provide explicit error types

### Step F: Add the agent runtime

Create:

- `app/agent/runner.py`
- `app/agent/planner.py`
- `app/agent/llm_planner.py`
- `app/agent/session_store.py`
- `app/agent/policies.py`
- `app/agent/context_provider.py`
- `app/agent/prompts/system_prompt.md`

Responsibilities:

- `planner.py`
  - define the planner contract and planner selection
- `llm_planner.py`
  - map natural-language requests to tool sequences through an actual LLM backend
- `runner.py`
  - execute plans and handle tool responses
- `policies.py`
  - enforce confirmation for sensitive actions
- `session_store.py`
  - remember recent preferences and last task references
- `context_provider.py`
  - provide recent task summaries and user defaults

The first `context_provider` should not use vector search. It can simply expose:

- recent tasks
- last used directories
- last used resolution/concurrency values
- recent failure summaries

The previous regex planner should remain in a separate legacy module during migration so that:

- the default runtime no longer pretends heuristic parsing is a true agent
- compatibility remains available for controlled fallback
- the new LLM runtime can replace planning without rewriting execution

### Step G: Integrate with the GUI

Create:

- `app/gui/agent_bridge.py`

Responsibilities:

- send GUI user text into the agent runner
- stream plan/progress/result messages back to the UI
- sync task IDs with queue cards and result views

The GUI should consume agent state, not become the agent state.

## 6. Suggested Function Migration Table

From `myvi_yt_batch.py`:

- `ensure_binary`, `run_command`, `yt_dlp_base`
  - move toward adapter/environment layer
- `search_candidates`, `dedupe_by_video_id`
  - move toward `search_service`
- `_fetch_one_detail`, `fetch_detail_metadata`
  - move toward `metadata_service`
- `score_candidate`, `filter_candidates`
  - move toward `filter_service`
- `export_outputs`, `write_download_report_csv`
  - move toward `report_service`
- `download_option_args`, `download_selected`
  - move toward `download_service`
- `parse_args`, `main`
  - keep in `myvi_yt_batch.py` as compatibility wrapper

From `gui_app.py`:

- keep UI classes in place first
- reduce direct subprocess orchestration over time
- redirect task execution through new services or the agent bridge

## 7. MVP Behavior Contract

The MVP agent should be able to:

1. Read a natural-language request
2. Decide whether it needs search, filter, download, retry, or status lookup
3. Produce a short execution plan
4. Ask for confirmation before side-effect-heavy actions
5. Execute tools in order
6. Return a compact summary with output paths and failures

## 8. Example End-to-End Flow

User request:

`帮我找 2024 年后的 Tesla Model 3 review，先筛 20 个，确认后再下载 1080p。`

Expected internal flow:

1. planner parses intent
2. runner creates a `TaskSpec`
3. `search_videos`
4. `fetch_video_details`
5. `filter_videos`
6. `prepare_download_list`
7. policy marks next step as confirmation-required
8. after confirmation, `start_download`
9. `get_task_status`
10. report summary returned to user

## 9. Minimum Test Plan

Before GUI integration, add coverage for:

- search request normalization
- filter determinism
- download option construction
- task status transitions
- error normalization
- CLI compatibility for the old script

## 10. Immediate Next Coding Slice

If implementation starts now, the safest first coding slice is:

1. create `app/` package skeleton
2. add `app/core/models.py`
3. extract `yt_dlp_base`, `ensure_binary`, `run_command` into adapters
4. extract `search_candidates` and `fetch_detail_metadata`
5. make `myvi_yt_batch.py` call the extracted services

This gives the project a real architectural seam without forcing a risky full rewrite.
