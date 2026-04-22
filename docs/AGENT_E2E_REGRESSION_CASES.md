# Agent E2E Regression Cases

This file defines the fixed manual regression checklist for the current LLM-first agent runtime.

## Goal

Use these cases after changing any of the following:

- `app/agent/llm_planner.py`
- `app/agent/runner.py`
- `app/gui/agent_bridge.py`
- `gui_app.py` when a change explicitly targets the legacy desktop shell

## Source of Truth

Structured fixture:

- `tests/agent_e2e_cases.json`

## Manual Verification Rules

For each case:

1. Fill Provider, Base URL, Model, and API Key in the legacy GUI.
2. Click `测试连接` first.
3. Submit the request in the Agent page.
4. Verify:
   - the plan intent matches the expected intent
   - the step count is reasonable
   - download/confirmation behavior matches the case
   - the Agent page status text is human-readable on success or failure

## Extra Failure Scenarios

Also verify these non-happy paths:

- Missing API key should show a configuration error, not a raw traceback.
- Wrong Base URL should show a connection error, not a generic failure.
- LLM returns non-JSON prose should surface a response/schema error with a clear message.
- Unsupported or malformed plan fields should be blocked before execution.
