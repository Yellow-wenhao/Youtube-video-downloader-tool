# YouTube-like Desktop UI Guidelines (For This Project)

## 1. Product Intent

- This app is a downloader tool, not a content platform.
- UI style should borrow YouTube Desktop rhythm: dark, clean, task-oriented.
- Priority is always: find video -> download -> observe progress -> manage results.

## 2. Visual Tokens

- Background base: `#0F0F0F`
- Elevated surface 1: `#181818`
- Elevated surface 2: `#212121`
- Border: `#303030`
- Primary text: `#F1F1F1`
- Secondary text: `#AAAAAA`
- Accent red (primary action): `#FF3B30`
- Success: `#22C55E`
- Info: `#3B82F6`
- Warning: `#F59E0B`
- Error: `#EF4444`

## 3. Layout Rules

- Top area contains task context and real-time status.
- Core body uses tabs for:
  - Task configuration
  - Queue / operation center
  - Result browsing
- Video card area must keep strong contrast in dark mode.
- Action buttons use red only for primary actions to preserve visual hierarchy.

## 4. Interaction Rules

- Any long-running operation must expose progress states.
- Queue states should be readable at a glance:
  - pending
  - running
  - success
  - failed
- Failure states should include retry paths.
- Download completion should show visible feedback and support opening folder.

## 5. Resolution and Desktop Adaptation

- Designed for desktop first.
- Must remain readable under 1080p, 2K, and 4K screens.
- Ensure high-DPI usability at 100% / 125% / 150% scale.

## 6. Implementation Mapping

- Theme tokens and styles are centralized in `ui_theme.py`.
- `gui_app.py` only references style helpers and avoids hard-coded hex colors.
- New UI changes should update token helpers first, then UI widgets.

## 7. Next Iteration (Recommended)

- Add a dedicated left navigation rail (Browse / Queue / Downloaded / Failed / Settings).
- Add download toast notifications with click-to-open-folder action.
- Split video detail controls into a right-side panel for YouTube-like flow.
- Add subtle transitions (150ms~250ms) for tab/card state changes.
