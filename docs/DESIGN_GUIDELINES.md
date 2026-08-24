# IGBot Design Guidelines

## Design Direction

IGBot should look and behave like a modern professional Windows desktop application. The interface is an operational tool for managing a large device fleet, not a marketing dashboard.

Visual decisions should prioritize clarity, density, responsiveness, and rapid problem identification.

## Dark Theme

- Dark mode is the primary application theme.
- Use the shared QSS stylesheet instead of per-widget inline styles.
- Maintain strong text contrast and visible focus, hover, selected, disabled, warning, and error states.
- Reserve saturated colors for actions and meaningful status.
- Do not encode state by color alone; pair color with text or an icon.
- Use a restrained palette consistently across pages.

The current theme uses dark neutral surfaces, blue navigation selection, green primary actions, and red error presentation.

## Modern Windows Desktop Application

- Follow familiar desktop interaction patterns: toolbars, status bars, tables, splitters, shortcuts, context menus, and selection-based actions.
- Keep primary actions visible and secondary actions discoverable without clutter.
- Provide keyboard access for frequent actions. Device refresh currently uses `F5`.
- Show progress and failure state near the operation being performed.
- Avoid web-page patterns that waste vertical space or obscure dense operational information.
- Use standard Qt behavior unless a custom interaction provides a clear operational benefit.

## Tables Instead of Large Cards

Device, account, and session inventories should use model-backed tables.

Tables should support, as appropriate:

- Stable row identifiers.
- Sorting.
- Search and filtering.
- Multi-selection.
- Column resizing and sensible default widths.
- Compact status indicators.
- Incremental row updates.
- Bulk actions based on current selection.

Large cards are unsuitable for inventories of 100+ phones. Cards may be used for small summaries or a selected item's details, not as the primary fleet view.

## Professional Spacing

- Use consistent page margins, section gaps, control heights, and alignment.
- Current pages use approximately 24–28 pixels for outer margins and 8–20 pixels between related elements.
- Group related controls closely and separate unrelated sections clearly.
- Avoid arbitrary spacing values within individual widgets when an existing spacing pattern applies.
- Keep dense tables compact while preserving readable row height.
- Align headers, filters, tables, and action controls to a shared content grid.

## Consistent Icons

- Use one coherent icon set appropriate for Windows desktop use.
- Give the same action the same icon everywhere.
- Pair unfamiliar icons with text or tooltips.
- Provide correct disabled and selected states.
- Do not use emoji as production navigation icons.
- Do not use icons as the only indication of critical state.
- Load icons through a centralized resource or icon provider when the icon system is introduced.

## Resizable Layout

- Use layouts and splitters rather than fixed widget positions.
- Define practical minimum sizes, not rigid page dimensions.
- Let the primary table or content view consume available space.
- Preserve usability at the application's minimum supported window size.
- Ensure long serial numbers, account names, and messages elide or scroll cleanly.
- Allow operational panels such as Live Log to be resized without covering primary content.
- Consider persisting splitter and column sizes in a later settings sprint.

## Designing for 100+ Phones

- Default to compact, sortable tables.
- Provide search and filters before adding additional visual decoration.
- Avoid rendering heavy custom widgets for every row.
- Update only rows whose state changed.
- Keep device serial numbers as stable identifiers.
- Make offline, unauthorized, busy, failed, and healthy states easy to distinguish.
- Put fleet-wide counts and selection counts near relevant actions.
- Require confirmation for destructive or high-impact bulk operations.
- Show partial success when a bulk operation succeeds for some devices and fails for others.
- Keep background refresh visible but unobtrusive.

## Empty, Loading, and Error States

- Empty state means a successful request returned no records.
- Loading state means work is in progress and should disable duplicate execution where necessary.
- Error state must explain what failed and, where possible, how to correct it.
- Never present an ADB failure as an empty fleet.
- Do not populate screens with fake rows to make a design look complete.

## Live Log Presentation

- Display real structured application records only.
- Use a monospaced font for log output.
- Bound retained output to protect memory.
- Keep timestamps and severity visually scannable.
- Future filtering should support severity, device, account, session, and text search.
- Never display passwords, tokens, or sensitive account configuration.
