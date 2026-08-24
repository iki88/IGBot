# IGBot Roadmap

The roadmap builds a desktop product around InstaAddict. It does not include rewriting the automation engine.

## Sprint 1 — Application Shell

Status: completed.

- Establish the PySide6 application entry point.
- Apply a modern dark theme.
- Build the left navigation sidebar, top toolbar, main content area, and bottom status bar.
- Add responsive horizontal and vertical splitters.
- Build the Devices page.
- Use the existing `PhoneManager` for real ADB discovery.
- Run discovery outside the UI thread.
- Add the Live Log panel using Python logging.
- Create reusable navigation, toolbar, and logging widgets.

## Sprint 2 — Fleet Device Management

- Replace the simple device list with a model-backed device table.
- Add scalable sorting, searching, and filtering.
- Display real device state, serial number, connection status, and collected metadata.
- Add refresh timestamps and explicit loading/error states.
- Introduce controlled background health checks.
- Handle disconnected, unauthorized, offline, and newly connected devices clearly.
- Add device grouping or tags only when backed by persistent data.
- Validate performance with at least 100 device records and realistic update frequency.

## Sprint 3 — Account Management

- Build an account inventory from existing InstaAddict account configurations.
- Add account-to-device and application-ID assignment.
- Validate required configuration before session execution.
- Provide a safe configuration editor for supported settings.
- Protect sensitive account data from logs and accidental display.
- Add account search, filtering, and assignment status.
- Keep account configuration compatible with InstaAddict.

## Sprint 4 — Session Orchestration

- Implement an InstaAddict session adapter instead of duplicating engine logic.
- Add application services for session start, stop, cancellation, and status.
- Run every automation session in managed workers.
- Add a fleet-scale session table with account, device, state, progress, and timestamps.
- Introduce bounded concurrency and a session queue.
- Surface engine errors and recovery state through structured events.
- Prevent duplicate sessions for the same assigned account or device.

## Sprint 5 — Monitoring and Analytics

- Build session history from real InstaAddict session data.
- Add filtering by account, device, outcome, and date.
- Present real interaction totals and session-limit outcomes.
- Add operational health summaries for devices and sessions.
- Support report export.
- Integrate existing Telegram/reporting capabilities through adapters.
- Add crash artifact and diagnostic inspection where supported by existing engine output.

## Future

- Session scheduling and working-hours management.
- Bulk operations with selection summaries and explicit confirmation.
- Saved fleet filters and operational workspaces.
- Advanced account and device health rules.
- Configurable notifications.
- Persistent user preferences and window state.
- Packaging, installer, signed releases, and automatic update strategy.
- Accessibility and keyboard-navigation review.
- Long-duration fleet soak testing.
- Optional remote coordination if a single desktop process is no longer sufficient for the target fleet size.
- Role-aware controls if IGBot becomes a shared multi-user system.

Roadmap priorities may change based on field testing, but all work must preserve the architectural boundary between the IGBot desktop application and the InstaAddict automation engine.
