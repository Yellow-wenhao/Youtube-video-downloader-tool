# Desktop UI Guidelines

## 1. Product Direction

- This product is a desktop workflow tool for YouTube search, review, download, and agent-assisted orchestration.
- The interface should feel like a mature desktop control center, not a dark media site and not a developer-only form dump.
- Visual priority order:
  1. Readability
  2. Task hierarchy
  3. Confirmation safety
  4. Operational confidence

## 2. Theme Strategy

- Default to a light productivity theme.
- Preserve clear contrast between page background, card background, interactive background, and status background.
- Avoid near-black surfaces, low-contrast gray borders, and overly saturated large-area accents.

## 3. Four-Level Surface System

- Page background
  - Used for app shell and outer whitespace
  - Should visually recede
- Card background
  - Used for grouped sections, overview panels, review cards, and workspaces
  - Must be clearly separated from page background
- Interactive background
  - Used for inputs, list panes, logs, embedded review blocks, and button surfaces
  - Must feel one level deeper than card background
- Status background
  - Used for badges, chips, alerts, and semantic notifications
  - Must stay compact and never replace layout hierarchy

## 4. Typography Rules

- Main title: strong, product-level, visually stable.
- Section title: heavier than body copy and consistent across tabs.
- Body text: prioritize readability over compactness.
- Helper text: secondary color, but still clearly readable.
- Never let primary labels or placeholders appear vertically clipped.

## 5. Spacing and Container Rules

- Use comfortable card padding for desktop surfaces.
- Avoid cramped side-by-side panes when content includes:
  - logs
  - plan lists
  - confirmation steps
  - long labels
  - review summaries
- Prefer increasing panel height, internal padding, or width ratio before truncating content.
- Inner scrollable areas must remain visually closed inside their parent cards.

## 6. Interaction Hierarchy

- One clear primary CTA per screen or module.
- Secondary actions must look coordinated, not weak or random.
- Template chips, status chips, and review chips should use a lighter visual weight than action buttons.
- Focus state should improve clarity, not create noisy or awkward shapes.

## 7. Key Page Patterns

### Agent Workspace

- Must present a complete loop:
  - input request
  - plan preview
  - confirmation boundary
  - execution state
  - result or log
- Action controls should live in a dedicated strip, not float between cards.
- Empty states should still look intentional.

### Queue / Task Area

- Agent tasks and manual tasks must be visually distinct at first glance.
- Task card status, next action, and available operation should be scannable within 2-3 seconds.

### Video Review Area

- Should feel like a review cockpit.
- Thumbnail, status, semantic score, similarity warning, and decision reason must form a clear reading rhythm.
- Low-similarity or manual-review states must stand out without turning the whole page visually noisy.

## 8. Anti-Patterns

- Dark-on-dark or gray-on-gray productivity surfaces
- Panels that cut off text or bottom borders
- Selected states that overlap text or create odd pills/ovals
- Buttons with inconsistent radius, weight, or hierarchy
- Placeholder text used as the only label for complex actions

## 9. Implementation Rules

- Centralize visual tokens and shared component styles in `ui_theme.py`.
- Keep page-level composition and sizing changes in `gui_app.py`.
- When polishing a page, adjust both:
  - local layout geometry
  - global semantic styling
- Any future visual change must be checked against:
  - readability
  - container fit
  - hierarchy clarity
  - border visibility
