# Web Workspace Regression Checklist

## Purpose

Use this checklist after changing any of the following:

- `app/web/main.py`
- `app/web/schemas.py`
- `app/web/static/index.html`
- `app/web/static/workspace.css`
- `app/web/static/workspace.js`

This checklist protects the current web-first workspace behavior:

- one clear task-stage surface
- explicit confirmation-to-download transition
- real-time download progress visibility
- one user-facing download entry instead of internal artifact panels

## Core Manual Flow

Run one real task that requires confirmation before download.

Verify the following in order:

1. Create the task and enter the workspace.
2. The status tab shows a single primary confirmation CTA when the task is waiting for confirmation.
3. Click `确认下载并继续`.
4. Within about 100ms, the confirmation button becomes disabled and the workspace enters `准备下载中`.
5. The right-side download card updates at roughly sub-second cadence once download progress starts.
6. The old developer-facing cards do not appear:
   - `结果与产物`
   - `最近状态`
7. When the task succeeds, the status tab keeps only the user-facing download entry:
   - `打开下载目录`
   - or equivalent completed-download entry

## Refresh And Visibility Checks

Verify the following resilience cases:

1. Refresh the page while the task is in `等待确认`, `准备下载中`, or `正在下载`.
2. Re-open the same task from the queue.
3. Confirm the workspace restores the correct stage and current progress.
4. Switch the browser tab away and back.
5. Confirm polling resumes normally and does not create duplicate timers or duplicated progress UI.

## Failure And Empty-State Checks

Verify these non-happy paths:

1. Failed tasks show a readable failure message and keep logs accessible from the `日志` tab.
2. Failed tasks do not reintroduce internal artifact cards as primary results.
3. Before download starts, the progress card shows a meaningful waiting state instead of a blank area.
4. Before completion, the download entry card shows the target directory state instead of fake completed output.

## Interface Consistency Checks

These should remain true for both `/api/tasks/{task_id}/lifecycle` and `/api/tasks/{task_id}/poll`:

- `workspace_stage` matches the current workspace phase
- `workspace_stage_label` is human-readable
- `primary_message` is suitable for direct display
- `confirmation` is present only when confirmation is truly required
- `download_entry` always points to the single user-facing output entry

## Desktop Layout Checks

Run these viewport checks in a real desktop browser after recent UI changes.

### 1366px Desktop

1. Open the workspace at around `1366 x 768` or a similar desktop viewport.
2. Confirm the left rail still reads in one pass:
   - `任务输入`
   - `任务队列`
3. Confirm the right workspace area still shows:
   - tabs in one row or a readable wrapped layout
   - no clipped pills, buttons, or filter labels
4. In `结果` tab, verify both result views:
   - `封面预览` keeps video cards readable without crushing actions
   - `紧凑列表` keeps thumbnail, title, meta, and action buttons aligned
5. In `设置` tab, confirm:
   - `常用设置` is fully readable without horizontal overflow
   - `媒体质量设置` and `高级下载行为` can expand without breaking card edges

### 1920px Desktop

1. Open the workspace at around `1920 x 1080`.
2. Confirm the layout does not become visually hollow:
   - cards do not stretch into overly long unreadable rows
   - result cards still group cleanly by session and by success/failed status
3. In `结果` tab, confirm:
   - `封面预览` uses the extra space for more cards instead of oversized single cards
   - `紧凑列表` still feels dense and scan-friendly rather than sparse
4. In `审核` tab, confirm candidate cards keep stable spacing and action alignment.

### Windows 125 Percent Scaling

1. On Windows display scaling set to `125%`, reopen the workspace.
2. Confirm the following do not clip vertically:
   - tab labels
   - pill labels
   - primary / secondary buttons
   - input placeholders
   - select controls
3. Confirm sticky and scroll containers remain usable:
   - left queue area scrolls normally
   - right workspace area still fits in viewport without impossible nested scrolling
4. Confirm compact result rows do not crop thumbnails or overlap buttons.

## Static Risk Notes

Based on the current CSS, these are the main spots to inspect first during manual validation:

- Left rail width is fixed at `356px`, so `1366px` is the minimum desktop width that still needs close visual checking.
- Workspace area uses sticky desktop layout and `100dvh`-based heights, so Windows `125%` scaling should focus on nested scroll behavior.
- Result compact mode uses a `168px + content` two-column card; this is the highest-risk area for button wrapping and text clipping.
- Settings overview uses a two-column summary block that collapses only below `1100px`, so `1366px` should still verify readable balance.

## Current Baseline

The following acceptance points were manually validated in the current branch:

1. Confirmation CTA appears correctly in the real flow.
2. Clicking confirm transitions the workspace into the task-stage view immediately.
3. The download progress surface updates in real time during download.
4. The completed task view keeps only the user-facing download entry.
