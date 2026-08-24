# IGBot Architecture

## System Overview

The repository contains two cooperating applications with different responsibilities:

- **InstaAddict** is the established Instagram automation engine.
- **IGBot** is the PySide6 desktop application that presents and coordinates that engine.

IGBot does not replace InstaAddict. New desktop features should expose InstaAddict capabilities through explicit adapters and application services while preserving the engine's behavior.

```text
PySide6 views and reusable widgets
                |
            Controllers
                |
      IGBot application services
                |
             Adapters
          /             \
PhoneManager / ADB    InstaAddict engine
```

## Repository Components

### InstaAddict Automation Engine

`InstaAddict/` owns automation behavior, including:

- Configuration and dynamic plugin loading.
- Android interaction through UIAutomator2.
- Instagram screen views, selectors, and navigation.
- Likes, follows, comments, messages, stories, and related interactions.
- Profile filtering and source handling.
- Session state, limits, storage, reports, and recovery behavior.
- Automation plugins for bloggers, hashtags, places, feeds, followers, and other sources.

`InstaAddict.core.bot_flow.start_bot()` is the current engine-level orchestration entry point. IGBot should integrate with this behavior through an adapter rather than importing engine internals throughout the UI.

### IGBot Desktop Application

`IGBot/` owns desktop concerns, including:

- Application startup and QSS loading.
- Main window composition.
- Navigation, toolbar, status bar, and resizable layouts.
- Fleet-oriented device, account, session, and analytics pages.
- UI controllers and worker coordination.
- Presentation of logs, progress, results, and errors.

The desktop layer must not contain Instagram automation algorithms or duplicate device-discovery commands.

## Current Desktop Architecture

### Application Startup

`IGBot.ui.app` creates the `QApplication`, applies the Fusion style and dark QSS theme, creates `MainWindow`, and starts the Qt event loop.

### Main Window

`IGBot.ui.main_window.MainWindow` is the composition root for the desktop interface. It assembles:

- `NavigationSidebar`
- `TopToolbar`
- A `QStackedWidget` for application pages
- `DevicesPage`
- `LiveLogPanel`
- The Qt status bar

Horizontal and vertical splitters provide a resizable layout. The main window connects global UI actions to controllers but does not run ADB commands itself.

### Devices Page

`IGBot.ui.pages.devices_page.DevicesPage` is a view. It renders device serial numbers, refresh state, empty state, and discovery errors. It does not execute ADB commands.

### Device Controller

`IGBot.ui.controllers.device_controller.DeviceController` coordinates device refresh operations. It:

1. Receives refresh requests from the page or toolbar.
2. Prevents overlapping refreshes.
3. Starts a `QRunnable` through the global `QThreadPool`.
4. Calls the existing `PhoneManager` from the worker.
5. Emits Qt signals for started, successful, and failed discovery.

This keeps subprocess work away from the UI thread.

### PhoneManager

`IGBot.core.phone_manager.PhoneManager` is the single IGBot component responsible for ADB phone discovery. It runs `adb devices`, returns ready device serial numbers, and reports discovery failures through `DeviceDiscoveryResult`.

No view, controller, worker, or future service may implement a second `adb devices` parser.

### Live Logging

`LiveLogPanel` installs a Python logging handler and forwards formatted records to Qt through a signal. The signal crossing ensures UI widgets are updated on Qt's main thread. The text buffer is bounded to prevent unbounded memory growth.

## Adapter Approach

Adapters isolate the desktop application from infrastructure and the legacy engine.

An adapter should:

- Present a small, stable interface to IGBot services.
- Translate IGBot requests into existing InstaAddict calls and configuration.
- Translate engine events, results, and failures into structured application data.
- Prevent PySide6 widgets from depending directly on InstaAddict internals.
- Preserve InstaAddict behavior instead of copying it.

Expected adapters include:

- **InstaAddict session adapter:** starts and monitors the existing engine.
- **Configuration adapter:** loads and validates existing account configuration.
- **Session-state adapter:** maps InstaAddict session state into desktop view models.
- **Storage adapter:** exposes existing session history without duplicating persistence rules.
- **Notification adapter:** connects existing reporting capabilities to desktop services.

Adapters may initially wrap existing synchronous APIs. The worker layer is responsible for executing those calls without blocking Qt.

## Workers

Workers perform slow or blocking operations, including:

- ADB discovery and device health checks.
- Starting or stopping InstaAddict sessions.
- Reading large account or session inventories.
- Collecting device metadata.
- Generating reports or processing crash artifacts.

Worker rules:

- Never mutate widgets directly.
- Communicate through Qt signals or thread-safe event objects.
- Use bounded concurrency appropriate for 100+ devices.
- Support cancellation for long-running session work.
- Return structured results and errors.
- Avoid creating an unmanaged thread for every device.

## Controllers

Controllers coordinate a page or feature. They convert user intent into application-service calls and expose results through signals.

Controllers should:

- Remain independent of widget layout details.
- Own refresh and operation state for their feature.
- Prevent accidental duplicate operations.
- Coordinate workers and services.
- Emit structured state suitable for more than one view when practical.

Controllers should not contain ADB parsing, InstaAddict automation logic, or persistence implementations.

## Services

Application services represent product use cases. Planned services include:

- Device inventory and health service.
- Account inventory and assignment service.
- Session start, stop, and monitoring service.
- Configuration validation service.
- Session history and reporting service.

Services should depend on adapter interfaces and domain data, not PySide6 widgets. This makes the same behavior testable without launching the desktop UI.

## Dependency Direction

The intended dependency direction is:

```text
Views -> Controllers -> Application services -> Adapters -> Infrastructure/Engine
```

Dependencies must not point back toward the UI. InstaAddict must remain usable independently through its existing command-line and programmatic interfaces.

## Scale and Concurrency

Supporting 100+ phones requires:

- Asynchronous discovery and health checks.
- Controlled worker-pool concurrency.
- Incremental updates keyed by stable device serial number.
- Table models suitable for sorting and filtering.
- Bounded logs and session histories in memory.
- No polling loop on the Qt main thread.
- Explicit device/session lifecycle states rather than inferred UI text.

The current Sprint 1 controller establishes the asynchronous pattern. Later sprints should extend that pattern rather than bypassing it.
