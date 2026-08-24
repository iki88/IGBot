# IGBot Rules for AI Development Sessions

These rules apply to AI-assisted work in this repository. Read them before planning or modifying IGBot.

## Product Boundaries

1. Never rewrite InstaAddict.
2. Treat `InstaAddict/` as the existing Instagram automation engine.
3. Treat `IGBot/` as the PySide6 desktop application around that engine.
4. Integrate engine behavior through adapters and services.
5. Do not move Instagram automation algorithms into the GUI.
6. Preserve InstaAddict's independent command-line and programmatic operation.

## Existing Capabilities

1. Reuse existing code whenever possible.
2. Reuse `PhoneManager` for Android phone discovery.
3. Never duplicate `adb devices` execution or parsing.
4. Search the repository before creating a new service, model, helper, widget, or adapter.
5. Extend a current ownership boundary instead of creating a competing implementation.

## Production Quality

1. Do not create placeholder code.
2. Do not create demo implementations or fake production data.
3. Do not add TODO implementations.
4. Do not expose nonfunctional navigation actions as if they are complete features.
5. Implement complete loading, success, empty, and failure paths for new operations.
6. Keep errors visible and actionable.
7. Never hide failures by converting them into ordinary empty results.

## UI Architecture

1. Keep UI code separated from business logic.
2. Views render state and emit user intent.
3. Controllers coordinate pages and operations.
4. Services implement application use cases.
5. Adapters wrap InstaAddict and infrastructure boundaries.
6. Prefer reusable widgets for behavior used by more than one page.
7. Use the shared QSS theme instead of scattered inline styles.
8. Prefer model-backed tables for device, account, and session inventories.
9. Preserve responsive, resizable layouts.

## Threading and Performance

1. Never freeze the Qt UI thread.
2. Never run blocking ADB, network, filesystem, or InstaAddict session work on the UI thread.
3. Use worker threads through managed Qt threading primitives.
4. Communicate with widgets through Qt signals.
5. Never update widgets directly from a worker.
6. Use bounded worker-pool concurrency.
7. Do not create an unmanaged thread per phone.
8. Prevent overlapping duplicate operations.
9. Plan cancellation and cleanup for long-running workers.
10. Optimize designs for 100+ phones from the beginning.

## Logging and Security

1. Use structured Python logging instead of `print()`.
2. Include device, account, and session identifiers when available.
3. Keep UI log buffers bounded.
4. Never log credentials, tokens, or sensitive account data.
5. Translate technical failures into concise UI messages while preserving diagnostic logs.

## Code Quality

1. Use type hints at architectural boundaries.
2. Prefer typed result objects over ambiguous dictionaries.
3. Prefer composition over duplication.
4. Keep functions and classes focused.
5. Catch specific exceptions.
6. Avoid process termination inside services, controllers, workers, and views.
7. Follow the existing package structure.
8. Format with Black and lint with Ruff.
9. Add tests for behavior introduced or changed.
10. Run relevant existing tests and report any pre-existing failures separately.

## Change Discipline

1. Inspect current repository state and applicable instructions before editing.
2. Do not modify unrelated files.
3. Preserve user changes in a dirty working tree.
4. Do not perform destructive Git or filesystem operations without explicit authorization.
5. Keep dependency changes intentional and documented.
6. Explain every new file and important architectural decision at handoff.
7. Do not claim verification that was not performed.

## Architecture Consistency Check

Before completing a change, verify:

- Does it keep InstaAddict as the automation engine?
- Does it reuse existing ADB and engine behavior?
- Is blocking work outside the UI thread?
- Are worker results delivered through signals or services?
- Is the component reusable where reuse is expected?
- Will the design remain usable with 100+ phones?
- Are logs structured, bounded, and free of sensitive data?
- Are there any placeholders, fake data, duplicate logic, or TODO implementations?

If any answer is unfavorable, revise the implementation before delivery.
