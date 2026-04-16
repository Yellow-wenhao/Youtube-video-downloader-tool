# UI Visual Polish Plan

## Goal

Turn the current downloader + agent desktop app into a clearer, more productized light-theme workspace without changing the core workflow.

## Design Objectives

1. Make the app readable at a glance on 1080p desktop screens.
2. Give Agent, Queue, and Video Review pages distinct but consistent visual hierarchy.
3. Remove cramped containers and incomplete card boundaries.
4. Make primary actions and safety confirmations feel intentional.
5. Keep all visual rules centralized enough to support later iterations.

## Visual System

### Surface Hierarchy

- Level 1: page shell
- Level 2: card shell
- Level 3: embedded interactive areas
- Level 4: semantic status surfaces

### Type Hierarchy

- App title: product headline
- Hero title: workspace headline
- Section title: card headline
- Body: operational content
- Hint: explanatory guidance
- Badge: state or mode marker

### Control Hierarchy

- Primary button: one strong action at a time
- Secondary button: operational support
- Template chip: lightweight suggestion
- Status badge: semantic state only

## Execution Scope

### Phase 1. Theme Foundation

- Refine token naming and keep all colors semantic.
- Harmonize button radius, card radius, borders, and embedded backgrounds.
- Replace heavy dark hover states with light productivity-friendly interaction states.

### Phase 2. Agent Workspace

- Build a stronger request loop:
  - command entry
  - request templates
  - plan preview
  - confirmation panel
  - action strip
  - activity log
- Ensure all panels feel closed and spacious.
- Keep confirmation actions visibly tied to confirmation content.

### Phase 3. Queue and Review Surfaces

- Strengthen differentiation between Agent and manual task cards.
- Improve card hover clarity and next-action readability.
- Productize video audit cards so review status and semantic score scan faster.

### Phase 4. Consistency Pass

- Re-check titles, card spacing, button widths, status chip contrast, and empty states.
- Ensure no control shows clipped text.
- Keep future rules documented for continued polish.

## Changes Executed In This Round

### Theme and Token Layer

- Reinforced the light semantic surface system in `ui_theme.py`.
- Standardized card shell borders and embedded interactive surfaces.
- Refined button hierarchy and hover behavior for light mode.

### Agent Workspace

- Increased input and workspace card breathing room.
- Reworked left navigation into a more stable segmented control style.
- Added a dedicated action strip for status + continue/refresh/queue actions.
- Improved plan, confirmation, and log pane closure and readability.

### Queue and Video Review

- Softened overly dark hover borders.
- Aligned queue task cards, next-action surfaces, and review cards with the same card-shell logic.
- Tightened review reason blocks and status chip readability.

## Follow-Up Recommendations

1. Add richer empty states for plan preview, confirmation, and activity log.
2. Add step-state color semantics inside Agent plan rows.
3. Add a clearer selected/hover state for queue cards.
4. Add explicit statistic headers above video review results when page density grows further.
