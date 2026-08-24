# IGBot Product Specification

## Mission

IGBot is a modern Windows desktop application for operating Instagram automation across fleets of Android phones. It provides a professional graphical control surface around the existing InstaAddict automation engine without replacing or duplicating that engine.

The product should make device discovery, account assignment, session control, monitoring, and operational review manageable from one desktop application.

## Main Goals

- Provide a reliable PySide6 desktop interface for InstaAddict.
- Support centralized operation of 100 or more Android phones connected through ADB.
- Support multiple Instagram accounts and explicit account-to-device assignments.
- Keep automation behavior in InstaAddict while presenting it safely through IGBot.
- Keep long-running work off the UI thread so the application remains responsive.
- Present real operational state, logs, errors, and progress without fabricated data.
- Make common operations efficient for both small installations and large device fleets.

## Target Users

- Operators managing multiple Android devices and Instagram accounts.
- Teams running repeatable Instagram automation workflows.
- Technical administrators responsible for ADB connectivity, device readiness, and session health.
- Existing InstaAddict users who want a desktop interface rather than a command-line-only workflow.

Users are expected to understand that Instagram automation carries platform, account, and operational risk. IGBot must communicate failures and uncertain states clearly rather than hiding them.

## Supported Scale

IGBot is designed for fleets of 100 or more Android phones.

This scale affects every product decision:

- Device lists must use compact rows and tables rather than large cards.
- Discovery and status checks must run asynchronously.
- The UI must support filtering, sorting, searching, and bulk operations as those features are introduced.
- Device and session updates should be incremental instead of rebuilding the entire interface unnecessarily.
- Logging must be bounded, filterable, and safe under sustained activity.
- Work must be scheduled with controlled concurrency rather than creating an unbounded thread per phone.

Sprint 1 establishes responsive ADB discovery and the desktop shell. Fleet orchestration and performance validation will be added incrementally.

## Multiple Instagram Accounts

IGBot will support multiple Instagram accounts. Account configuration and automation behavior remain compatible with InstaAddict account configurations.

The product will provide:

- An account inventory.
- Explicit assignment of accounts to Android devices and Instagram application IDs.
- Validation of account configuration before a session starts.
- Visibility into current account, device, and session state.
- Safe handling of simultaneous sessions within configured concurrency limits.
- Historical session results and account-level operational metrics.

Credentials and sensitive account data must not be written into logs or embedded in UI source code.

## Main Features

### Available in the Current Application

- Modern dark PySide6 application shell.
- Left navigation sidebar.
- Global top toolbar.
- Main content area with resizable panels.
- Bottom status bar.
- Devices page populated by the existing `PhoneManager` and real ADB output.
- Non-blocking device discovery through a controller and Qt worker task.
- Clear empty and ADB-error states.
- Live Log panel backed by structured Python logging records.
- Shared styling through the application QSS theme.

### Core Product Capabilities

- Android device discovery and health monitoring.
- Instagram account inventory and device assignment.
- InstaAddict configuration management and validation.
- Start, stop, and monitor automation sessions.
- Per-device and fleet-wide session status.
- Live operational logs and actionable error reporting.
- Session history, limits, and outcome reporting.
- Safe recovery from disconnected devices and failed sessions.

## Future Features

- Searchable and sortable fleet-scale device table.
- Account management and configuration editor.
- Session queue and concurrency controls.
- Bulk device and session operations with explicit confirmation.
- Device tags, groups, and saved filters.
- Session scheduling and working-hours management.
- Analytics dashboards based on real session history.
- Notifications and Telegram integration through adapters.
- Crash artifact and screen-dump inspection.
- Device readiness checks for ADB, Instagram, UIAutomator2, and account assignment.
- Persistent application settings and workspace configuration.
- Exportable operational reports.
- Role-aware controls if IGBot evolves into a shared multi-user system.

Future work must continue to use InstaAddict as the automation engine and must not create a competing automation implementation inside IGBot.
