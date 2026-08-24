# IGBot Coding Guidelines

## General Principles

- Reuse existing code whenever possible.
- Avoid duplicate logic and competing implementations.
- Keep InstaAddict responsible for Instagram automation.
- Keep IGBot responsible for desktop presentation and coordination.
- Prefer composition over duplication and deep inheritance.
- Keep functions and classes focused on one responsibility.
- Make failures explicit and actionable.
- Do not add placeholder, demo, or speculative production code.

## Python Standards

- Use type hints for public functions, methods, signals, service results, and important internal boundaries.
- Prefer typed data objects for structured results instead of loosely shaped dictionaries.
- Use descriptive names based on product concepts such as device, account, assignment, and session.
- Format Python with Black.
- Run Ruff and address relevant findings before completing a change.
- Keep imports ordered and remove unused imports.
- Use docstrings for public classes and behavior that is not evident from the implementation.
- Avoid mutable class-level state unless it is intentionally shared and documented.
- Catch specific exceptions and preserve useful failure details.
- Do not use `sys.exit()` below an application entry-point boundary.

## Reuse and Duplication

- Search the repository before implementing a new capability.
- Extend or adapt an existing component when it already owns the behavior.
- `PhoneManager` owns ADB phone discovery; do not parse `adb devices` elsewhere.
- InstaAddict owns automation behavior, configuration semantics, session limits, and interaction logic.
- Extract a reusable widget or service when the same behavior is needed in multiple pages.
- Do not copy a class and rename it to create a variation. Introduce configuration, composition, or a strategy interface.

## UI and Business Logic Separation

Views should:

- Build and update widgets.
- Emit user intent.
- Render structured state supplied by controllers.
- Avoid subprocess, filesystem, network, and automation-engine operations.

Controllers should:

- Coordinate a feature or page.
- Convert user intent into service calls.
- Start managed workers for blocking operations.
- Expose success, loading, progress, and failure through signals.

Services should:

- Implement application use cases independently of widget layout.
- Depend on adapters or interfaces for infrastructure.
- Return structured results suitable for testing.

Adapters should:

- Wrap existing InstaAddict or infrastructure behavior.
- Translate between external structures and IGBot application models.
- Keep legacy or third-party details out of views and controllers.

## Qt and Threading

- Never perform blocking ADB, filesystem, network, or automation operations on the Qt main thread.
- Use `QThreadPool`, `QRunnable`, or a managed `QThread` appropriate to the operation lifecycle.
- Use bounded concurrency for fleet work.
- Communicate from workers through Qt signals or explicitly thread-safe queues.
- Never mutate a widget from a worker thread.
- Prevent duplicate actions while the same operation is active.
- Support cancellation and orderly cleanup for long-running session workers.
- Keep worker objects alive for the duration of their operation.

## Logging and Errors

- Use Python's `logging` package rather than `print()` for application operations.
- Include identifiers such as device serial, account, and session ID in structured context when available.
- Use appropriate levels: debug, info, warning, error, and exception.
- Do not hide infrastructure failures by returning an ordinary empty result.
- Show concise actionable messages in the UI while retaining diagnostic detail in logs.
- Never log credentials, API tokens, private configuration, or sensitive message content.
- Bound log retention in UI components.

## Models and Fleet Scale

- Use stable identifiers, especially the ADB device serial number.
- Prefer Qt model/view classes for large device, account, and session collections.
- Avoid one complex QWidget instance per table row.
- Apply incremental state changes instead of rebuilding an entire collection.
- Keep sorting and filtering behavior deterministic.
- Design concurrency and memory usage for 100+ devices.

## Configuration and Persistence

- Maintain compatibility with existing InstaAddict account configuration.
- Centralize configuration loading and validation.
- Use atomic writes for material persistent state.
- Distinguish application settings from Instagram account configuration.
- Do not silently discard unknown or invalid configuration.
- Keep runtime data, logs, and secrets outside committed source files.

## Testing and Validation

- Add focused unit tests for services, controllers, adapters, and data transformations.
- Mock process boundaries such as ADB; do not mock the logic under test.
- Add headless Qt tests for widget state and controller signal handling.
- Keep engine compatibility tests separate from desktop presentation tests.
- Test success, empty, loading, cancellation, and failure paths.
- Validate fleet-sensitive features with representative collection sizes.
- Run compilation, formatting, linting, relevant tests, and Git whitespace checks before delivery.

## File Organization

- Put reusable widgets in `IGBot/ui/widgets/`.
- Put complete application pages in `IGBot/ui/pages/`.
- Put UI coordinators in `IGBot/ui/controllers/`.
- Keep core non-visual business concepts out of `IGBot/ui/`.
- Add adapters and services in dedicated packages as those layers are implemented.
- Avoid adding unrelated helpers to broad `utils.py` modules.
