# Web Migration Plan

## Status

This document is now a historical architecture reference.

The Web-first migration described below has already been completed at the product-direction level. New execution priorities should be tracked in [AGENT_TODO.md](./AGENT_TODO.md), not in this file.

## Decision

The desktop EXE is no longer the primary product direction.

The project will move to:

- local backend API
- browser-based frontend
- agent-first workflow

The old PySide6 GUI stays only as a migration reference until the web workflow covers the core use cases.

## Why

The current EXE UI has become too heavy, too crowded, and too expensive to evolve.

The product problem is no longer "how to make a desktop downloader prettier".
The product problem is now:

- how to expose agent planning clearly
- how to make task state observable
- how to let users configure providers and agent behavior sanely
- how to iterate UI faster

These goals fit a web app far better than a large monolithic desktop GUI.

## New Primary Architecture

```text
Browser UI
   |
   v
FastAPI backend (`app/web/`)
   |
   v
Agent runtime (`app/agent/`)
   |
   v
Tools (`app/tools/`)
   |
   v
Core services (`app/core/`)
```

## Phase Plan

### Phase 1

- Create FastAPI backend entrypoint
- Expose health / provider test / agent planning endpoints
- Add a minimal browser workspace shell
- Keep current task persistence model

### Phase 2

- Expose task run / resume / status / events endpoints
- Replace desktop Agent page with web Agent workspace
- Add web queue and result views

### Phase 3

- Move remaining queue and download orchestration out of `gui_app.py`
- Stop treating the desktop GUI as a supported primary path

## Immediate Engineering Rule

All new product-facing UI work should go to the web stack first.

Desktop GUI changes should be limited to:

- migration support
- bug fixes needed to preserve legacy access
- extracting reusable backend logic
