# AGENTS.md

## 1. Project Mission

This repository started as a Windows desktop YouTube search/filter/download tool built on `yt-dlp + PySide6`.

The active product direction is now to evolve it into a web-first, agent-enabled application:

- Users should be able to describe a download task in natural language.
- An agent should translate that request into structured search, filtering, and download actions.
- The agent should orchestrate existing backend capabilities instead of driving a desktop GUI.
- The primary user interface should be a browser-based frontend talking to a local backend API.

The desktop GUI is now legacy compatibility surface, not the primary product surface.
The current goal is not to build a fully autonomous system. The goal is to build a reliable local web agent on top of the existing downloader.

## 2. Current Entrypoints

- `app/web/main.py`
  - Target web backend entrypoint.
  - Should become the default local application entrypoint over time.
- `gui_app.py`
  - Legacy desktop GUI entrypoint.
  - Still useful as migration reference, but no longer the preferred product shell.
- `youtube_batch.py`
  - Current generic CLI entrypoint.
- `youtube_batch_compat.py`
  - Thin compatibility wrapper kept for migration continuity.

These two files are the current sources of truth. New architecture should be extracted from them gradually rather than rewritten all at once.

## 3. Agentization Strategy

Follow this order:

1. Extract reusable backend logic into importable core services.
2. Add structured tool wrappers around those services.
3. Build a single-agent orchestration layer on top of those tools.
4. Expose the agent through a backend API.
5. Build the browser frontend on top of that API.

Do not start with:

- multi-agent collaboration
- browser automation
- GUI click automation
- RAG-heavy architecture
- cloud-first deployment

## 4. Engineering Principles

- Prefer `core-first` architecture over `GUI-first` or `frontend-first` orchestration.
- Prefer direct Python function calls over subprocess shelling where practical.
- Keep CLI compatibility while refactoring.
- Make long-running tasks observable with structured state, not only free-form logs.
- Use schemas and typed payloads for agent tools.
- Keep the first agent deterministic and safe, even if it is less flexible.
- Treat the web backend API as the main composition boundary for the new product.

## 5. Safety and Confirmation Boundaries

The agent may run without confirmation for:

- search
- metadata fetch
- local filtering
- report generation
- reading prior task state
- environment inspection

The agent should require confirmation before:

- starting bulk downloads
- updating `yt-dlp`
- updating `ffmpeg`
- reusing or overriding an existing output directory
- using cookies that affect authenticated access
- applying unusually high concurrency settings

## 6. Repository Working Rules

- Do not make the agent depend on GUI widget state as the primary execution path.
- Do not duplicate business logic in GUI and web layers.
- Move logic out of `gui_app.py` and old compatibility wrappers incrementally into new modules.
- Preserve the existing CLI behavior unless a deliberate migration step says otherwise.
- Keep Windows compatibility as a first-class constraint.

## 7. Recommended Target Module Layout

This is the intended direction, not the current structure:

```text
app/
  gui/
  core/
  agent/
  tools/
  adapters/
  web/
```

Suggested responsibilities:

- `app/core/`
  - search, metadata, filtering, download, report services
- `app/tools/`
  - agent-callable wrappers with schemas and error mapping
- `app/agent/`
  - planner, runner, session state, policies, prompt files
- `app/adapters/`
  - `yt-dlp`, `ffmpeg`, filesystem, environment adapters
- `app/gui/`
  - Legacy desktop-facing composition, views, and bridge code
- `app/web/`
  - FastAPI app, request/response schemas, API routes, and static frontend hosting

## 8. Current Function Migration Guideline

Likely extraction sources from the historical batch CLI:

- search-related functions -> `search_service`
- metadata functions -> `metadata_service`
- scoring and filtering -> `filter_service`
- export/report functions -> `report_service`
- download and retry behavior -> `download_service`
- binary/tool resolution -> `environment_service` or adapter layer

The old script should gradually become a thin CLI adapter around these services.

## 9. Agent Runtime Expectations

The first production agent should support:

- natural-language task parsing
- parameter normalization
- safe tool invocation
- task progress inspection
- failure explanation
- retry guidance
- lightweight preference memory

The first production agent should not require RAG. If future retrieval becomes useful, add it behind a dedicated context provider interface.

## 10. Documentation Expectations

Keep these documentation types separate:

- `AGENTS.md`
  - repository-level development and collaboration guidance
- `docs/AGENT_TODO.md`
  - phased delivery checklist
- `docs/AGENT_IMPLEMENTATION_PLAN.md`
  - concrete architecture and migration plan
- future prompt docs such as `app/agent/system_prompt.md`
  - runtime behavior instructions for the product agent

## 11. Testing Priorities

As agentization work begins, prioritize tests for:

- argument normalization
- filter/scoring determinism
- download option assembly
- task status transitions
- error mapping from backend exceptions to tool responses

Avoid coupling tests to GUI rendering unless the change is explicitly UI-only.

## 12. Definition of Success for Phase 1

Phase 1 is successful when:

- core logic is callable without the GUI
- at least one end-to-end download workflow can be executed through importable services
- tool wrappers can return structured outputs
- the future agent can be added without refactoring everything again
